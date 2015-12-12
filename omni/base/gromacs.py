#!/usr/bin/python

import os,subprocess,re

#---CONSTANTS
#-------------------------------------------------------------------------------------------------------------

gmx_error_strings = [
	'File input/output error:',
	'command not found',
	'Fatal error:',
	'Fatal Error:',
	'Can not open file:',
	]
	
gmx4paths = {
	'grompp':'grompp',
	'mdrun':'mdrun',
	'pdb2gmx':'pdb2gmx',
	'editconf':'editconf',
	'genbox':'genbox',
	'make_ndx':'make_ndx',
	'genion':'genion',
	'trjconv':'trjconv',
	'trjcat':'trjcat',
	'gmxcheck':'gmxcheck',
	}

gmx5paths = {
	'grompp':'gmx grompp',
	'mdrun':'gmx mdrun',
	'pdb2gmx':'pdb2gmx',
	'editconf':'editconf',
	'genbox':'gmx solvate',
	'make_ndx':'make_ndx',
	'genion':'gmx genion',
	'trjconv':'gmx trjconv',
	'trjcat':'trjcat',
	'gmxcheck':'gmxcheck',
	}
	
#---SETTINGS
#-------------------------------------------------------------------------------------------------------------

#---load configuration
config_raw = {}
#---look upwards if making docs so no tracebacks
prefix = '../../../' if re.match('.+\/docs\/build$',os.getcwd()) else ''
if os.path.isfile(prefix+'./gromacs.py'): execfile(prefix+'./gromacs.py',config_raw)
else: execfile(os.environ['HOME']+'/.automacs.py',config_raw)
machine_configuration = config_raw['machine_configuration']

#---select a machine configuration
this_machine = 'LOCAL'
hostnames = [key for key in machine_configuration 
	if any([varname in os.environ and (
	re.search(key,os.environ[varname])!=None or re.match(key,os.environ[varname]))
	for varname in ['HOST','HOSTNAME']])]
if len(hostnames)>1: raise Exception('[ERROR] multiple machine hostnames %s'%str(hostnames))
elif len(hostnames)==1: this_machine = hostnames[0]
else: this_machine = 'LOCAL'
print '[STATUS] setting gmxpaths for machine: %s'%this_machine
machine_configuration = machine_configuration[this_machine]

#---modules in LOCAL configuration must be loaded before checking version
module_path = '/usr/share/Modules/default/init/python.py'
if 'modules' in machine_configuration:
	print '[STATUS] found modules in LOCAL configuration'
	if 'module_path' in machine_configuration: module_path = machine_configuration['module_path']
	try: execfile(module_path)
	except: raise Exception('could not execute %s'%module_path)
	print '[STATUS] unloading GROMACS'
	#---note that modules that rely on dynamically-linked C-code must use EnvironmentModules
	for mod in machine_configuration['modules'].split(','):
		print '[STATUS] module load %s'%mod
		module('load',mod)
	del mod

#---basic check for gromacs version series
suffix = '' if 'suffix' not in machine_configuration else machine_configuration['suffix']
check_gmx = subprocess.Popen('gmx%s'%suffix,shell=True,
	stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()
if not re.search('not found',check_gmx[1]): gmx_series = 5
else:
	check_mdrun = ' '.join(subprocess.Popen('mdrun%s -g /tmp/md.log'%suffix,
		shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate())
	if re.search('VERSION 4',check_mdrun): gmx_series = 4
	else: raise Exception('gromacs is absent')
	del check_mdrun
print '[NOTE] using GROMACS %d'%gmx_series

#---select the right GROMACS utilities names
if gmx_series == 4: gmxpaths = dict(gmx4paths)
if gmx_series == 5: gmxpaths = dict(gmx5paths)

#---modify gmxpaths according to hardware configuration
config = machine_configuration
if 'nprocs' in config and config['nprocs'] != None: gmxpaths['mdrun'] += ' -nt %d'%config['nprocs']
if 'gpu_flag' in config: gmxpaths['mdrun'] += ' -nb %s'%config['gpu_flag']

machine_name = str(this_machine)
del config,this_machine,gmx5paths,gmx4paths,config_raw,module_path
del check_gmx,gmx_series,hostnames
if suffix != '': gmxpaths = dict([(key,val+suffix) for key,val in gmxpaths.items()])

