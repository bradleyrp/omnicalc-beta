#!/usr/bin/python

import re,os,sys

default_configuration_gromacs = """#!/usr/bin/python
machine_configuration = {
	'LOCAL':dict(
		nprocs = 4,
		module_path = '/usr/share/Modules/default/init/python.py',
		modules = 'gromacs/gromacs-5.0.4',
		),
	}
"""

default_paths = """#!/usr/bin/python
paths = {
	'data_spots':[DATA],
	'post_data_spot':POST,
	'post_plot_spot':PLOT,
	'workspace_spot':WORK,
	'specs_file':SPECS,
	}
"""

def set_post_directory(dn):

	"""
	Create a post-processing directory.
	"""
	
	dn = os.path.abspath(os.path.expanduser(dn))
	if os.path.isdir(dn): print '[WARNING] %s already exists so there better be data there'%dn
	else: os.mkdir(dn)
	return True
	
def check_data_dir(dn):
	
	"""
	Confirm that the user has supplied a valid directory.
	"""
	
	dn = os.path.abspath(os.path.expanduser(dn))
	if not os.path.isdir(dn): raise Exception('[ERROR] %s is missing'%dn)
	else: return True

def check_work_file(fn):
	
	"""
	Confirm that the user has supplied a valid directory.
	"""
	
	fn = os.path.abspath(os.path.expanduser(fn))
	if os.path.isfile(fn): print '[WARNING] %s already exists'%fn
	return True

def check_specs_file(fn):
	
	"""
	Confirm that the user has supplied a valid directory.
	"""
	
	fn = os.path.abspath(os.path.expanduser(fn))
	if os.path.isfile(fn): print '[WARNING] %s already exists'%fn
	else: print '[NOTE] you must create this file'
	return True
	
#---guide for setting paths for the first time
config_help = {
	'DATA':{'name':'preexisting data directory','default':None,
	'help':'the code needs at least one simulation data location (you can add more later)',
	'valid':check_data_dir},
	'POST':{'name':'postprocessing directory','default':'./post',
	'help':'location for postprocessed data (directory must not exist)',
	'valid':set_post_directory},
	'PLOT':{'name':'plot directory','default':'./post/plot',
	'help':'location for writing figures (directory must not exist)',
	'valid':set_post_directory},
	'WORK':{'name':'workspace file location','default':'./workspace',
	'help':'location for storing the workspace file',
	'valid':check_work_file},
	'SPECS':{'name':'specifications file','default':'./meta.yaml',
	'help':'location for setting specifications',
	'valid':check_specs_file},
	}
	
def bootstrap_gromacs():

	"""
	Prepare a new GROMACS configuration.
	"""

	#---we skip the bootstrap if we are only making docs from its subfolder
	print '[BOOT] bootstrapping a GROMACS configuration'
	if re.match('.+\/docs\/build$',os.getcwd()): return
	#---! remove above
	print "[STATUS] bootstrapping a configuration now"
	fn = 'gromacs.py'
	with open(fn,'w') as fp: fp.write(default_configuration_gromacs)
	print "[STATUS] default configuration file:\n|"
	for line in default_configuration_gromacs.split('\n'): print '|  '+re.sub('\t','  ',line)
	print "[STATUS] edit this file at %s"%fn
	
def bootstrap_paths():

	"""
	Prepare a new paths configuration.
	"""

	print '[BOOT] bootstrapping default paths'	
	fn = 'paths.py'
	if os.path.exists(fn): raise Exception('[DEVERROR] only bootstrap if paths.py is absent')
	paths_script = str(default_paths)
	#---begin user intervention because paths are crucial
	for key in ['DATA','POST','PLOT','WORK','SPECS']:
		prompt = '[QUESTION] enter a %s'%config_help[key]['name']
		if config_help[key]['default'] is not None:
			prompt += ' (enter for default: %s): '%config_help[key]['default']
		else: prompt += ': '
		ans = raw_input(prompt)
		if ans == '' and config_help[key]['default'] is not None:
			ans = config_help[key]['default']
		if not config_help[key]['valid'](ans): raise Exception('[ERROR] invalid response')
		else: paths_script = re.sub(key,"'%s'"%ans,paths_script)
	#---end user intervention
	with open(fn,'w') as fp: fp.write(paths_script)
	print "[STATUS] default configuration file:\n|"
	for line in paths_script.split('\n'): print '|  '+re.sub('\t','  ',line)
	print '[STATUS] edit this file at %s'%fn	
