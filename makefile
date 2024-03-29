
#---INTERFACE TO CONTROLLER
#-------------------------------------------------------------------------------------------------------------

#---always show the banner
-include banner
banner:
	@echo -n "[STATUS] banner: "
	@sed -n 1,7p omni/readme.md
	@echo "[STATUS] use 'make help' for details"

#---do not target arguments if using python
.PHONY: banner ${RUN_ARGS}

#---hack to always run makefile interfaced with python
scripts = omni/controller.py
$(shell touch $(scripts))
checkfile = .pipeline_up_to_date

#---collect arguments
RUN_ARGS_UNFILTER := $(wordlist 1,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
RUN_ARGS := $(filter-out banner help,$(RUN_ARGS_UNFILTER))
$(eval $(RUN_ARGS):;@:)

#---valid function names from the python script
TARGETS := $(shell perl -n -e '@parts = /^def\s+[a-z,_]+/g; $$\ = "\n"; \
print for @parts;' omni/controller.py calcs/scripts/*.py | awk '{print $$2}')

#---default and arbitrary make targets
default: $(checkfile)
$(TARGETS): $(checkfile)

#---exit if target not found
controller_function = $(word 1,$(RUN_ARGS))
ifneq ($(controller_function),)
ifeq ($(filter $(controller_function),$(TARGETS)),)
    $(info [ERROR] "$(controller_function)" is not a valid make target)
    $(info [ERROR] targets are python function names in omni/controller.py or calcs/scripts/*.py)
    $(info [ERROR] valid targets include: $(TARGETS))
    $(error [ERROR] exiting)
endif
endif

#---targets
$(checkfile): $(scripts)
	touch $(checkfile)
	@echo "[STATUS] calling: python omni/controller.py ${RUN_ARGS} ${MAKEFLAGS}"
	@python omni/controller.py ${RUN_ARGS} ${MAKEFLAGS} && echo "[STATUS] bye" || { echo "[STATUS] fail"; }

#---display the help
help:
	@echo -n "[STATUS] printing readme: "
	tail -n +7 omni/readme.md

