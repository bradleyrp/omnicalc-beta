.. omni documentation master file
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. _sec-concept:

Concept
=======

*Omnicalc* is a framework for analyzing biophysical simulations with minimal, compact, human readable analysis functions, parameter sweeps, and elegant plotting functionality. The codes are designed to cleave the scientific analysis components from the bookkeeping and data structures required to run hundreds of different simulations. This separation is literal: omnicalc manages the bookkeeping while a separate repository holds the analysis codes and specifications. These resulting analysis codes are easily shared between datasets and published in tandem with journal articles. In this way, the authors hope that omnicalc can contribute to ensuring that simulation analyses are both scalabe and reproducible.

Contents
========

.. toctree::
  :maxdepth: 4
  :numbered:

  paths

.. note :: 

  slices
  calculations
  controller
  pipeline
  plots
  alchemy

Codebase
========

Most of the functions in amx sub-modules are designed to be hidden from the user. Instead, these codes document the procedures very explicitly, and these procedure codes should produce documentation for reproducing any simulation procedure while being relatively easy to read.

Check out the :doc:`OMNI codebase <omni>` for more details.

