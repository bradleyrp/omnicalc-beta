#!/usr/bin/python

import os,sys,time
import yaml
import re,pickle,subprocess,glob,inspect
from base.config import bootstrap_gromacs,bootstrap_paths
from base.constants import conf_paths,conf_gromacs
from base.store import load
from base.tools import unpacker,delve,status

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

def compute(calculation_name=None,specfile=None,workspace=None,autoreload=False,dry=False):

	"""
	Open the workspace, parse a YAML script with instructions, save, and exit.
	"""

	from base.workspace import Workspace
	if workspace == None: workspace = unpacker(conf_paths,'paths')['workspace_spot']
	if specfile == None: specfile = unpacker(conf_paths,'paths')['specs_file']
	work = Workspace(workspace,previous=False,autoreload=autoreload)
	work.action(calculation_name=calculation_name,spec_fn=specfile,dry=dry)
	work.save()

def look(workspace=None,nox=False):

	"""
	Take a look around (you). Drops you into an interactive shell with the header.
	"""

	os.system('python -i ./omni/base/header.py'+(' nox' if nox else ''))

def refresh(specfile=None,workspace=None,autoreload=False,dry=False):

	"""
	If you have new data or more data (i.e. more XTC files or longer trajectories) you must
	run refresh in order to add those files to the tables of contents.
	"""

	from base.workspace import Workspace
	if workspace == None: workspace = unpacker(conf_paths,'paths')['workspace_spot']
	if specfile == None: specfile = unpacker(conf_paths,'paths')['specs_file']
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
		if specfile == None: spec_fn = unpacker(conf_paths,'paths')['specs_file']
		#---! note that this code is repeated in multiple places and needs consolidation
		#---! locations include workspace.py,action and store.py,plotload

		#---load the yaml specifications file
		if type(spec_fn)==str: spec_fn = [spec_fn]
		raw_specs = ''
		for sfn in spec_fn: 
			with open(sfn,'r') as fp: raw_specs += '\n'+fp.read()
		specs = yaml.load(raw_specs)
		if not specs: raise Exception('\n[ERROR] specs file at %s appears to be empty'%
			self.paths['specs_file'])
		#---merge automatic calculations here
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
		plotnames = specs['plots'].keys()
	else: plotnames = [plotname]

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


def tests(specfile=None,nox=False):

	"""
	Run the test suite. 
	Makes all plots found in the test_plots section of the specs_files.
	"""

	from base.workspace import Workspace
	if specfile == None: specfile = unpacker(conf_paths,'paths')['specs_file']
	with open(specfile,'r') as fp: test_plot_names = yaml.load(fp.read())['test_plots']
	for name in test_plot_names:
		print '[TEST SUITE] plotting %s'%name
		os.system('python calcs/plot-'+name+'.py'+(' nox' if nox else ''))

def export_to_factory(project_name,project_location,specfile=None,workspace=None):

	"""
	Export the simulation data from the toc to the factory database.
	Users should not run this.
	"""

	sys.path.append(project_location)
	os.environ.setdefault("DJANGO_SETTINGS_MODULE",project_name+".settings")
	from simulator import models
	from base.workspace import Workspace
	if workspace == None: workspace = unpacker(conf_paths,'paths')['workspace_spot']
	if specfile == None: specfile = unpacker(conf_paths,'paths')['specs_file']
	work = Workspace(workspace,previous=False)
	for key in work.toc:
		models.Simulation(name=key,program="protein",code=key).save()

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
	for stray in ['--','w']:
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
