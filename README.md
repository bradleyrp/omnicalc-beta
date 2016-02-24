<img src="https://github.com/bradleyrp/omnicalc/raw/master/omni/docs/source/omnicalc.png" width="150"/>

OMNICALC
========

The "omnicalc" codes are designed to apply clearly-written biophysical calculations to large simulation datasets. In conjunction with "automacs" and "factory" codes, omnicalc is the end of a data pipeline which allows users to create and analyze simulations from a simple web interface. As a standalone code, omnicalc catalog GROMACS simulation data and applies a series of (possible chained) calculations to it. The codes include plotting routines and common calculations.

Requires
--------

	1. Python version 2.7 or higher
	2. GROMACS (any version)
	3. hdf5 libraries for writing files
	4. Numpy, Scipy, and MDAnalysis Python libraries
	5. Sphinx for documentation
	
Installation
------------

Download and run ``make help`` for instructions. Run ``make config`` to set paths. Run ``make docs`` to generate documentation which explains the pipeline further.
