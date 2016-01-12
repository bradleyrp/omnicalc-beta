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
#---only run this script from the top directory
if not os.path.isdir('omni'): raise Exception('[ERROR] you can only use the header from the top level')
import re,pickle,subprocess
import yaml
#---scripts are run via make so we have to add to the path to find dependencies
sys.path.insert(0,'./omni/')
#---if nox (no X windows) is in the arguments then we use the Agg backend
if 'nox' in sys.argv:
	import matplotlib
	matplotlib.use('Agg')
from base.constants import conf_paths,conf_gromacs
from base.config import bootstrap_gromacs,bootstrap_paths
from base.workspace import Workspace
from base.tools import status,unpacker,flatten,unique
from base.store import picturedat,picturefind,datmerge
from base.timer import checktime
from functools import wraps

#---get the active workspace
if 'work' not in globals():
	workspace = unpacker(conf_paths,'paths')['workspace_spot']
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
