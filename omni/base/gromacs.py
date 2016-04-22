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
	'genconf':'genconf',
	'trjconv':'trjconv',
	'tpbconv':'tpbconv',
	'vmd':'vmd',
	'gmxcheck':'gmxcheck',
	}

gmx5paths = {
	'grompp':'gmx grompp',
	'mdrun':'gmx mdrun',
	'pdb2gmx':'gmx pdb2gmx',
	'editconf':'gmx editconf',
	'genbox':'gmx solvate',
	'make_ndx':'gmx make_ndx',
	'genion':'gmx genion',
	'trjconv':'gmx trjconv',
	'genconf':'gmx genconf',
	'tpbconv':'gmx convert-tpr',
	'gmxcheck':'gmx check',
	'vmd':'vmd',
	}
	
#---SETTINGS
#-------------------------------------------------------------------------------------------------------------

def prepare_machine_configuration(hostname=None):

	"""
	Prepare the machine configuration according to $HOSTNAME or for a custom machine.
	"""

	#---load configuration
	config_raw = {}
	#---look upwards if making docs so no tracebacks
	prefix = '../../../' if re.match('.+\/docs\/build$',os.getcwd()) else ''
	if os.path.isfile(prefix+'./config.py'): execfile(prefix+'./gromacs.py',config_raw)
	else: execfile(os.environ['HOME']+'/.automacs.py',config_raw)
	machine_configuration = config_raw['machine_configuration']

	#---select a machine configuration
	this_machine = 'LOCAL'
	if not hostname:
		hostnames = [key for key in machine_configuration 
			if any([varname in os.environ and (
			re.search(key,os.environ[varname])!=None or re.match(key,os.environ[varname]))
			for varname in ['HOST','HOSTNAME']])]
	else: hostnames = [key for key in machine_configuration if re.search(key,hostname)]
	if len(hostnames)>1: raise Exception('[ERROR] multiple machine hostnames %s'%str(hostnames))
	elif len(hostnames)==1: this_machine = hostnames[0]
	else: this_machine = 'LOCAL'
	print '[STATUS] setting gmxpaths for machine: %s'%this_machine
	machine_configuration = machine_configuration[this_machine]
	#---compute total number of processors for the user if missing
	if ('nnodes' in machine_configuration and 'ppn' in machine_configuration 
		and not 'nprocs' in machine_configuration):
		machine_configuration['nprocs'] = machine_configuration['nnodes']*machine_configuration['ppn']
	return machine_configuration,this_machine

def prepare_gmxpaths(machine_configuration,override=False,gmx_series=False):

	"""
	Prepare the paths to GROMACS executables.
	"""

	#---basic check for gromacs version series
	suffix = '' if 'suffix' not in machine_configuration else machine_configuration['suffix']
	check_gmx = subprocess.Popen('gmx%s'%suffix,shell=True,executable='/bin/bash',
		stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()
	if override and 'gmx_series' in machine_configuration: 
		gmx_series = machine_configuration['gmx_series']
	elif not gmx_series:
		if not re.search('command not found',check_gmx[1]): gmx_series = 5
		else:
			check_mdrun = ' '.join(subprocess.Popen('mdrun%s -g /tmp/md.log'%suffix,shell=True,
				executable='/bin/bash',stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate())
			if re.search('VERSION 4',check_mdrun): gmx_series = 4
			elif not override: raise Exception('gromacs is absent')
			else: print '[NOTE] preparing gmxpaths with override'
	else: print '[NOTE] using GROMACS %d'%gmx_series

	#---select the right GROMACS utilities names
	if gmx_series == 4: gmxpaths = dict(gmx4paths)
	if gmx_series == 5: gmxpaths = dict(gmx5paths)

	#---modify gmxpaths according to hardware configuration
	config = machine_configuration
	if suffix != '': 
		if gmx_series == 5:
			for key,val in gmxpaths.items():
				gmxpaths[key] = re.sub('gmx ','gmx%s '%suffix,val)
		else: gmxpaths = dict([(key,val+suffix) for key,val in gmxpaths.items()])
	if 'nprocs' in config and config['nprocs'] != None: gmxpaths['mdrun'] += ' -nt %d'%config['nprocs']
	#---use mdrun_command for quirky mpi-type mdrun calls on clusters
	if 'mdrun_command' in machine_configuration: gmxpaths['mdrun'] = machine_configuration['mdrun_command']
	#---if any utilities are keys in config we override it and then perform uppercase substitutions from config
	utility_keys = [key for key in gmxpaths if key in config]
	if any(utility_keys):
		for name in utility_keys:
			gmxpaths[name] = config[name]
			for key,val in config.items(): gmxpaths[name] = re.sub(key.upper(),str(val),gmxpaths[name])
		del name
	#---even if mdrun is customized in config we treat the gpu flag separately
	if 'gpu_flag' in config: gmxpaths['mdrun'] += ' -nb %s'%config['gpu_flag']	
	return gmxpaths

#---load machine configuration and gmxpaths into globals
machine_configuration,machine_name = prepare_machine_configuration()
#---load environment modules from python to setup GROMACS if necessary/desired
try:
	#---modules in LOCAL configuration must be loaded before checking version
	module_path = '/usr/share/Modules/default/init/python.py'
	if 'modules' in machine_configuration:
		import importlib
		print '[STATUS] found modules in %s configuration'%machine_name
		if 'module_path' in machine_configuration: module_path = machine_configuration['module_path']
		execfile(module_path)
		#try: execfile(module_path)
		#except: raise Exception('could not execute %s'%module_path)
		print '[STATUS] unloading GROMACS'
		#---note that modules that rely on dynamically-linked C-code must use EnvironmentModules
		modlist = machine_configuration['modules']
		if type(modlist)==str: modlist = modlist.split(',')
		for mod in modlist:
			print '[STATUS] module load %s'%mod
			module('load',mod)
		del mod
except: print '[STATUS] failed to use importlib to load modules'
gmxpaths = prepare_gmxpaths(machine_configuration)
