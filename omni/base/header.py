#!/usr/bin/python

#---IMPORTS

import sys
#---autocompletion via startup script if absent
if 'os' not in globals():
	import os
	if 'PYTHONSTARTUP' in os.environ:
		execfile(os.environ['PYTHONSTARTUP'])
	import os
#---group writeable files
os.umask(002)
#---if building docs we do things slightly differently
building_docs = '/usr/bin/sphinx-build' in sys.argv
#---only run this script from the top directory
if not os.path.isdir('omni') and not building_docs:
	raise Exception('[ERROR] you can only use the header from the top level')
import re,pickle,subprocess
import yaml
#---scripts are run via make so we have to add to the path to find dependencies
sys.path.insert(0,'./omni/')
#---if nox (no X windows) is in the arguments then we use the Agg backend
if 'nox' in sys.argv:
	import matplotlib
	matplotlib.use('Agg')
if building_docs: sys.path.insert(0,'../../../omni')
from base.workspace import Workspace
from base.tools import status,unpacker,flatten,unique
from base.store import picturedat,picturefind,datmerge
from base.timer import checktime
from functools import wraps

conf_paths,conf_gromacs = "paths.yaml","gromacs.py"

#---get the active workspace
if 'work' not in globals() and not building_docs :
	workspace = unpacker(conf_paths)['workspace_spot']
	work = Workspace(workspace,previous=False)

#---INTERFACE

def workspace(func):

	"""
	This decorator tacks on the workspace to the function.
	"""

	@wraps(func)
	def mod(*args,**kwargs):	
		kwargs['workspace'] = work
		return func(*args,**kwargs)
	return mod

def incoming_kwargs_string():

	"""
	Controller passes kwargs to plot script as a string.
	This function finds the dictionary and returns it.
	"""

	kwargs = {}
	for a in sys.argv:
		try: kwargs = dict(eval(a))
		except: pass
	return kwargs

def doneplot(): 

	"""
	After plotting, exit if kwargs['quit'].
	"""

	if 'kwargs' in globals() and 'quit' in globals()['kwargs'] and globals()['kwargs']['quit']:
		os._exit(1)
