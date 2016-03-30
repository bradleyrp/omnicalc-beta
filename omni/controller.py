#!/usr/bin/python

import os,sys,time,shutil
import yaml
import re,pickle,subprocess,glob,inspect
from base.config import bootstrap_gromacs,bootstrap_paths
from base.constants import conf_paths,conf_gromacs
from base.store import load
from base.tools import unpacker,delve,status,call

#---CONFIGURE
#-------------------------------------------------------------------------------------------------------------

def config(defaults=False,post=None,plot=None):

	"""
	Configure paths and GROMACS paths.
	All configuration files (paths.py, gromacs.py) are local.
	"""
	
	if not os.path.isfile(conf_paths): bootstrap_paths(defaults=defaults,post=post,plot=plot)
	if not os.path.isfile(conf_gromacs): bootstrap_gromacs()

#---FUNCTIONS
#-------------------------------------------------------------------------------------------------------------

def compute(calculation_name=None,workspace=None,autoreload=False,dry=False):

	"""
	Open the workspace, parse a YAML script with instructions, save, and exit.
	"""

	from base.workspace import Workspace
	if workspace == None: workspace = unpacker(conf_paths,'paths')['workspace_spot']
	work = Workspace(workspace,previous=False,autoreload=autoreload)
	work.action(calculation_name=calculation_name,dry=dry)
	work.save()

def look(workspace=None,nox=False):

	"""
	Take a look around (you). Drops you into an interactive shell with the header.
	"""

	os.system('python -i ./omni/base/header.py'+(' nox' if nox else ''))

def refresh(workspace=None,autoreload=False,dry=False):

	"""
	If you have new data or more data (i.e. more XTC files or longer trajectories) you must
	run refresh in order to add those files to the tables of contents.
	"""

	from base.workspace import Workspace
	if workspace == None: workspace = unpacker(conf_paths,'paths')['workspace_spot']
	work = Workspace(workspace,previous=False,autoreload=autoreload)
	work.bootstrap()
	work.save()
	
def plot(plotname=None,nox=False,workspace=None,specfile=None,**kwargs):

	"""
	Run a plotting routine.
	"""

	from copy import deepcopy
	if plotname == None:
		from base.workspace import Workspace
		if workspace == None: workspace = unpacker(conf_paths,'paths')['workspace_spot']
		#---! note that this code is repeated in multiple places and needs consolidation
		#---! locations include workspace.py,action and store.py,plotload
		#---! merge is now handled in workspace so this needs removed
		#---merge automatic calculations here
		if 0:
			if 'autocalcs' in specs:
				for key,val in specs['autocalcs'].items():
					if key in specs['calculations']: 
						raise Exception('\n[ERROR] redundant names in calculations and autocalcs: %s'%key+
							", which is populated with django so check calculator.Calculation")
					else: specs['calculations'][key] = deepcopy(val)
			if 'autoplots' in specs:
				for key,val in specs['autoplots'].items():
					if key in specs['plots']: 
						raise Exception('\n[ERROR] redundant names in plots and autoplots: %s'%key+
							", which is populated with django so check calculator.Calculation")
					else: specs['plots'][key] = deepcopy(val)
		work = Workspace(workspace,previous=False)
		specs = work.load_specs()
		plotnames = specs['plots'].keys()
	else: plotnames = [plotname]
	#---for each desired plot type
	for pname in plotnames:
		fns = []
		for (dirpath, dirnames, filenames) in os.walk('./'): 
			fns.extend([dirpath+'/'+fn for fn in filenames])
		search = filter(lambda x:re.match('^\.\/[^omni].+\/plot-%s\.py$'%pname,x),fns)
		if len(search)!=1: status('unclear search for %s: %s'%(pname,str(search)))
		else: 
			if plotname==None: 
				cmd = 'python '+search[0]+' nox quit=True '+' "%s"'%str(kwargs)+' &> log'
			else: 
				status('rerun the plot with:\n\nexecfile(\''+search[0]+'\')\n',tag='note')
				cmd = "python -i "+search[0]+(' nox' if nox else '')+' "%s"'%str(kwargs)
			status('calling: "%s"'%cmd,tag='status')
			os.system(cmd)

def tests(nox=False):

	"""
	Run the test suite. 
	"""

	from base.workspace import Workspace
	with open(specfile,'r') as fp: test_plot_names = yaml.load(fp.read())['test_plots']
	for name in test_plot_names:
		print '[TEST SUITE] plotting %s'%name
		os.system('python calcs/plot-'+name+'.py'+(' nox' if nox else ''))

