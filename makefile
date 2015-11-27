
#---INTERFACE TO CONTROLLER
#-------------------------------------------------------------------------------------------------------------

#---always show the banner
banner:
	@echo -n "[STATUS] banner: "
	sed -n 1,7p omni/readme.md
	@echo "[STATUS] use 'make help' for details"

#---fun banner first
-include banner
	
#---valid function names from the python script
TARGETS := $(shell perl -n -e '@parts = /^def\s+[a-z,_]+/g; $$\ = "\n"; print for @parts;' omni/controller.py calcs/scripts/*.py | awk '{print $$2}')

#---collect arguments
RUN_ARGS_UNFILTER := $(wordlist 1,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
RUN_ARGS := $(filter-out banner help,$(RUN_ARGS_UNFILTER))
$(eval $(RUN_ARGS):;@:)

#---do not target arguments if using python
.PHONY: banner ${RUN_ARGS}

#---hack to always run makefile interfaced with python
scripts=omni/controller.py
$(shell touch $(scripts))
checkfile=.pipeline_up_to_date

#---targets
$(checkfile): $(scripts)
ifeq (,$(findstring push,${RUN_ARGS}))
	touch $(checkfile)
	@echo "[STATUS] calling: python omni/controller.py ${RUN_ARGS} ${MAKEFLAGS}"
	@python omni/controller.py ${RUN_ARGS} ${MAKEFLAGS} && echo "[STATUS] bye" || { echo "[STATUS] fail"; }
endif

#---default and arbitrary make targets
default: $(checkfile)
$(TARGETS): $(checkfile)

#---display the help
help:
ifeq (,$(findstring push,${RUN_ARGS}))
	@echo -n "[STATUS] printing readme: "
	tail -n +7 omni/readme.md
endif
