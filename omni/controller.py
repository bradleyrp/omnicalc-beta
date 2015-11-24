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

def config():

	"""
	Configure paths and GROMACS paths.
	All configuration files (paths.py, gromacs.py) are local.
	"""
	
	if not os.path.isfile(conf_paths): bootstrap_paths()
	if not os.path.isfile(conf_gromacs): bootstrap_gromacs()
	
#---always configure
config()
from base.computer import computer	
	
#---FUNCTIONS
#-------------------------------------------------------------------------------------------------------------

def compute(specfile=None,workspace=None,autoreload=False,dry=False):

	"""
	Open the workspace, parse a YAML script with instructions, save, and exit.
	"""

	from base.workspace import Workspace
	if workspace == None: workspace = unpacker(conf_paths,'paths')['workspace_spot']
	if specfile == None: specfile = unpacker(conf_paths,'paths')['specs_file']
	work = Workspace(workspace,previous=False,autoreload=autoreload)
	work.action(specfile,dry=dry)
	work.save()

def look(workspace=None):

	"""
	Take a look around (you). Drops you into an interactive shell with the header.
	"""

	os.system('python -i ./omni/base/header.py')
	
def plot(plotname):

	"""
	Run a plotting routine.
	"""

	fns = []
	for (dirpath, dirnames, filenames) in os.walk('./'): 
		fns.extend([dirpath+'/'+fn for fn in filenames])
	search = filter(lambda x:re.match('^\.\/[^omni].+\/plot-%s\.py$'%plotname,x),fns)
	if len(search)!=1: status('unclear search for %s: %s'%(plotname,str(search)))
	else: 
		status('rerun the plot with:\n\nexecfile(\''+search[0]+'\')\n',tag='note')
		os.system('./'+search[0])

def tests(specfile=None):

	"""
	Run the test suite. 
	Makes all plots found in the test_plots section of the specs_files.
	"""

	from base.workspace import Workspace
	if specfile == None: specfile = unpacker(conf_paths,'paths')['specs_file']
	with open(specfile,'r') as fp: test_plot_names = yaml.load(fp.read())['test_plots']
	for name in test_plot_names:
		print '[TEST SUITE] plotting %s'%name
		os.system('python calcs/plot-%s.py'%name)

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
	if '--' in arglist: arglist.remove('--')
	funcname = arglist.pop(0)
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
