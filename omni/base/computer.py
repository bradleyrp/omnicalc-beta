#!/usr/bin/python

from store import store,load
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
	for sn in sns:
		if incoming_type == 'simulation':
			#---prepare combinations in a dictionary
			jobs.append({'sn':sn,'slice_name':slice_name,'group':group,
				'grofile':work.postdir+work.slices[sn][slice_name][group]['gro'],
				'trajfile':work.postdir+work.slices[sn][slice_name][group]['xtc'],})
		else:
			#---if the incoming type is a dictionary we use it to look up an upstream calculation
			if incoming_type == 'post': 
				for key,val in calc['specs']['upstream'].items():
					upspecs = deepcopy(work.calc['lipid_abstractor'])
					options,stubs = work.interpret_specs(upspecs,return_stubs=True)
					whittles = [(i,j) for i,j in catalog(val)]
					#---select the correct option by matching all catalogued routes from the incoming
					#---...key to the original calculation
					select = [options[ss] for r,v in whittles for ss,s in enumerate(stubs) 
						if delve(s['specs'],*r)==v]
					if len(select)!=1: raise Exception('[ERROR] redundant upstream selection %s'%str(select))
					else: specs = select[0]
					#---load the upstream data
					fn_base = work.slices[sn][upspecs['slice_name']][upspecs['group']]['filekey']+'.%s'%key
					fn = work.select_postdata(fn_base,specs)
					data[sn][key] = load(os.path.basename(fn)[:-4]+'dat',work.postdir)
			else: raise Exception("[ERROR] 'data type in' %s not implemented yet"%incoming_type)
			jobs.append({'sn':sn,'slice_name':slice_name,'group':group,'upstream':data[sn].keys()})

	#---master loop
	for outgoing in jobs:
		sn,slice_name,group = outgoing['sn'],outgoing['slice_name'],outgoing['group']
		
		#---we index all calculations automatically in case we loop over specs later
		index,fn_key = -1,''
		if not group:
			fn_base = re.findall('^v[0-9]+\.[0-9]+-[0-9]+-[0-9]+',
				work.slices[sn][slice_name]['all']['filekey'])[0]+'.%s'%function.__name__
		else:
			try: fn_base = work.slices[sn][slice_name][
				'all' if not group else group]['filekey']+'.%s'%function.__name__
			except:
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
					outgoing['upstream'] = dict([(k,data[sn][k]) for k in outgoing['upstream']])
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
				if any(unaccounted): status('some calculation specs were not saved: %s'%
					str(unaccounted),tag='warning')				
				if 'upstream' in unaccounted and 'upstream' not in attrs: 
					status('automatically appending upstream data',tag='status')
					attrs['upstream'] = calc['specs']['upstream']
				store(result,fn,work.postdir,attrs=attrs)
				with open(work.postdir+fn_base+fn_key+'.spec','w') as fp: fp.write(json.dumps(attrs)+'\n')
				#---previously stored lookup logic but this is contained in calcspecs and can be inferred
				work.clear_lookups()

	#---no modifications to work so no save
	return

