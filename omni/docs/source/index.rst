.. omni documentation master file
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. _sec-concept:

Concept
=======

What is omnicalc? 

Atomistic protein simulations
=============================

If you have a reasonable protein structure, automacs can perform a complete a protein-in-water simulation.

1. Start by cloning automacs and typing ``make program protein``. This will deposit a script ``script_protein.py`` in the root directory.
2. Edit ``script_protein.py`` so that ``start structure`` points to your ``PDB`` file, which should be stored in the ``inputs`` folder for safekeeping. You can adjust the other settings to taste. For convenience, if you only have a single PDB file in ``inputs``, the program will automatically detect it and use it.

.. code-block:: python
  :linenos:

  settings = """
  step:                protein
  procedure:           aamd,protein
  equilibration:       nvt,npt
  start structure:     inputs/STRUCTURE.pdb
  system name:         SYSTEM
  protein water gap:   3.0
  water:               tip3p
  force field:         charmm36
  water buffer:        1.2
  solvent:             spc216
  ionic strength:      0.150
  cation:              NA
  anion:               CL
  """

3. Run the simulation via ``./script-protein.py``. If you wish to deploy these codes on supercomputers or clusters running `TORQUE <http://www.adaptivecomputing.com/products/open-source/torque/>`_, you have to write a small :ref:`configuration <sec-configuration>` file. If it exists, running ``make cluster`` will prepare a batch script at ``cluster-protein.sh`` which can be submitted via ``qsub cluster-protein.sh``.

.. _sec-configuration:

Configuration
=============

Automacs needs to find the correct GROMACS executables. Whenever the user runs ``make``, it will check for a global configuration file at ``~/.automacs.py`` or a local one at ``./config.py``. If neither exists, it will make one and instruct the user to set it correctly. The code will use ``~/.automacs.py`` by default, but if you want to start a local configuration, run ``make config local``. Regardless of location, the configuration file will resemble the one below.

.. code-block:: python
  :linenos:

  #---a typical cluster header
  compbio_cluster_header = """#!/bin/bash
  #PBS -l nodes=NNODES:ppn=NPROCS,walltime=WALLTIME:00:00
  #PBS -j eo 
  #PBS -q opterons
  #PBS -N gmxjob
  echo "Job started on `hostname` at `date`"
  cd $PBS_O_WORKDIR
  #---commands follow
  """

  machine_configuration = {
    'LOCAL':dict(),
    'compbio':dict(
      nnodes = 1,
      nprocs = 16,
      gpu_flag = 'auto',
      modules = 'gromacs/gromacs-4.6.3',
      cluster_header = compbio_cluster_header,
      walltime = 24,
      ),
    }

The ``machine_configuration`` dictionary contains a sub-dictionary for each unique hardware you would like to use. The ``LOCAL`` dictionary can be blank, and will use a default configuration which expects GROMACS binaries to be available in the path. Any deviations from this default will require an additional entry in ``machine_configuration`` with a key that contains a substring of the hostname on your machine. 

The subdictionary contains three protected keys.

1. The ``gpu_flag`` is passed directly to the ``mdrun`` binary in GROMACS. 
2. The ``modules`` key should contain a comma-separated list of module keys which you would normally load with `module load key`. Automacs will execute this for you as long as the ``Modules`` package is available in its standard location (``/usr/share/Modules/default``). Otherwise you should add the binaries to your path manually.
3. The ``cluster_header`` key should be a string which is prepended to the top of a TORQUE submission script. It can contain key parameters in all-caps which are then substituted from lowercase keys in the `machine_configuration`` sub-dictionary. In this example, the WALLTIME will be changed to 24 when running on the ``compbio`` cluster. The ``cluster_header`` lets the user customize the job submission for the correct queue, the right number of processors, and most importantly, the correct software modules.

The Automacs code can run successfully on clusters with the industry-standard TORQUE and MODULES packages. Failing that, the user may always choose to execute the python scripts locally, or wrap them in another execution script. 

Development
===========

Automacs is both a tool and a framework. You can use it directly out of the box in order to generate molecular dynamics simulations according to typical use-cases, e.g. a coarse-grained bilayer or an atomistic simulation. But you can also use it to develop new simulations more easily. In this way, automacs provides some useful, standardized tools for making new simulation protocols. They can draw from pre-established parameter sets, have access to a number of geometric functions, automatically log themselves during the simulation, and so on. 

Each new protocol consists of a script and a set of functions. Here are some brief notes.

1. Each script has a YAML-style header section. Every variable is written to a dictionary called the "wordspace".
2. Running ``from amx import *`` and ``init(settings)`` loads the parameters into the wordspace and they are accessible everywhere.
3. Command library.
4. Writing MDP files.
5. Developing iteratively. Use the save function.

Codebase
========

Most of the functions in amx sub-modules are designed to be hidden from the user. Instead, these codes document the procedures very explicitly, and these procedure codes should produce documentation for reproducing any simulation procedure while being relatively easy to read.

Check out the :doc:`OMNI codebase <omni>` for more details.
