#!/usr/bin/python

import sys,os,re,time
import yaml
import pickle,json,copy,glob
from constants import conf_paths,conf_gromacs
from base.tools import unpacker,path_expand,status,argsort,unescape,tupleflat
from base.tools import delve,asciitree,catalog,status,unique,flatten
from base.gromacs_interface import edrcheck,slice_trajectory,machine_name
from base.hypothesis import hypothesis
from base.computer import computer
from base.timer import checktime
from base.store import picturefind
from copy import deepcopy
import MDAnalysis

#---joblib and multiprocessing modules require all functions to be registered in __main__
for fn in glob.glob('calcs/codes/*.py'): execfile(fn)

#---CLASS
#-------------------------------------------------------------------------------------------------------------

class Workspace():

	"""
	Wrapper for a workspace object that organizes all simulation data and postprocess.
	Note that the variable name "toc" is used throughout and refers to a table of contents.
	"""

	#---presets
	conf_paths = conf_paths
	conf_gromacs = conf_gromacs
	
	def __init__(self,fn,previous=False,autoreload=False):

		#---load workspace if it  exists
		self.filename = path_expand(fn)
		#---! paths and machine can change?
		self.paths = unpacker(conf_paths,'paths')
		self.parse_specs = unpacker(conf_paths,'parse_specs')
		self.machine = unpacker(conf_gromacs,'machine_configuration')[machine_name]
		self.nprocs = self.machine['nprocs']
		self.rootdir = os.path.join(path_expand(self.paths['data_spots'][0]),'')
		self.postdir = os.path.join(path_expand(self.paths['post_data_spot']),'')
		self.plotdir = os.path.join(path_expand(self.paths['post_plot_spot']),'')
		#---generic variables associated with the workspace
		self.vars = {}
		self.meta = {}
		self.calc = {}
		#---automatically add preexisting files to the workspace if they are found
		self.autoreload = autoreload
		#---remember logic for substitutions in YAML specifications files
		self.lookups = []
		#---open self if the filename exists
		if os.path.isfile(self.filename): 
			self.load(previous=previous)
			self.verify()
		#---otherwise make a new workspace
		else: self.bootstrap()

	def load(self,previous=False):

		"""
		Unpack a saved pickle into self.
		"""

		incoming = pickle.load(open(self.filename,'rb'))
		self.toc = incoming.toc
		self.datahead = incoming.datahead
		self.shortname_regex = incoming.shortname_regex
		self.post = incoming.post
		self.groups = incoming.groups
		self.slices = incoming.slices
		self.xtc_files = incoming.xtc_files
		self.edr_times = incoming.edr_times
		self.vars = incoming.vars
		self.meta = incoming.meta
		self.calc = incoming.calc
		for key in [key for key in incoming.__dict__ if re.match('^toc_',key)]:
			setattr(self,key,incoming.__dict__[key])
		if previous: self.previous = incoming
			
	def save(self,quiet=False):

		"""
		Write the class to a pickle.
		Consider another format which is more ordered.
		"""

		import time
		from threading import Thread
		if not quiet: status('saving',tag='work')
		th = Thread(target=pickle.dump(self,open(self.filename,'wb')));th.start();th.join()
		if not quiet: status('done saving',tag='work')

	def bootstrap(self):

		#---bootstrapping the paths.py file will also make the directory
		if not os.path.isdir(self.postdir): os.mkdir(self.postdir)
		if not os.path.isdir(self.plotdir): os.mkdir(self.plotdir)
		if len(self.paths['data_spots'])>1:
			print '[WARNING] only one data spot is allowed so ignoring the rest'
		
		#---the datahead lists different "parsings" of the root data
		#---the keys in datahead will become objects of the self
		self.datahead = dict([(name,{'regex':self.parse_specs[name]}) for name in self.parse_specs
			if re.match('^toc',name)])
		if 'shortname' in self.parse_specs: self.shortname_regex = self.parse_specs['shortname']
		
		#---prepare and save regex which sets rules for parsing files
		for toc in self.datahead: self.get_regex_groups(toc)
		
		#---ignore other tocs for now
		if 'toc' not in self.datahead: raise Exception("[ERROR] need a 'toc' inside parse_specs")
		
		#---parse the tree for the primary toc
		self.treeparser('toc')
		self.treeparser('toc_structures',sort=False)
		self.treeparser_xtc_edr('toc')

		#---data are stored in dictionaries by simulation name
		self.post = dict([(sn,{}) for sn in self.toc.keys()])
		self.groups = dict([(sn,{}) for sn in self.toc.keys()])
		self.slices = dict([(sn,{}) for sn in self.toc.keys()])
		self.save()

	def verify(self,scrub=False):

		"""
		Check the post-processing filenames to make sure they are present.
		"""

		missing_files = []
		checks = []
		#---group files
		checks += [(('groups',sn,group),val[group]['fn']) for sn,val in self.groups.items() for group in val]
		checks += [sl[name][key] for sn,sl in self.slices.items() 
			for name in sl for key in ['gro','xtc']	if key in sl[name]]
		for route,fn in checks:
			if not os.path.isfile(self.postdir+fn): missing_files.append([route,fn])
		if missing_files != [] and not scrub: status('missing files: %s'%str(missing_files),tag='warning')
		elif missing_files != []:
			status('scrubbing deleted files from the workspace: %s'%str(missing_files),tag='warning')
			for route,fn in missing_files:
				del delve(self.__dict__,*route[:-1])[route[-1]]
		else: print '[STATUS] verified'

	#---UTILITIES
	
	def sns(self):
	
		"""
		Return sorted simulation keys.
		"""
		
		try: keys = [self.toc.keys()[j] for j in 
			argsort(map(lambda x:int(re.findall('^.+-v([0-9]+)',x)[0]),self.toc.keys()))]
		except: keys = self.toc.keys()
		return keys

	def shortname(self,sn):

		"""
		If a 'shortname' key is placed in parse_specs then we can use this rule to shorten the name of 
		simulations when writing files associated with them.
		"""

		return re.findall(self.shortname_regex,sn)[0]

	def key_recon(self,toc='toc'):
	
		"""
		Returns a function which reconstitutes a set of keys from the atomized ones.
		"""
	
		cumsum = lambda x: [sum(x[:i]) for i in range(len(x)+1)]
		chunk = lambda ulist,step: map(lambda i: ulist[i:i+step],xrange(0,len(ulist),step))
		inds = chunk([int(cumsum(self.datahead[toc]['counts'])[i])
			for i in map(lambda x:int(x/2.),range((len(self.datahead[toc]['counts'])+1)*2))[1:-1]],2)
		return lambda t: tuple([unescape(self.datahead[toc]['write'][xx]%tuple(t[slice(x[0],x[1])])) 
			for xx,x in enumerate(inds)])

	def fullpath(self,*key,**kwargs):

		"""
		Generates a full path relative to the root from the standard regex keys.
		"""

		if any([type(i)!=tuple for i in key]): key = tupleflat(key)
		path = '/'.join(self.key_recon(**kwargs)(key))
		return path

	def lookup(self,*args,**kwargs):

		"""
		Perform a lookup with variable substitutions
		NOTE THAT THIS SCHEME LETS SPECS FILES BECOME SELF-REFERENTIAL
		"""
		
		logic = ''
		result = delve(self.__dict__,*args)
		#---if the result is a leaf node but can be found in self.vars we continue to substitute
		if args[-1] in self.vars:
			over = delve(self.vars,args[-1])
			if result.__hash__ != None and result in over: 
				logic += '>'+str(result)
				result = over[result]
		#---if the result is not a leaf node we try to traverse further down the tree
		if type(result)==dict:
			#---we use the simulation name to check the meta dictionary values for a descriptor
			if 'sn' in kwargs:
				match_meta = [i for i in self.meta[kwargs['sn']].values() if i in result]
				#---search for values in the meta dictionary for a particular simulation to traverse
				if len(match_meta)==1:
					result = result[match_meta[0]] 
					logic += '>'+str(match_meta[0])
		summary = {'args':args,'logic':logic}
		if kwargs != {}: summary['kwargs'] = kwargs
		self.lookups.append(summary)
		return result

	def clear_lookups(self): self.lookups = []

	#---MDAnalysis 

	def gmxread(self,grofile,trajfile=None):

		"""
		Read a simulation trajectory
		"""

		import MDAnalysis
		if trajfile == None: uni = MDAnalysis.Universe(grofile)
		else: uni = MDAnalysis.Universe(grofile,trajfile)
		return uni
	
	def mdasel(self,uni,select): 

		"""
		Make a selection in MDAnalysis regardless of version.
		"""

		if hasattr(uni,'select_atoms'): return uni.select_atoms(select)
		else: return uni.selectAtoms(select)
	
	def get_regex_groups(self,toc):
	
		"""
		Given a regex definition for parsing files we extract some rules for later.
		"""
		
		regex = self.datahead[toc]['regex']
		regex_groups = []
		for count,r in enumerate(regex):
			regex_backwards = str(r)
			for key in re.findall('(\([^\)]+\))',r):
				regex_backwards = re.sub(re.escape(key),'%s',regex_backwards)
			regex_groups.append([regex_backwards.count('%s'),regex_backwards])
		self.datahead[toc]['counts'],self.datahead[toc]['write'] = zip(*regex_groups)
		
	#---DATASET PARSER
			
	def treeparser(self,tocname,sort=True):
	
		"""
		For a particular table-of-contents specification, parse the root directory.
		"""
		
		regexs = regex_top,regex_sub,regex_fn = self.datahead[tocname]['regex']
		regex = '^%s\/'%re.escape(
			self.rootdir if self.rootdir[-1]!='/' else self.rootdir[:-1]
			)+'\/'.join([regex_top,regex_sub,regex_fn])+'$'
		#---parse all files under the root
		fns = []
		for (dirpath, dirnames, filenames) in os.walk(self.rootdir):
			fns.extend([dirpath+'/'+fn for fn in filenames])			
		#---collect matching files
		reassemble = self.key_recon(tocname)
		matches = [reassemble(re.findall(regex,fn)[0]) for fn in fns if re.match(regex,fn)]
		if matches == []: raise Exception('[ERROR] failed to find matches')
		#---toc is a nested dictionary of the available top directories and subdirectories
		newtoc = dict([(s,
			dict([(re.findall(regex_sub,t)[0],[]) for t in 
				set([x[1] for x in matches if x[0]==s])
				if re.match(regex_sub,t)])
			) for s in set(zip(*matches)[0])])
		#---load the filenames
		for dn,sub,fn in matches:
			if (re.match(regex_sub,sub) and
				re.match('^%s$'%regex_fn,fn)):
				newtoc[dn][re.findall(regex_sub,sub)[0]].append(fn)
		#---sort by number if there is one integer regex group in the filename regex
		if sort:
			for sn in newtoc.keys():
				for sub in newtoc[sn].keys():
					parts = list(newtoc[sn][sub])
					newtoc[sn][sub] = [re.findall(self.datahead[tocname]['regex'][2],parts[j])[0]
						for j in argsort([int(re.findall(self.datahead[tocname]['regex'][2],i)[0]) 
						for i in parts])]
		else: 
			for sn in newtoc.keys():
				for sub in newtoc[sn].keys():
					parts = list(newtoc[sn][sub])
					newtoc[sn][sub] = [re.findall(self.datahead[tocname]['regex'][2],p)[0] for p in parts]
		setattr(self,tocname,newtoc)
		
	def treeparser_xtc_edr(self,tocname):
	
		"""
		compile the toc into a list with full file names for time testing
		"""
	
		toc = self.__dict__[tocname]
		fns = []
		for sn in toc.keys():
			for sub in toc[sn].keys():
				for fn in toc[sn][sub]: 
					fns.append(self.fullpath(sn,sub,fn))
		self.xtc_files = fns
		edr_times = []
		for ii,fn in enumerate(fns):
			status('scanning EDR files',i=ii,looplen=len(fns),tag='scan')
			edr_times.append([float(i) if i!=None else i for i in edrcheck(self.rootdir+fn)])
		self.edr_times = edr_times
		
	def get_last_start_structure(self,sn,tocname='toc_structures'):
	
		"""
		A function which identifies an original structure for reference.
		"""
		
		top = self.toc_structures[sn]
		last_subdir = top.keys()[argsort([int(key[1]) for key in top])[-1]]
		#---! select the first item in the list
		struct = (sn,last_subdir,top[last_subdir][0])
		return self.rootdir+self.fullpath(*struct,toc='toc_structures')

	def sort_steps(self,sn,letters='su'):

		"""
		Sort the subdirectory steps by the first group and then the second group which must be an integer.
		"""

		root = self.toc[sn]
		ordered = {}
		for letter in list(set(zip(*root.keys())[0])):
			keys = [k for k in root if k[0]==letter]
			ordered[letter] = [keys[j] for j in argsort(map(lambda y:int(y),zip(*keys)[1]))]
		if letter in [None,'']: return ordered
		else: return [j for k in 
			[ordered[i] for i in ordered if re.match('^(%s)'%('|'.join(letters)),i)]
			for j in k]
			
	def picture(self,plotname,meta=None):
	
		"""
		Call picturefind with the plot directory from this workspace.
		"""
		
		return picturefind('fig.%s'%plotname,directory=self.paths['post_plot_spot'],meta=meta)

	#---POSTPROCESSING SIMULATIONS

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
			#---! later allow a file deletion if the user says the file is invalid			

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
			import pdb;pdb.set_trace()
		return None

	def collection(self,*args):

		"""
		Return simulation keys from a collection.
		"""

		return unique(flatten([self.vars['collections'][i] for i in args]))

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
		#---for each non-terminal path we save everything below and replace it with a key
		nonterms = []
		for path in nonterm_paths:
			base = deepcopy(delve(details_trim,*path[:-1]))
			nonterms.append(base['loop'])
			pivot = delve(details_trim,*path[:-1])
			pivot['loop'] = base['loop'].keys()
		#---hypothesize over the reduced specifications dictionary
		sweeps = [{'route':i[:-1],'values':j} for i,j in catalog(details_trim) if 'loop' in i]
		if sweeps == []: new_calcs = [deepcopy(details)]
		else: new_calcs = hypothesis(sweeps,default=details_trim)
		new_calcs_stubs = deepcopy(new_calcs)
		#---replace non-terminal loop paths with their downstream dictionaries
		for ii,i in enumerate(nonterms):
			for nc in new_calcs:
				downkey = downkey = delve(nc,*nonterm_paths[ii][:-1])
				upkey = nonterm_paths[ii][-2]
				point = delve(nc,*nonterm_paths[ii][:-2])
				point[upkey] = nonterms[ii][downkey]
		return new_calcs if not return_stubs else (new_calcs,new_calcs_stubs)

	#---CREATE GROUPS
		
	def create_group(self,**kwargs):
	
		"""
		Create a group.
		"""

		sn = kwargs['sn']
		name = kwargs['group']
		select = kwargs['select']
		cols = 100 if 'cols' not in kwargs else kwargs['cols']
		simkey = 'v%s.%s'%(self.shortname(sn),name)
		fn = '%s.ndx'%simkey

		#---see if we need to make this group
		if os.path.isfile(self.postdir+fn) and name in self.groups[sn]: return
		elif os.path.isfile(self.postdir+fn):
			if self.confirm_file(self.postdir+fn):
				self.groups[sn][name] = {'fn':fn,'select':select}
			return

		status('creating group %s'%simkey,tag='status')
		if 'dry' in kwargs and kwargs['dry']: return
		#---read the structure
		uni = self.gmxread(self.get_last_start_structure(sn))
		sel = self.mdasel(uni,select)
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

	#---CREATE SLICES
	
	def slice_timeseries(self,grofile,trajfile):

		"""
		Get the time series from a trajectory slice.
		"""

		uni = self.gmxread(*[os.path.abspath(i) for i in [grofile,trajfile]])
		timeseries = [uni.trajectory[fr].time for fr in range(len(uni.trajectory))]
		return timeseries

	def get_timeseq(self,sn,strict=False):

		"""
		One common task is to look up EDR times for a particular simulation.
		"""

		subs = self.sort_steps(sn)
		seq_key_fn = [((sn,sub,fn),self.fullpath(sn,sub,fn)) for sub in subs for fn in self.toc[sn][sub]]
		seq_time_fn = [(self.edr_times[self.xtc_files.index(fn)],key) for key,fn in seq_key_fn
			if not strict or (None not in self.edr_times[self.xtc_files.index(fn)])]
		return seq_time_fn

	def create_slice(self,**kwargs):

		"""
		Create a skice of a trajectory.
		"""
	
		dry = kwargs['dry'] if 'dry' in kwargs else False
		sn = kwargs['sn']
		start = kwargs['start']
		end = kwargs['end']
		skip = kwargs['skip']
		group = kwargs['group']
		slice_name = kwargs['slice_name']
		pbc = kwargs['pbc'] if 'pbc' in kwargs else None
		outkey = 'v%s.%d-%d-%d.%s%s'%(self.shortname(sn),start,end,skip,
			group,'' if pbc==None else '.pbc%s'%pbc)
		grofile,trajfile = outkey+'.gro',outkey+'.xtc'
		both_there = all([os.path.isfile(self.postdir+fn) for fn in [grofile,trajfile]])
		if both_there and slice_name in self.slices[sn] and group in self.slices[sn][slice_name]: return
		if not both_there or not all([self.confirm_file(self.postdir+fn) for fn in [grofile,trajfile]]):
			status('making slice: %s'%outkey,tag='status')
			if not dry:
				#---slice is not there or not confirmed so we make a new one here
				seq_time_fn = self.get_timeseq(sn,strict=False)
				slice_trajectory(start,end,skip,seq_time_fn,
					groupfn=self.postdir+self.groups[sn][group]['fn'],outkey=outkey,pbc=pbc,
					path=self.fullpath,rootdir=self.rootdir,postdir=self.postdir)
		print '[STATUS] checking timestamps of slice: %s'%outkey
		#---slice is made or preexisting and now we validate
		timeseries = self.slice_timeseries(self.postdir+grofile,self.postdir+trajfile)
		import numpy as np
		if len(timeseries)!=len(np.arange(start,end+skip,skip)): verified = False
		else:
			try: verified = all(np.array(timeseries).astype(float)==
				np.arange(start,end+skip,skip).astype(float))
			except: verified = False
		if not verified: status('frame problems in %s'%outkey,tag='warning')
		if slice_name not in self.slices[sn]: self.slices[sn][slice_name] = {}
		self.slices[sn][slice_name][group] = {'start':start,'end':end,'skip':skip,
			'group':group,'pbc':pbc,'verified':verified,'timeseries':timeseries,'filekey':outkey,
			'gro':grofile,'xtc':trajfile}
			
	#---READ SPECIFICATIONS FILES

	def action(self,calculation_name=None,spec_fn='specs.yaml',dry=False):
	
		"""
		Parse a specifications file to make changes to a workspace.
		"""

		status('parsing specs file',tag='status')
		#---load the yaml specifications file
		with open(spec_fn,'r') as fp: raw_specs = fp.read()
		specs = yaml.load(raw_specs)
		if not specs: raise Exception('\n[ERROR] specs file at %s appears to be empty'%
			self.paths['specs_file'])
		#---either simulations are placed at the root of the YAML file or in the slices dictionary
		sns = [key for key in specs if re.match(self.datahead['toc']['regex'][0],key)]
		if 'slices' in specs:
			sns += [('slices',key) for key in specs['slices'] 
				if re.match(self.datahead['toc']['regex'][0],key)]

		#---variables are passed to self.vars
		if 'variables' in specs:
			for key,val in specs['variables'].items(): self.vars[key] = val
		
		#---replace all terminal nodes with a self-reference
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
		for route in sns:
			root,sn = delve(specs,*route),route[-1]

			#---create groups
			if 'groups' in root:
				for group,select in root['groups'].items():
					kwargs = {'group':group,'select':select,'sn':sn}
					if dry: kwargs['dry'] = True
					self.create_group(**kwargs)
					self.save(quiet=True)
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
						if dry: kwargs['dry'] = True
						self.create_slice(**kwargs)
						self.save(quiet=True)
				root.pop('slices')
			if root != {}: raise Exception('[ERROR] unprocessed specifications %s'%str(root))
			else: del root
		checktime()

		#---meta is passed to self.meta
		if 'meta' in specs:
			for sn in specs['meta']:
				self.meta[sn] = specs['meta'][sn]

		#---collections are groups of simulations
		if 'collections' in specs: self.vars['collections'] = specs['collections']
		#---calculations are executed last
		if 'calculations' in specs:
			status('starting calculations',tag='status')
			#---note that most variables including calc mirror the specs file
			self.calc = dict(specs['calculations'])
			#---infer the correct order for the calculation keys from their upstream dependencies
			depends = {t[0]:[t[ii+1] for ii,i in enumerate(t) if ii<len(t)-1 and t[ii]=='upstream'] for t in [i for i,j in catalog(self.calc) if 'upstream' in i]}
			calckeys = [i for i in self.calc if i not in depends]
			"""
			depends_keys = depends.keys()
			while any(depends_keys):
				ii = depends_keys.pop(0)
				i = depends[ii]
				if all([j in calckeys for j in i]) and i!=[]: 
					calckeys.append(ii)
					depends.pop(ii)
				else: depends_keys.append(ii)
				print depends_keys
			"""
			while any(depends):
				ii,i = depends.popitem()
				if all([j in calckeys for j in i]) and i!=[]: calckeys.append(ii)
				else: depends[ii] = i
			#---if a specific calculation name is given then only perform that calculation
			if not calculation_name is None: calckeys = [calculation_name]
			for calcname in calckeys:
				details = specs['calculations'][calcname]
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
						computer(function,calc=calc,workspace=self,dry=dry)
						self.save()
					checktime()
		self.save()
