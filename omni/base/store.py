#!/usr/bin/python

import os,json,glob,re
import h5py,numpy,yaml
from tools import status,flatten,delve,catalog
from copy import deepcopy
import matplotlib as mpl 
import matplotlib.pyplot as plt
from PIL import Image
from PIL import PngImagePlugin

def store(obj,name,path,attrs=None,print_types=False,verbose=True):

	"""
	Use h5py to store a dictionary of data.
	"""

	if type(obj) != dict: raise Exception('except: only dictionaries can be stored')
	if os.path.isfile(path+'/'+name): raise Exception('except: file already exists: '+path+'/'+name)
	path = os.path.abspath(os.path.expanduser(path))
	if not os.path.isdir(path): os.mkdir(path)
	fobj = h5py.File(path+'/'+name,'w')
	for key in obj.keys(): 
		if print_types: 
			print '[WRITING] '+key+' type='+str(type(obj[key]))
			print '[WRITING] '+key+' dtype='+str(obj[key].dtype)
		try: dset = fobj.create_dataset(key,data=obj[key])
		except: raise Exception("failed to write this object so it's probably not numpy"+
			"\n"+key+' type='+str(type(obj[key]))+' dtype='+str(obj[key].dtype))
	if attrs != None: fobj.create_dataset('meta',data=numpy.string_(json.dumps(attrs)))
	if verbose: status('[WRITING] '+path+'/'+name)
	fobj.close()

def load(name,path,verbose=False,filename=False,exclude_slice_source=False):

	"""
	Load an h5py datastore.
	"""

	path = os.path.abspath(os.path.expanduser(path))
	if not os.path.isfile(path+'/'+name): 
		raise Exception('[ERROR] failed to load '+path+'/'+name)
	data = {}
	rawdat = h5py.File(path+'/'+name,'r')
	for key in [i for i in rawdat if i!='meta']: 
		if verbose:
			print '[READ] '+key
			print '[READ] object = '+str(rawdat[key])
		data[key] = numpy.array(rawdat[key])
	if 'meta' in rawdat: attrs = json.loads(rawdat['meta'].value)
	else: 
		print '[WARNING] no meta in this pickle'
		attrs = {}
	if exclude_slice_source:
		for key in ['grofile','trajfile']:
			if key in attrs: del attrs[key]
	for key in attrs: data[key] = attrs[key]
	if filename: data['filename'] = path+'/'+name
	rawdat.close()
	return data
	
def plotload(plotname,work,specfile=None,choice_override=None):

	"""
	Load postprocessing data for making a plot.
	Note that we currently do not use the specs items.
	"""

	#---read plot specification
	if not specfile: specfile = work.paths['specs_file']
	with open(specfile,'r') as fp:
		plotspecs = yaml.load(fp.read())['plots'][plotname]
	
	#---load the calculation from the workspace
	calcnames = plotspecs['calculation']
	status('update work.calc with "make compute dry" if it is out of date',tag='warning')

	if type(calcnames)==str: calcnames = [calcnames]
	datasets = {name:[] for name in calcnames}
	calcsets = {name:[] for name in calcnames}
	
	#---loop over calcnames requested in the plot specs
	for calcname in calcnames:
		
		calcs = work.interpret_specs(work.calc[calcname])
		if len(calcs)==0: raise Exception('[ERROR] failed to retrieve calculations')
	
		#---get the group from either plotspecs or the calculation or exception
		if 'group' in plotspecs: group = plotspecs['group']
		elif 'group' in work.calc[calcname]: group = work.calc[calcname]['group']
		else: group = None
		#---get the collection from either plotspecs or the upstream calculation
		if 'collections' in plotspecs: collections = plotspecs['collections']
		else: collections = calc['collections']
		sns = flatten([work.vars['collections'][c] for c in collections])

		#---compile all upstream data
		data = [{} for c in calcs]
	
		#---iterate over the loop over upstream calculations
		for calcnum,calcwhittle in enumerate(calcs):

			status('upstream data type: %s'%str(calcwhittle),tag='load')
			calc = deepcopy(work.calc[calcname])
			#---loop over simulations 
			for snum,sn in enumerate(sns):
				status(sn,tag='load',i=snum,looplen=len(sns))
				#---assume slices in plotspecs
				if 'slices' in plotspecs: sl = work.slices[sn][plotspecs['slices']][
					'all' if not group else group]
				else: raise Exception('[ERROR] cannot infer slices')
				#---compute base filename
				if not group: 
					fn_base = re.findall('^v[0-9]+\.[0-9]+-[0-9]+-[0-9]+',sl['filekey'])[0]+'.%s'%calcname
				else: fn_base = '%s.%s'%(sl['filekey'],calcname)
				#---fill in upstream details in our replicate of the calculation specs
				for route,val in [(i,j) for i,j in catalog(calcwhittle)]:
					endpoint = delve(work.calc[calcname],*route)
					if type(endpoint)==dict and 'loop' in endpoint: 
						penultimate = delve(calc,*route[:-1])
						penultimate[route[-1]] = val
				#---get the dat file and package it
				fn = work.select_postdata(fn_base,calc,debug=True)
				if fn == None: 
					print '[ERROR] cannot locate a file necessary for plotting'
					import pdb;pdb.set_trace()
				dat_fn = os.path.basename(fn)[:-4]+'dat'
				data[calcnum][sn] = {'data':load(dat_fn,work.postdir),
					'slice':sl,'group':group,'fn_base':fn_base}
		#---if only one calculation of this type then we elevate package
		if len(calcs)==1: calcs,data = calcs[0],data[0]
		datasets[calcname],calcsets[calcname] = data,calcs
	#---if only one upstream calculation we return that directly
	if len(datasets)==1: return datasets.values()[0],calcsets.values()[0]
	else: return datasets,calcsets

