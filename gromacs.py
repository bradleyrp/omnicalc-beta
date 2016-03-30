#!/usr/bin/python

machine_configuration = {
	'LOCAL':{
		#---specify nprocs otherwise GROMACS decides
		#---if you use modules to load gromacs binaries, specify the python header below
		module_path = '/usr/share/Modules/default/init/python.py',
		#---list the module names (e.g. gromacs/gromacs-5.0.4) needed to run "module load"
		modules = [],
		),
	}
