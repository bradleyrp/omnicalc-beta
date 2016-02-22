#!/bin/bash

<<notes
only run this from the top level alongside/from makefile
notes

here=$(pwd)
codeback=../../../omni
docsdir=omni/docs/build
sourcedir=omni/docs/source

sphinx-apidoc --version &> /dev/null
if ! [[ $? -eq 0 ]]; then echo "[ERROR] need sphinx-apidoc"; exit 1; fi

#---if no arguments we bootstrap the docs and make HTML files
if [[ ! -d $docsdir ]]; then 
mkdir $docsdir
cd $docsdir
sphinx-apidoc -F -o . $codeback
cd $here
fi
cd $sourcedir
cp conf.py $here/$docsdir
cp *.png $here/$docsdir
cp *.rst $here/$docsdir
cp style.css $here/$docsdir/_build/html/_static/
cd $here
echo $@
make -C $docsdir html
cd $sourcedir
cp style.css $here/$docsdir/_build/html/_static/
cd $here
echo "[STATUS] docs are ready at file://$(pwd)/omni/docs/build/_build/html/index.html"
