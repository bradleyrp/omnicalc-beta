#!/usr/bin/python

import sys,os,re,time,glob
import yaml
import pickle,json,copy,glob,signal,collections
from base.tools import unpacker,path_expand,status,argsort,unescape,tupleflat
from base.tools import delve,asciitree,catalog,status,unique,flatten,tracer
from base.gromacs_interface import gmxread,mdasel,edrcheck,slice_trajectory,machine_name
from base.hypothesis import hypothesis
from base.computer import computer
from base.timer import checktime
from base.store import picturefind,store,load
from copy import deepcopy
import MDAnalysis

conf_paths,conf_gromacs = "paths.yaml","gromacs.py"

#---joblib and multiprocessing modules require all functions to be registered in __main__
# WHAT WAS I THINKING? for fn in glob.glob('calcs/codes/*.py'): execfile(fn)

#---CLASS
#-------------------------------------------------------------------------------------------------------------

class Workspace():

	"""
	The "workspace" represents the requested slices, groups, calculations, and plots, to the rest of the 
	omnicalc codes. It reads YAML-formatted specs files saved to calcs/specs/*.yaml and then performs the 
	following functions in order:

	1. Index the molecules in a simulation to make a "group". These are used to generate slices of the 
	   simulation trajectory which contain certain elements specified by the user.
	2. Make a "slice" of a simulation trajectory. Typically we sample a part of a production run with a 
	   specific start time, duration, and sampling interval.
	3. Run a calculation on many simulations, grouped by "collection" and specified by specially-formatted 
	   functions in python scripts at calcs/<name>.py. These functions received the simulation data from 
	   slices saved in the post data folder.
	4. Makes plots from the output of the calculations.

	!Note: recently removed functions which may cause downstream issues: 
		sns,collection,get_files,shortname,key_recon,fullpath,lookup,clear_lookups,
		path,get_regex_groups,sort_steps,picture,collect_times,
	"""

	#---presets
	conf_paths = conf_paths
	conf_gromacs = conf_gromacs
	#---throw an error if you are missing more than 20% of the data
	missing_frame_tolerance = 0.2
	#---! deprecated below?
	members_with_specific_parts = ['slices']

	def __init__(self,fn,previous=False,autoreload=False):

		"""
		Note that we initialize paths.yaml and superficial data first, then load from the workspace or
		parse the dataset if the workspace was not saved.
		"""
		self.filename = path_expand(fn)
		self.paths = unpacker(conf_paths)
		self.machine = unpacker(conf_gromacs,'machine_configuration')[machine_name]
		del sys.modules['yaml']

		self.nprocs = self.machine['nprocs'] if 'nprocs' in self.machine else 1
		#---write timeseries to the post data directory when making slices
		self.write_timeseries_to_disk = self.paths.get('timekeeper',False)
		self.postdir = os.path.join(path_expand(self.paths['post_data_spot']),'')
		self.plotdir = os.path.join(path_expand(self.paths['post_plot_spot']),'')
		#---generic variables associated with the workspace
		self.vars = {}
		self.meta = {}
		self.calc = {}
		#---automatically add preexisting files to the workspace if they are found
		self.autoreload = autoreload

		#---for each "spot" in the yaml file, we construct a template for the data therein
		#---the table of contents ("toc") holds one parsing for every part regex in every spot
		self.spots,self.toc = {},collections.OrderedDict()
		for name,details in self.paths['spots'].items():
			rootdir = os.path.join(details['route_to_data'],details['spot_directory'])
			if not os.path.isdir(rootdir):
				raise Exception('\n[ERROR] cannot find root directory %s'%rootdir)
			for part_name,part_regex in details['regexes']['part'].items():
				spot = (name,part_name)
				self.toc[spot] = {}
				self.spots[spot] = {
					'rootdir':os.path.join(rootdir,''),
					'top':details['regexes']['top'],
					'step':details['regexes']['step'],
					'part':part_regex,
					'namer':eval(details['namer']),
					'namer_text':details['namer'],
					}
				self.spots[spot]['divy_keys'] = self.divy_keys(spot)
		#---we always require an xtc entry in the parts list
		if 'xtc' not in zip(*self.spots.keys())[1]: 
			raise Exception('\n[ERROR] you must have "xtc" in the parts list')
		#---set a cursor which specifies the active spot which should always be the first in the yaml
		self.cursor = self.spots.keys()[0]
		#---the self.c variable holds the top spot name but not the part name
		self.c = self.cursor[0]
		#---! default to XTC
		self.trajectory_format = 'xtc'
		self.merge_method = self.paths.get('merge_method','careful')
		
		#---open self if the filename exists 
		#---note that we save parser results but not details from paths.yaml in case these change
		if os.path.isfile(self.filename): 
			self.load(previous=previous)
			self.verify()
		#---otherwise make a new workspace
		else: self.bootstrap()

	def bootstrap(self):

		"""
		Parse the data when the workspace is first created or when we need to re-parse the data.
		"""

		#---paths.yaml specifies directories which might be absent so make them
		if not os.path.isdir(self.postdir): os.mkdir(self.postdir)
		if not os.path.isdir(self.plotdir): os.mkdir(self.plotdir)
		#---parse the simulations found in each "spot"
		for spot in self.spots: self.treeparser(spot)
		#---if there is a part named edr then we use it to get simulation times
		#---! edr files are required to infer times for slicing however we might also use xtc or trr later
		assert 'edr' in zip(*self.spots.keys())[1]
		self.treeparser_edr()
		#---data are stored in dictionaries by spot name
		all_top_keys = [i for j in [k.keys() for k in self.toc.values()] for i in j]

		#---! under development
		for key in ['post','groups','slices']:
			if key not in self.members_with_specific_parts:
				self.__dict__[key] = {i:{} for i in all_top_keys}
			else: self.__dict__[key] = {(spot,i):{} 
				for spot in self.toc for i in self.toc[spot]}
		self.save()

	def load(self,previous=True):

		"""
		Unpack a saved workspace pickle into self.
		"""

		incoming = pickle.load(open(self.filename,'rb'))
		#---reconstitute things that were bootstrapped
		#---we do not load spots because e.g. paths might have changed slightly in paths.yaml
		self.post = incoming.post
		self.groups = incoming.groups
		self.slices = incoming.slices
		self.vars = incoming.vars
		self.meta = incoming.meta
		self.calc = incoming.calc
		self.toc = incoming.toc

		#---retain the incoming workspace for comparison
		if previous: self.previous = incoming
		
	def save(self,quiet=False):

		"""
		Write the class to a pickle.
		Saving the workspace obviates the need to check timestamps and parse EDR files every time.
		Note: future development here will allow the workspace to be fully and quickly reconstituted from
		clock files saved to disk if the user sets the "timekeeper" option in paths.yaml.
		"""

		#---cannot save lambda functions in pickle
		detach = deepcopy(self.spots)
		for spot,details in self.spots.items(): 
			del details['namer']
			del details['divy_keys']
		if not quiet: status('saving',tag='work')
		#---ignore interrupts while writing the pickle
		wait = signal.signal(signal.SIGINT,signal.SIG_IGN)
		pickle.dump(self,open(self.filename,'wb'))
		signal.signal(signal.SIGINT,wait)
		if not quiet: status('done saving',tag='work')
		#---reattach the lambda functions after saving
		self.spots = detach
		
	def verify(self,scrub=False):

		"""
		Check the post-processing filenames to make sure they are present.
		!!! Needs finished.
		"""

		status('passing through verify',tag='development')
		return

		#---! the following needs to be reincorprated into the workflow
		missing_files = []
		checks = []
		#---group files
		checks += [(('groups',sn,group),val[group]['fn']) 
			for sn,val in self.groups.items() for group in val]
		checks += [sl[name][key] for sn,sl in self.slices.items() 
			for name in sl for key in ['gro',self.trajectory_format] if key in sl[name]]
		for route,fn in checks:
			if not os.path.isfile(self.postdir+fn): missing_files.append([route,fn])
		if missing_files != [] and not scrub: 
			status('missing files: %s'%str(missing_files),tag='warning')
		elif missing_files != []:
			status('scrubbing deleted files from the workspace: %s'%str(missing_files),tag='warning')
			for route,fn in missing_files:
				del delve(self.__dict__,*route[:-1])[route[-1]]
		else: print '[STATUS] verified'

	###---NAMING

	def keyfinder(self,spot=None):

		"""
		Decorate the keys_to_filename lookup function so it can be sent to e.g. slice_trajectory.
		If you are only working with a single spot, then this creates the file-name inference function
		for all data in that spot.
		"""

		spot = self.cursor if not spot else spot
		def keys_to_filename(*args,**kwargs):

			"""
			After decomposing a list of files into keys that match the regexes in paths.yaml we often 
			need to reconstitute the original filename.
			"""

			strict = kwargs.get('strict',True)
			if not spot in self.toc: raise Exception('need a spotname to look up keys')
			#---! it may be worth storing this as a function a la divy_keys
			#---follow the top,step,part naming convention
			try:
				backwards = [''.join(['%s' if i[0]=='subpattern' else chr(i[1]) 
					for i in re.sre_parse.parse(regex)]) 
					for regex in [self.spots[spot][key] for key in ['top','step','part']]]
				fn = os.path.join(
					self.spots[spot]['rootdir'],
					'/'.join([backwards[ii]%i for ii,i in enumerate(args)]))
			except Exception as e: 
				tracer(e)
				#---previously: raise Exception('error making keys: %s,%s'%(str(spotname),str(args)))
				import pdb;pdb.set_trace() #---legit
			if strict: assert os.path.isfile(fn)
			return fn

		return keys_to_filename

	def divy_keys(self,spot):

		"""
		The treeparser matches trajectory files with a combined regex. 
		This function prepares a lambda that divides the combined regex into parts and reduces them to 
		strings if there is only one part. The resulting regex groups serve as keys in the toc.
		"""

		group_counts = [sum([i[0]=='subpattern' 
			for i in re.sre_parse.parse(self.spots[spot][key])]) 
			#---apply naming convention
			for key in ['top','step','part']]
		cursor = ([0]+[sum(group_counts[:i+1]) for i in range(len(group_counts))])
		slices = [slice(cursor[i],cursor[i+1]) for i in range(len(cursor)-1)]
		divy = lambda x: [y[0] if len(y)==1 else y for y in [x[s] for s in slices]]
		return divy

	def spotname_lookup(self,sn):

		"""
		Find the spotname for a particular simulation.
		"""

		assert type(sn)==str
		spotnames = [key for key,val in self.toc.items() if sn in val]
		spotnames_unique = list(set(zip(*spotnames)[0]))
		if len(spotnames_unique) != 1: 
			raise Exception('[ERROR] you cannot have the same simulation in multiple spots.\n'+
				'simulation = "%s" and "%s"'%(sn,str(spotnames)))
		return spotnames_unique[0]

	def prefixer(self,sn):

		"""
		Choose a prefix for naming post-processing files.
		"""

		#---"spot" is a tuple of spotname and the part name
		#---namer takes the spotname (called spot in the yaml defn of namer) and the simulation name
		#---we include the partname when accessing self.spots
		spot = spotname,partname = (self.spotname_lookup(sn),self.trajectory_format)
		prefix = self.spots[spot]['namer'](spotname,sn)
		return prefix
		
	###---DATASET PARSER

	def treeparser(self,spot):

		"""
		This function parses simulation data which are organized into a "spot". 
		It writes the filenames to the table of contents (self.toc).
		"""

		spot_sub = self.spots[spot]
		rootdir = spot_sub['rootdir']
		#---start with all files under rootdir
		fns = [os.path.join(dirpath,fn) 
			for (dirpath, dirnames, filenames) 
			in os.walk(rootdir,followlinks=True) for fn in filenames]
		#---regex combinator is the only place where we enforce a naming convention via top,step,part
		#---note that we may wish to generalize this depending upon whether it is wise to have three parts
		regex = ('^%s\/'%re.escape(rootdir.rstrip('/'))+
			'\/'.join([spot_sub['top'],spot_sub['step'],spot_sub['part']])
			+'$')
		matches_raw = [i.groups() for fn in fns for i in [re.search(regex,fn)] if i]
		if not matches_raw: 
			status('no matches found for spot: "%s,%s"'%spot,tag='warning')
			return
		#---first we organize the top,step,part into tuples which serve as keys
		#---we organize the toc as a doubly-nested dictionary of trajectory parts
		#---the top two levels of the toc correspond to the top and step signifiers
		#---note that this procedure projects the top,step,part naming convention into the toc
		matches = [self.spots[spot]['divy_keys'](i) for i in matches_raw]
		self.toc[spot] = collections.OrderedDict()
		#---sort the tops into an ordered dictionary
		for top in sorted(set(zip(*matches)[0])): 
			self.toc[spot][top] = collections.OrderedDict()
		#---collect unique steps for each top and load them with the parts
		for top in self.toc[spot]:
			#---sort the steps into an ordered dictionary
			for step in sorted(set([i[1] for i in matches if i[0]==top])):
				#---we sort the parts into an ordered dictionary
				#---this is the leaf of the toc tree and we use dictionaries
				parts = sorted([i[2] for i in matches if i[0]==top and i[1]==step])
				self.toc[spot][top][step] = collections.OrderedDict([(part,{}) for part in parts])
		#---now the toc is prepared with filenames but subsequent parsings will identify EDR files

	def treeparser_edr(self):

		"""
		A special tree parser gets times from edr files.
		"""

		#---perform this operation on any spotnames with a part named "edr"
		spots_edr = [i for i in self.spots.keys() if i[1]=='edr']
		#---prepare a list of edr files to parse first
		targets = []
		for spot in spots_edr:
			for sn in self.toc[spot].keys():
				steps = self.toc[spot][sn].keys()
				for step in steps:
					parts = self.toc[spot][sn][step].keys()
					for part in parts:
						fn = self.keyfinder(spot)(sn,step,part)
						keys = (spot,sn,step,part)
						targets.append((fn,keys))
		for ii,(fn,keys) in enumerate(targets):
			status('scanning EDR files',i=ii,looplen=len(targets),tag='scan')
			times = edrcheck(fn)
			leaf = delve(self.toc,*keys)
			leaf['start'],leaf['stop'] = times

	def get_timeseries(self,sn,strict=False,**kwargs):

		"""
		Typically EDR times are stored in the toc for a particular spot. 
		This function retrieves the sequence from the spot that corresponds to the parsed edr data 
		for either the active spot denoted by the cursor or a user-supplied spot from kwargs.
		"""

		self.slice(sn)
		spot = kwargs.get('spot',self.cursor)
		#---! get the default spot and get the edr part 
		assert (spot[0],'edr') in self.toc
		edrtree = self.toc[(spot[0],'edr')][sn]
		#---naming convention
		sequence = [((sn,step,part),tuple([edrtree[step][part][key] 
			for key in ['start','stop']]))
			for step in edrtree 
			for part in edrtree[step]]
		#---return a list of keys,times pairs
		return sequence
		#---! discarded logic below
		#seq_key_fn = [((sn,sub,fn),self.fullpath(sn,sub,fn)) for sub in subs for fn in self.toc[sn][sub]]
		#seq_time_fn = [(self.edr_times[self.xtc_files.index(fn)],key) for key,fn in seq_key_fn
		#	if not strict or (None not in self.edr_times[self.xtc_files.index(fn)])]
		#return seq_time_fn

	def get_last_start_structure(self,sn,partname='structure'):
	
		"""
		A function which identifies an original structure for reference.
		Note that this function requires a spot with a part named "structures" for the right lookup.
		Note that this function needs to be renamed since it can also get TPR files.
		"""
		
		#---call slice to move the cursor
		self.slice(sn,part_name=partname)
		step,structures = self.toc[self.cursor][sn].items()[-1]
		#---since structures should be equivalent we take the first
		structure = structures.keys()[0]
		keys = sn,step,structure
		return self.keyfinder()(*keys)

	def confirm_file(self,fn):
	
		"""
		When the workspace is deleted we can automatically detect preexisting files.
		This function handles that procedure.
		"""
		
		if self.autoreload: 
			print '[STATUS] autoreloading %s'%fn
			return True
		else:
			caller = sys._getframe().f_back.f_code.co_name
			print "[STATUS] function %s found %s"%(caller,fn)
			ans = raw_input('[QUESTION] is this file valid else quit (y/N)? ')
			if re.match('^(y|Y)',ans): return True
			else: raise Exception('\n[ERROR] file was invalid and must be deleted manually:\n%s'%fn)
			#---! may want to later allow a file deletion if the user says the file is invalid		

	###---CREATE GROUPS AND SLICES

	def create_group(self,**kwargs):
	
		"""
		Create a group.
		"""

		sn = kwargs['sn']
		name = kwargs['group']
		select = kwargs['select']
		cols = 100 if 'cols' not in kwargs else kwargs['cols']
		#---naming convention holds that the group names follow the prefix and we suffix with ndx
		simkey = self.prefixer(sn)+'.'+name
		fn = '%s.ndx'%simkey
		#---see if we need to make this group
		if os.path.isfile(self.postdir+fn) and name in self.groups[sn]: return
		elif os.path.isfile(self.postdir+fn):
			if self.confirm_file(self.postdir+fn):
				self.groups[sn][name] = {'fn':fn,'select':select}
			return
		status('creating group %s'%simkey,tag='status')
		#---read the structure
		uni = gmxread(self.get_last_start_structure(sn))
		sel = mdasel(uni,select)
		#---write NDX 
		import numpy as np
		iii = sel.indices+1	
		rows = [iii[np.arange(cols*i,cols*(i+1) if cols*(i+1)<len(iii) else len(iii))] 
			for i in range(0,len(iii)/cols+1)]
		with open(self.postdir+fn,'w') as fp:
			fp.write('[ %s ]\n'%name)
			for line in rows:
				fp.write(' '.join(line.astype(str))+'\n')
		self.groups[sn][name] = {'fn':fn,'select':select}

	def slice(self,sn,**kwargs):

		"""
		Interface to the slices dictionary. Handles all necessary inferences.
		Returns a subset of the self.slices dictionary indexed by group names.
		MORE DOCUMENTATION.
		"""

		#---default spotname
		self.cursor = kwargs.get('spot',self.cursor)
		part_name = kwargs.get('part_name',self.cursor[1])
		#---search for the simulation in all spots
		keys_to_sn = [key for key in self.slices.keys() if key[1]==sn and key[0][1]==part_name]
		if len(keys_to_sn)>1: raise Exception('found simulation %s in multiple spots!'%sn)
		elif not keys_to_sn: 
			raise Exception('failed to find slice key for sn "%s" and part "%s". '%(sn,part_name)+
				'this might happen if you are missing that simulation or the "spot" that holds it. '+
				'the cursor is "%s" and the spotname is "%s"'%(self.cursor,self.c))
		unique_key = keys_to_sn[0]
		if unique_key[0] != self.cursor:
			self.cursor = unique_key[0]
			status('moving cursor to %s,%s'%self.cursor,tag='status')
			#---! needs concerted motion of cursor/c
			self.c = self.cursor[0]
		if unique_key not in self.slices: 
			status('could not find slices for %s (is it in the specs file?)'%str(unique_key))
		return self.slices[unique_key]

	def create_slice(self,**kwargs):

		"""
		Create a slice of a trajectory.
		"""
	
		sn = kwargs['sn']
		start = kwargs['start']
		end = kwargs['end']
		skip = kwargs['skip']
		group = kwargs['group']
		slice_name = kwargs['slice_name']
		pbc = kwargs['pbc'] if 'pbc' in kwargs else None
		pbc_suffix = '' if not pbc else '.pbc%s'%pbc
		outkey = '%s.%d-%d-%d.%s%s'%(self.prefixer(sn),start,end,skip,group,pbc_suffix)
		grofile,trajfile = outkey+'.gro',outkey+'.'+self.trajectory_format
		
		#---make the slice only if necessary
		both_there = all([os.path.isfile(self.postdir+fn) for fn in [grofile,trajfile]])
		self.slice(sn,part_name=self.trajectory_format)
		if both_there and slice_name in self.slice(sn) and group in self.slice(sn)[slice_name]: return
		if not both_there or not all([self.confirm_file(self.postdir+fn) for fn in [grofile,trajfile]]):
			status('making slice: %s'%outkey,tag='status')
			#---slice is not there or not confirmed so we make a new one here
			sequence = self.get_timeseries(sn,strict=False)
			traj_toc = self.toc[self.cursor]
			#---assume the tpr part exists
			tpr_toc = self.toc[(self.c,'tpr')]
			try:
				#---! note that we force xtc below and this needs a solution ASAP!
				slice_trajectory(start,end,skip,sequence,outkey,self.postdir,
					tpr_keyfinder=self.keyfinder((self.c,'tpr')),
					traj_keyfinder=self.keyfinder((self.c,self.trajectory_format)),
					group_fn=self.groups[sn][group]['fn'])
			except KeyboardInterrupt: raise Exception('[ERROR] cancelled by user')
			except Exception as e:
				#---the following exception handler allows the code to continue to slice in case
				#---...of faulty data but it produces a large quantity of output including a full 
				#---...traceback to the original exception which also tells you which log files to read
				#---...to diagnose the error. tested on faulty data. note that the calculator continues
				#---...but every time you run "make compute" it will hit the error until you solve it
				exc_type, exc_obj, exc_tb = sys.exc_info()
				fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
				status('%s in %s at line %d'%(str(exc_type),fname,exc_tb.tb_lineno),tag='error')
				status('%s'%e,tag='error')
				import traceback
				status(re.sub('\n','\n[TRACEBACK] ',traceback.format_exc()),tag='traceback')
				status('failed to make slice: '+outkey,tag='error')
				if slice_name not in self.slice(sn): self.slice(sn)[slice_name] = {}
				self.slice(sn)[slice_name][group] = {'start':start,'end':end,'skip':skip,
					'group':group,'pbc':pbc,'verified':False,'filekey':outkey,
					'gro':grofile,self.trajectory_format:trajfile,'missing_frame_percent':100.}
				status('returning from this function but otherwise passing',tag='error')			
				return
		print '[STATUS] checking timestamps of slice: %s'%outkey
		#---slice is made or preexisting and now we validate
		timeseries = self.slice_timeseries(self.postdir+grofile,self.postdir+trajfile)
		import numpy as np
		missing_frame_percent = 1.-len(np.arange(start,end+skip,skip))/float(len(timeseries))
		if len(timeseries)!=len(np.arange(start,end+skip,skip)): verified = False
		else:
			try: verified = all(np.array(timeseries).astype(float)==
				np.arange(start,end+skip,skip).astype(float))
			except: verified = False
		if not verified: status('frame problems in %s'%outkey,tag='warning')
		if slice_name not in self.slice(sn): self.slice(sn)[slice_name] = {}
		self.slice(sn)[slice_name][group] = {'start':start,'end':end,'skip':skip,
			'group':group,'pbc':pbc,'verified':verified,'timeseries':timeseries,'filekey':outkey,
			'gro':grofile,self.trajectory_format:trajfile,'missing_frame_percent':missing_frame_percent}

	def slice_timeseries(self,grofile,trajfile,**kwargs):

		"""
		Get the time series from a trajectory slice.
		The workspace holds very little data that cannot be parsed from specs files.
		However timeseries data for newly-created slices or perhaps even original sources can be large and
		somewhat costly to generate for an entire data set. For that reason we dump these to disk. 
		For now we write the file based on the incoming trajfile name which should refer to new slices in
		the post directory. In the future we may extend this to sourced trajectories in a "spot".
		"""

		timefile = os.path.basename(re.sub('\.(xtc|trr)$','.clock',trajfile))
		diskwrite = kwargs.get('diskwrite',self.write_timeseries_to_disk)
		timefile_exists = os.path.isfile(os.path.join(self.postdir,timefile))
		if timefile_exists and not self.autoreload and diskwrite: 
			status('removing clock file because autoreload=False and diskwrite=True',tag='warning')
			os.remove(timefile)
		if timefile_exists and self.autoreload:
			#---load the clockfile instead of parsing the XTC file
			dat = load(timefile,path=self.postdir)
			timeseries = dat['timeseries']
		else:
			uni = gmxread(*[os.path.abspath(i) for i in [grofile,trajfile]])
			timeseries = [uni.trajectory[fr].time for fr in range(len(uni.trajectory))]
			if diskwrite: 
				store({'timeseries':timeseries},timefile,self.postdir,
					attrs=None,print_types=False,verbose=True)
		return timeseries
			
	###---INTERPRET SPECIFICATIONS

	def load_specs(self,merge_method=None):

		"""
		A central place where we read all specs files.
		Note that this is where we implement a new part of the framework in which all files of a particular
		naming convention are interpreted as specifications and then intelligently merged.
		This feature allows the user and the factory to create new specs without conflicts and without 
		overspecifying how these things will work.
		"""

		import copy
		specs_files = glob.glob('./calcs/specs/meta*yaml')
		allspecs = []
		merge_method = self.merge_method if not merge_method else merge_method
		for fn in specs_files:
			with open(fn) as fp: 
				if (merge_method != 'override_factory' or 
					not re.match('^meta\.factory\.',os.path.basename(fn))):
					allspecs.append(yaml.load(fp.read()))
		#---if we are overriding factory then we change to careful after filtering out the factory
		merge_method = 'careful' if merge_method=='override_factory' else merge_method
		if merge_method=='strict':
			specs = allspecs.pop(0)
			for spec in allspecs:
				for key,val in spec.items():
					if key not in specs: specs[key] = copy.deepcopy(val)
					else: raise Exception('\n[ERROR] redundant key %s in more than one meta file'%key)
		elif merge_method=='careful':
			#---! recurse only ONE level down in case e.g. calculations is defined in two places but there
			#...! ...are no overlaps, then this will merge the dictionaries at the top level
			specs = allspecs.pop(0)
			for spec in allspecs:
				for topkey,topval in spec.items():
					if topkey not in specs: specs[topkey] = copy.deepcopy(topval)
					else: 
						for key,val in topval.items():
							if key not in specs[topkey]: specs[topkey][key] = val
							else: raise Exception(
								('[ERROR] performing careful merge in the top-level specs dictionary "%s" '+
								' but there is already a child key "%s"')%(topkey,key))
		else: raise Exception('\n[ERROR] unclear meta specs merge method %s'%merge_method)
		return specs

	def interpret_specs(self,details,return_stubs=False):

		"""
		The YAML-formatted specifications file must be interpreted if it contains loops.
		"""

		#---this loop interpreter allows for a loop key at any point over specs in list or dict
		#---trim a copy of the specs so all loop keys are terminal
		details_trim = deepcopy(details)
		#---get all paths to a loop
		nonterm_paths = list([tuple(j) for j in set([tuple(i[:i.index('loop')+1]) 
			for i,j in catalog(details_trim) if 'loop' in i[:-1]])])
		#---some loops end in a list instead of a sub-dictionary
		nonterm_paths_list = list([tuple(j) for j in set([tuple(i[:i.index('loop')+1]) 
			for i,j in catalog(details_trim) if i[-1]=='loop'])])
		#---for each non-terminal path we save everything below and replace it with a key
		nonterms = []
		for path in nonterm_paths:
			base = deepcopy(delve(details_trim,*path[:-1]))
			nonterms.append(base['loop'])
			pivot = delve(details_trim,*path[:-1])
			pivot['loop'] = base['loop'].keys()
		#---hypothesize over the reduced specifications dictionary
		sweeps = [{'route':i[:-1],'values':j} for i,j in catalog(details_trim) if 'loop' in i]
		#---! note that you cannot have loops within loops (yet?) but this would be the right place for it
		if sweeps == []: new_calcs = [deepcopy(details)]
		else: new_calcs = hypothesis(sweeps,default=details_trim)
		new_calcs_stubs = deepcopy(new_calcs)
		#---replace non-terminal loop paths with their downstream dictionaries
		for ii,i in enumerate(nonterms):
			for nc in new_calcs:
				downkey = delve(nc,*nonterm_paths[ii][:-1])
				upkey = nonterm_paths[ii][-2]
				point = delve(nc,*nonterm_paths[ii][:-2])
				point[upkey] = nonterms[ii][downkey]
		#---loops over lists (instead of dictionaries) carry along the entire loop which most be removed
		for ii,i in enumerate(nonterm_paths_list):
			for nc in new_calcs: 
				#---! this section is supposed to excise the redundant "loop" list if it still exists
				#---! however the PPI project had calculation metadata that didn't require it so we just try
				try:
					pivot = delve(nc,*i[:-2]) if len(i)>2 else nc
					val = delve(nc,*i[:-1])[i[-2]]
					pivot[i[-2]] = val
				except: pass
		return new_calcs if not return_stubs else (new_calcs,new_calcs_stubs)

	###---DOWNSTREAM DATA AND BOOKKEEPING

	def sns(self,**kwargs):
	
		"""
		Return the simulation keys.
		Note that we previously performed a sort step here but the treeparser does that automatically
		and the toc is stored in OrderedDict
		"""

		cursor = kwargs.get('cursor',self.cursor)
		return self.toc[cursor].keys()

	def collection(self,*args,**kwargs):

		"""
		Return simulation keys from a collection.
		"""

		calcname = kwargs.get('calcname',None)
		if args and calcname: raise Exception('\n[ERROR] self.collection takes either calcname or name')
		elif not calcname:
			return list(unique(flatten([self.vars['collections'][i] for i in args])))
		elif calcname: 
			collections = self.calc[calcname]['collections']
			if type(collections)==str: collections = [collections]
			return list(unique(flatten([self.vars['collections'][i] for i in collections])))
		#---return all simulations for the current cursor, already sorted by the treeparser and ordered dict
		else: return self.sns()

	def select_postdata(self,fn_base,calc,debug=False):
	
		"""
		Search postprocess spec files for a match with a calculation.
		Queries the spec files in order to determine if a calculation has been run already.
		Also used by store.plot_header to identify the correct data to unpack.
		"""

		for specfn in glob.glob(self.postdir+fn_base+'*.spec'):
			with open(specfn,'r') as fp: attrs = json.loads(fp.read())
			if attrs=={} or attrs==calc['specs']: return specfn
			#---if specs are not identical we compare the ones that are and pass if they are equal
			chop = deepcopy(attrs)
			extra_keys = [key for key in chop if key not in calc['specs']]
			for key in extra_keys: del chop[key]
			if calc['specs']==chop: return specfn
		if debug: 
			import pdb;pdb.set_trace() #---legit
		return None

	def collect_times(self,calc,sn,group):
	
		"""
		Collect the timeseries for one or multiple slices in a calculation.
		"""
	
		if type(calc['slice_name'])==str:
			return self.slices[sn][calc['slice_name']]['all' if not group else group]['timeseries']
		else: 
			return concatenate([self.slices[sn][sname]['all' if not group else group]['timeseries']
				for sname in calc['slice_name']])

	def get_post(self,sn,calcname=None,plotname=None,lookup=None):

		"""
		Next-generation postprocessing data lookups.
		Note that this should probably replace portions of code in store.plotload and computer.
		UNDER DEVELOPMENT. Recommend parting out the interpreter function.
		"""

		if calcname and plotname or (not calcname and not plotname):
			raise Exception('\n[ERROR] specify only one (calcname or plotname)')

		#---look up post by calculation name
		#---! this section dripped from store.plotload
		if calcname:

			#---get slice name
			#---! this would fail if we looped over slices
			slice_name = self.calc[calcname]['slice_name']

			#---get the group name
			if 'group' in self.calc[calcname]: group = self.calc[calcname]['group']
			else: group = None

			#---look up the slice
			sl = self.slices[sn][slice_name][group if group else 'all']

			#---base file name according to group conventions
			if not group: 
				fn_base = re.findall('^v[0-9]+\.[0-9]+-[0-9]+-[0-9]+',sl['filekey'])[0]+'.%s'%calcname
			else: fn_base = '%s.%s'%(sl['filekey'],calcname)

			#---see how many there are 
			candidates = glob.glob(self.path('post_data_spot')+fn_base+'*.spec')

			if len(candidates)==1: return re.sub('.spec','.dat',candidates[0])
			else:
				options = {}
				for c in candidates:
					nnum = int(re.findall('^.+\.n([0-9]+)\.spec',c)[0])
					with open(c) as fp: options[c] = eval(fp.read())
				meta = self.load_specs()
				new_calcs = self.interpret_specs(meta['calculations'][calcname])				
				#---use lookup to whittle these calculations
				if lookup:
					index = next(ii for ii,i in enumerate(new_calcs) if 
						all([delve(i,*key)==val for key,val in lookup.items()]))
				else: raise Exception('\n[ERROR] too many options so you need to specify via lookup kwarg')
				specs = new_calcs[index]
				#---driped from interpret function (needs its own function)
				for path,sub in [(i,j) for i,j in catalog(specs) if type(j)==str and re.match('^\+',j)]:
					source = delve(self.vars,*sub.strip('+').split('/'))
					point = delve(specs,*path[:-1])
					point[path[-1]] = source
				#---end drip
				particular = next(key for key,val in options.items() if val==specs['specs'])
				return re.sub('.spec','.dat',particular)

		elif plotname:
			print "[DEVELOPMENT] need to handle plotnames here"
			import pdb;pdb.set_trace() #---legit

	###---WORKPLACE ACTUATOR

	def action(self,calculation_name=None):
	
		"""
		Parse a specifications file to make changes to a workspace.
		This function interprets the specifications and acts on it. 
		It manages the irreducible units of an omnicalc operation and ensures
		that the correct data are sent to analysis functions in the right order.
		"""

		status('parsing specs file',tag='status')

		#---load the yaml specifications file
		specs = self.load_specs()
		#### status('done loading specs',tag='status')		
		
		#---read simulations from the slices dictionary
		sns = specs['slices'].keys()
		#---variables are passed directly to self.vars
		self.vars = deepcopy(specs['variables']) if 'variables' in specs else {}

		#---apply "+"-delimited internal references in the yaml file
		for path,sub in [(i,j[-1]) for i,j in catalog(specs) if type(j)==list 
			and type(j)==str and re.match('^\+',j[-1])]:
			source = delve(self.vars,*sub.strip('+').split('/'))
			point = delve(specs,*path[:-1])
			point[path[-1]][point[path[-1]].index(sub)] = source
		for path,sub in [(i,j) for i,j in catalog(specs) if type(j)==str and re.match('^\+',j)]:
			source = delve(self.vars,*sub.strip('+').split('/'))
			point = delve(specs,*path[:-1])
			point[path[-1]] = source
		
		#---loop over all simulations to create groups and slices
		self.save(quiet=True)
		for route in [('slices',i) for i in sns]:
			root,sn = delve(specs,*route),route[-1]
			#---create groups
			if 'groups' in root:
				for group,select in root['groups'].items():
					kwargs = {'group':group,'select':select,'sn':sn}
					self.create_group(**kwargs)
				root.pop('groups')
			#---slice the trajectory
			if 'slices' in root:
				for sl,details in root['slices'].items(): 
					#---! use a default group here?
					for group in details['groups']:
						kwargs = {'sn':sn,'start':details['start'],
							'end':details['end'],'skip':details['skip'],'slice_name':sl}
						kwargs['group'] = group
						if 'pbc' in details: kwargs['pbc'] = details['pbc']
						self.create_slice(**kwargs)
				root.pop('slices')
			if root != {}: raise Exception('[ERROR] unprocessed specifications %s'%str(root))
			else: del root
		#---we only save after writing all slices. if the slicer fails autoreload will find preexisting files
		self.save(quiet=True)
		checktime()

		#---meta is passed to self.meta
		if 'meta' in specs:
			for sn in specs['meta']:
				self.meta[sn] = specs['meta'][sn]

		#---collections are groups of simulations
		if 'collections' in specs: self.vars['collections'] = specs['collections']

		#---calculations are executed last and organized in this loop
		if 'calculations' in specs:
			status('starting calculations',tag='status')
			#---note that most variables including calc mirror the specs file
			self.calc = dict(specs['calculations'])
			#---infer the correct order for the calculation keys from their upstream dependencies
			upstream_catalog = [i for i,j in catalog(self.calc) if 'upstream' in i]
			#---if there are no specs required to get the upstream data object the user can either 
			#---...use none/None as a placeholder or use the name as the key as in "upstream: name"
			for uu,uc in enumerate(upstream_catalog):
				if uc[-1]=='upstream': upstream_catalog[uu] = upstream_catalog[uu]+[delve(self.calc,*uc)]
			depends = {t[0]:[t[ii+1] for ii,i in enumerate(t) if ii<len(t)-1 and t[ii]=='upstream'] 
				for t in upstream_catalog}
			calckeys = [i for i in self.calc if i not in depends]
			while any(depends):
				ii,i = depends.popitem()
				if all([j in calckeys for j in i]) and i!=[]: calckeys.append(ii)
				else: depends[ii] = i
			#---if a specific calculation name is given then only perform that calculation
			if not calculation_name is None: calckeys = [calculation_name]
			for calcname in calckeys:
				details = specs['calculations'][calcname]
				status('checking calculation %s'%calcname,tag='status')
				new_calcs = self.interpret_specs(details)
				#---perform calculations
				for calc in new_calcs:
					#---find the script with the funtion
					fns = []
					for (dirpath, dirnames, filenames) in os.walk('./'): 
						fns.extend([dirpath+'/'+fn for fn in filenames])
					search = filter(lambda x:re.match('^\.\/[^ate].+\/%s\.py$'%calcname,x),fns)
					if len(search)==0: raise Exception('\n[ERROR] cannot find %s.py'%calcname)
					elif len(search)>1: raise Exception('\n[ERROR] redundant matches: %s'%str(search))
					else:
						sys.path.insert(0,os.path.dirname(search[0]))
						function = unpacker(search[0],calcname)
						status('computing %s'%calcname,tag='loop')
						computer(function,calc=calc,workspace=self)
						self.save()
					checktime()
		self.save()