def picturesave(savename,directory='./',meta=None,extras=[],backup=False,
	dpi=300,form='png',version=False):

	"""
	Function which saves the global matplotlib figure without overwriting.
	"""

	status('saving picture',tag='store')
	#---if version then we choose savename based on the next available index
	if version:
		#---check for this meta
		search = picturefind(savename,directory=directory,meta=meta)
		if not search:
			if meta == None: raise Exception('[ERROR] versioned image saving requires meta')
			fns = glob.glob(directory+'/'+savename+'*')
			nums = [int(re.findall('^.+\.v([0-9]+)\.png',fn)[0]) for fn in fns 
				if re.match('^.+\.v[0-9]+\.png',fn)]
			ind = max(nums)+1 if nums != [] else 1
			savename += '.v%d'%ind
		else: savename = re.findall('(.+)\.[a-z]+',os.path.basename(search))[0]
	#---backup if necessary
	savename += '.'+form
	if os.path.isfile(directory+savename) and backup:
		for i in range(1,100):
			base = directory+savename
			latestfile = '.'.join(base.split('.')[:-1])+'.bak'+('%02d'%i)+'.'+base.split('.')[-1]
			if not os.path.isfile(latestfile): break
		if i == 99 and os.path.isfile(latestfile):
			raise Exception('except: too many copies')
		else: 
			status('backing up '+directory+savename+' to '+latestfile,tag='store')
			os.rename(directory+savename,latestfile)
	plt.savefig(directory+savename,dpi=dpi,bbox_extra_artists=extras,bbox_inches='tight')
	plt.close()
	#---add metadata to png
	if meta != None:
		im = Image.open(directory+savename)
		imgmeta = PngImagePlugin.PngInfo()
		imgmeta.add_text('meta',json.dumps(meta))
		im.save(directory+savename,form,pnginfo=imgmeta)
	
def picturedat(savename,directory='./',bank=False):

	"""
	Read metadata from figures with identical names.
	"""

	directory = os.path.join(directory,'')
	if not bank: 
		if os.path.isfile(directory+savename): 
			return json.loads(Image.open(directory+savename).info['meta'])
		else: return
	else:
		dicts = {}
		if os.path.isfile(directory+savename):
			dicts[directory+savename] = Image.open(directory+savename).info
		for i in range(1,100):
			base = directory+savename
			latestfile = '.'.join(base.split('.')[:-1])+'.bak'+('%02d'%i)+'.'+base.split('.')[-1]
			if os.path.isfile(latestfile): dicts[latestfile] = json.loads(Image.open(latestfile).info)
		return dicts

def picturefind(savename,directory='./',meta=None):

	status('searching pictures',tag='store')
	regex = '^.+\.v([0-9]+)\.png'
	fns = glob.glob(directory+'/'+savename+'*')
	nums = map(lambda y:(y,int(re.findall(regex,y)[0])),filter(lambda x:re.match(regex,x),fns))
	matches = [fn for fn,num in nums if meta==picturedat(os.path.basename(fn),directory=directory)]
	if len(matches)>1 and meta!=None: raise Exception('[ERROR] multiple matches found for %s'%savename)
	if matches==[] and meta==None:
		return dict([(os.path.basename(fn),
			picturedat(os.path.basename(fn),directory=directory)) for fn,num in nums]) 
	return matches if not matches else matches[0]

