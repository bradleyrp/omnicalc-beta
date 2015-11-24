#!/usr/bin/python

execfile('./ate/base/header.py')
from base.tools import asciitree

@workspace
def get_simulation_names(*args,**kwargs):

	"""
	Return all simulations with names.
	"""

	work = kwargs['workspace']
	data_path = work.paths['data_spots'][0]
	renamer = []
	for simulation_path in glob.glob(data_path+'/simulation-v*'):
		for (dirpath, dirnames, filenames) in os.walk(simulation_path): break
		renamer.extend([(os.path.basename(dirpath),
			re.sub('_',' ',re.sub('_simulation','',re.findall('^(.+)\.txt$',fn)[0])))
			for fn in filenames if re.match('^.+\.txt$',fn)
			and not re.search('upload-rsync-list.txt',fn)])
	renamer = dict(renamer)
	asciitree(renamer)
	return renamer

@workspace
def get_text_name(sn,*args,**kwargs):

	work = kwargs['workspace']
	for (dirpath, dirnames, filenames) in os.walk(work.paths['data_spots'][0]+'/'+sn): break
	text_files = [fn for fn in filenames if re.match('^.+\.txt',fn) and 
		not re.search('upload-rsync-list.txt',fn)]
	if any(text_files): return re.findall('^(.+)\.txt$',text_files.pop())[0]
		
@workspace
def get_completed_simulations(*args,**kwargs):

	"""
	Return all simulations with names.
	"""

	work = kwargs['workspace']
	finished = [i[0] for i in [(sn,work.get_timeseq(sn)[-1][0][-1]) 
		for sn in work.sns()] if i[1]>=kwargs['max_time']]
	renamer = get_simulation_names()
	for sn in work.sns(): 
		if sn not in renamer: renamer[sn] = sn
	asciitree({'completed simulations':dict([(sn if not renamer[sn] else renamer[sn],
		dict([(i[1][2],str(i[0])) for i in work.get_timeseq(sn)])) for sn in finished])})
	return renamer,finished

@workspace
def metadata(*args,**kwargs):

	"""
	A function which writes the slices section of specs/meta.yaml for the current dataset.
	"""

	start_time,end_time = 1000,5000
	spacer = ' '*2
	renamer,finished = get_completed_simulations(max_time=end_time)
	specs_strings = '\nslices:'
	for sn in finished:
		specs_strings += '\n'+spacer+sn+':'
		specs_strings += '\n'+spacer*2+'groups:\n'+spacer*3+'all: all'
		specs_strings += '\n'+spacer*2+'slices:\n'+spacer*3+\
			"current: {'pbc':'mol','groups':['all'],'start':%d,'end':%d,'skip':100}"%(
				start_time,end_time)
	print specs_strings
	meta_strings = '\nmeta:'
	for sn in finished:
		meta_strings += '\n'+spacer+sn+':'
		meta_strings += '\n'+spacer*2+'name: %s'%(sn if not renamer[sn] else renamer[sn])
	print meta_strings
	print '\ncollections:\n'+spacer+'all:\n'+'\n'.join([spacer*2+'- %s'%sn for sn in finished])

	print '\n[NOTE] manually add the specifications above to %s'%work.paths['specs_file']
	#---! automatically write this to a section in the meta.yaml file
