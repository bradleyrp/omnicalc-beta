#!/usr/bin/python

from store import store,load,datmerge
from tools import status,asciitree,flatten,unique,catalog,delve
import os,glob,re,json
from copy import deepcopy
import yaml

def computer(function,**kwargs):

	"""
	Compute function figures out how to run a calculation over a simulation.
	"""

	dry = kwargs['dry'] if 'dry' in kwargs else False
	work = kwargs['workspace']
	calc = kwargs['calc']
	
	#---perform a calculation over all collections
	if 'collections' in calc: 
		cols = tuple([calc['collections']]) if type(calc['collections'])==str else calc['collections']
		sns = unique(flatten([work.vars['collections'][i] for i in cols]))
	else: sns = work.sns()
	
	#---get slices (required)
	slice_name = calc['slice_name']
	group = calc['group'] if 'group' in calc else None
	
	#---pass data to the function according to upstream data type
	incoming_type = calc['uptype']
	jobs,data = [],dict([(sn,{}) for sn in sns])
	combined_slices = []
	for sn in sns:
		new_job = {'sn':sn,'slice_name':slice_name,'group':group}
		if incoming_type == 'simulation':
			#---prepare combinations in a dictionary
			if slice_name not in work.slices[sn]:
				raise Exception('\n[ERROR] the slices yaml file is missing a slice named "%s" for simulation "%s"'%
					(slice_name,sn))
			if work.slices[sn][slice_name][group]['missing_frame_percent']>work.missing_frame_tolerance:
				status('upstream slice failure: %s,%s,%s'%(sn,slice_name,group),tag='warning')
				continue
			new_job['grofile'] = work.postdir+work.slices[sn][slice_name][group]['gro']
			new_job['trajfile'] = work.postdir+work.slices[sn][slice_name][group]['xtc']
		if 'specs' not in calc: calc['specs'] = ''
		if 'upstream' in calc['specs']:
			#---if no loop on upstream you can use a list
			if type(calc['specs']['upstream'])==list: 
				upstream_ask = dict([(key,None) for key in calc['specs']['upstream']])
			elif type(calc['specs']['upstream'])==str: 
				upstream_ask = {calc['specs']['upstream']:None}
			else: upstream_ask = calc['specs']['upstream']
			for key,val in upstream_ask.items():
				upspecs = deepcopy(work.calc[key])
				#---identify the list of particular options along with the stubs
				options,stubs = work.interpret_specs(upspecs,return_stubs=True)
				#---identify paths and values over which we "whittle" the total list of specs
				whittles = [(i,j) for i,j in catalog(val)]
				#---if no loop on upstream pickles we interpret none and send blank specs
				if val in ['None','none',None]: 
					specs = [options[ss] for r,v in whittles for ss,s in enumerate(stubs)]
				else:
					#---select the correct option by matching all catalogued routes from the incoming
					#---...key to the original calculation
					specs = [options[ss] for r,v in whittles for ss,s in enumerate(stubs) 
						if delve(s['specs'],*r)==v]
				if len(specs)!=1 and 'loop' not in upspecs['slice_name']: 
					raise Exception('[ERROR] redundant upstream selection %s'%str(select))
				#---if there are multiple slices
				#---! note that we expect that if slice_names is a list it will be ordered here too
				for slicenum,spec in enumerate(specs):
					#---if the upstream calculation has a group then use it in the filename
					if not group:
						if 'group' in work.calc[key]: upgroup = work.calc[key]['group']
						else: upgroup = None
					else: upgroup = group
					if not upgroup: 
						sl = work.slices[sn][spec['slice_name']]
						fn_base = re.findall('^v[0-9]+\.[0-9]+-[0-9]+-[0-9]+',
							work.slices[sn][upspecs['slice_name']]['all']['filekey']
							)[0]+'.%s'%key
					else: 
						sl = work.slices[sn][spec['slice_name']][upgroup]
						fn_base = '%s.%s'%(sl['filekey'],key)
					#---! moved the following block left recently
					fn = work.select_postdata(fn_base,spec)
					if not fn: 
						import pdb;pdb.set_trace()
						raise Exception('[ERROR] missing %s'%fn)
					outkey = key if len(specs)==1 else '%s%d'%(key,slicenum)
					#---before each calculation the master loop loads the filename stored here
					data[sn][outkey] = os.path.basename(fn)[:-4]+'dat'
			new_job['upstream'] = data[sn].keys()
		jobs.append(new_job)
	
	#---master loop
	for outgoing in jobs:
		sn,slice_name,group = outgoing['sn'],outgoing['slice_name'],outgoing['group']
		
		#---if we combine slices for this calculation we use the whole time span in the base filename
		if type(slice_name)==list:
			#---! simple method for making the combination file key
			start = min([work.slices[sn][s]['all' if not group else group]['start'] for s in slice_name])
			end = max([work.slices[sn][s]['all' if not group else group]['end'] for s in slice_name])
			skip = work.slices[sn][s]['all' if not group else group]['skip']
			#---! this filekey construction means the user will have to anticipate the names of combos
			fn_base = 'v%s.%d-%d-%d.%s'%(work.shortname(sn),start,end,skip,function.__name__)
		else:
			#---we index all calculations automatically in case we loop over specs later
			index,fn_key = -1,''
			if not group:
				fn_base = re.findall('^v[0-9]+\.[0-9]+-[0-9]+-[0-9]+',
					work.slices[sn][slice_name][
					'all' if not group else group]['filekey'])[0]+'.%s'%function.__name__
			else:
				try: fn_base = work.slices[sn][slice_name][
					'all' if not group else group]['filekey']+'.%s'%function.__name__
				except:
					print "no group and cannot get base filename"
					import pdb;pdb.set_trace()
		prev = glob.glob(work.postdir+fn_base+'*.dat')
		if prev == []: index = 0
		else: index = max(map(lambda x:int(re.findall('^.+\/%s\.n([0-9]+)\.dat'%fn_base,x)[0]),prev))+1
		fn_key = '.n%d'%index
		fn = fn_base+fn_key+'.dat'
		#---safety check for file errors to prevent overwriting however this should be handled by indices
		if os.path.isfile(work.postdir+fn): raise Exception('[ERROR] %s exists'%(work.postdir+fn))
		
		#---check for specs file with the exact same specifications
		exists = True if index != -1 and work.select_postdata(fn_base,calc) != None else False
		if not exists:

			status("%s %s"%(function.__name__,str(outgoing)),tag='compute')
			if not dry:

				outgoing['workspace'] = work
				outgoing['calc'] = calc
				if 'upstream' in outgoing:
					sn = outgoing['sn']
					outgoing['upstream'] = dict([(k,
						load(data[sn][k],work.postdir)) for k in outgoing['upstream']])
				result,attrs = function(**outgoing)
				"""
				spec files are carefully constructed
				they prevent redundant calculations
				they allow us to loop over many parameters while saving files with a single index
				the calculation dictionary in the specs file contains meta-parameters for looping
				we are careful not to save meta parameters to the spec file
				we only save parameters which are relevant to the calculation itself
				the calculation dictionary in the spec file must therefore separate these parameters
				in a sub-dictionary called 'specs'
				we prefer attrs to be small and specific
				since attrs is also used to uniquely specify the data
				all big data should be stored as a result via numpy
				"""
				#---if any calculation specifications are not in attributes we warn the user here
				if 'specs' in calc: unaccounted = [i for i in calc['specs'] if i not in attrs]
				else: unaccounted = []
				if 'upstream' in unaccounted and 'upstream' not in attrs: 
					status('automatically appending upstream data',tag='status')
					unaccounted.remove('upstream')
					attrs['upstream'] = calc['specs']['upstream']
				if any(unaccounted):
					status('some calculation specs were not saved: %s'%
						str(unaccounted),tag='warning')
					print '[ERROR] a calculation spec was not added to the attributes and '+\
						'hence these data will not be found by plotloader later on. '+\
						'Add the specs to attrs in your calculation function to continue.'
					import pdb;pdb.set_trace()
				store(result,fn,work.postdir,attrs=attrs)
				with open(work.postdir+fn_base+fn_key+'.spec','w') as fp: fp.write(json.dumps(attrs)+'\n')
				#---previously stored lookup logic but this is contained in calcspecs and can be inferred
				work.clear_lookups()

	#---no modifications to work so no save
	return