def export_to_factory(project_name,project_location,workspace=None):

	"""
	Export the simulation data from the toc to the factory database.
	Users should not run this.
	"""

	sys.path.insert(0,project_location)
	os.environ.setdefault("DJANGO_SETTINGS_MODULE",project_name+".settings")
	import django
	django.setup()
	from simulator import models
	from base.workspace import Workspace
	#---! rpb sez remove all optional workspace arguments
	if workspace == None: workspace = unpacker(conf_paths,'paths')['workspace_spot']
	try:
		work = Workspace(workspace,previous=False)
		for key in work.toc: models.Simulation(name=key,program="protein",code=key).save()
	except: print "[STATUS] nothing to export"

def pipeline(script,nox=False):

	"""
	DEVELOPMENT
	Method for consolidating many features of the workspace in one calculation/plot.
	Initially developed for making movies.
	"""

	#---drop into the pipeline code but load the header first
	script_fn = "./calcs/pipeline-%s.py"%script
	print "[STATUS] starting pipeline via %s"%script_fn
	if not os.path.isfile(script_fn): raise Exception("[ERROR] cannot find "+script_fn)
	extra_args = "" if not nox else "import os,sys;sys.argv.append(\"nox\");"
	os.system('python -i -c \'%sexecfile("./omni/base/header.py");execfile("%s")\''%(extra_args,script_fn))

def docs(clean=False):

	"""
	Relocated the documentation codes here.
	"""

	docsdir = 'omni/docs/build'
	sourcedir = 'omni/docs/source'

	if clean: 
		build_dn = 'omni/docs/build'
		if os.path.isdir(build_dn): 
			shutil.rmtree(build_dn)
			print "[STATUS] cleaned docs"
		else: print "[STATUS] no docs to clean"
		return
	else:
		try: 
			sphinx_avail = subprocess.check_call('sphinx-apidoc --version',
				shell=True,executable='/bin/bash')
		except: sphinx_avail = 1
		if sphinx_avail != 0:
			raise Exception('\n[ERROR] sphinx-apidoc is needed for documentation')
		if not os.path.isdir(sourcedir): os.mkdir(sourcedir)
		subprocess.check_call('sphinx-apidoc -F -o %s ./omni/'%docsdir,
			shell=True,executable='/bin/bash')
		shutil.copy(sourcedir+'/conf.py',docsdir+'/')
		for fn in glob.glob(sourcedir+'/*.png'): shutil.copy(fn,docsdir+'/')
		for fn in glob.glob(sourcedir+'/*.rst'): shutil.copy(fn,docsdir+'/')
		subprocess.check_call('make html',shell=True,executable='/bin/bash',cwd=docsdir)
		shutil.copy(sourcedir+'/style.css',docsdir+'/_build/html/_static/')
		print "[STATUS] docs are ready at file://%s/omni/docs/build/_build/html/index.html"%os.getcwd()

#---INTERFACE
#-------------------------------------------------------------------------------------------------------------

def makeface(*arglist):

	"""
	Standard interface to makefile.
	"""

	#---unpack arguments
	if arglist == []: 
		raise Exception('[ERROR] no arguments to controller')
	aargs,kwargs = [],{}
	arglist = list(arglist)
	for stray in ['--','w','ws','sw','s']:
		if stray in arglist: arglist.remove(stray)
	funcname = arglist.pop(0)
	#---if not configured we exit
	if (not os.path.isfile(conf_paths) or not os.path.isfile(conf_gromacs)) and funcname != 'config': 
		raise Exception('\n[ERROR] run make config to generate gromacs.py and paths.py')
	while len(arglist)>0:
		arg = arglist.pop(0)
		regex = '^([^\=]+)\=(.+)'
		if re.match(regex,arg):
			parname,parval = re.findall(regex,arg)[0]
			kwargs[parname] = parval
		else:
			argspec = inspect.getargspec(globals()[funcname])
			if arg in argspec.args: kwargs[arg] = True
			else: aargs.append(arg)
	aargs = tuple(aargs)
	if arglist != []: raise Exception('unprocessed arguments %s'%str(arglist))
	#---log is a protected keyword for writing stdout+stderr to a file
	if 'log' in kwargs: 
		logfile = kwargs.pop('log')
		print '[LOG] no further output because writing log to %s'%logfile
		sys.stdout = sys.stderr = open(logfile,'w',0)
	#---call the function
	globals()[funcname](*aargs,**kwargs)
	if 'log' in kwargs: print '[STATUS] bye'

#---MAIN
#-------------------------------------------------------------------------------------------------------------

if __name__ == "__main__": 

	#---if the function is not above check scripts
	if sys.argv[1] not in globals(): 
		for fn in glob.glob('./calcs/scripts/*.py'): execfile(fn)
	makeface(*sys.argv[1:])
