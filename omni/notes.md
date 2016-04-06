# development notes

## 2016.4.5

currently completing major revisions to use multiple data spots and paths
currently testing on a large dataset with many calculations
note that the slices have been significantly changed and this required in-place replacements via the following command:
	"find ./calcs/ -name "*.py" | xargs sed -i 's/work\.slices\[sn\]/work.slice\(sn\)/g'"
unresolved issues:
	1. consider removing the "dry" functionality e.g. "make compute dry" which would interpret the specs files without doing anything. this was intended to update the workspace in the event that the user changed the specs and ran the calculations in an order that broke the consistency of the database. a far better solution would prevent this from happening in the first place.
	2. paths are set to allow multiple spots. the workspace holds self.cursor and self.c which tell you the "active" or desired spotname. a spotname is a couple with the name of the spot and the name of the part according to paths.yaml. the basic use case will have self.cursor = ('simulations','xtc'). the self.c just holds the first part, and is named with a single letter because it will be used a lot. currently the workspace.slice function mediates the interactions with the slices dictionary. you can ask for a specific spotname otherwise it will use the cursor. the major revisions to date should handle evertying on the parsing side, but we have yet to continue these changes to the calculation side. that is, we still need a multi-spot dataset to develop calculations for. at some point, the cursor will have to move or intelligently move itself to access simulations in it.

## 2016.4.6

testing on a large dataset with completed calculations
	faulty data caused a traceback which directed the user to the log file for the failure. in this case it was a failed concatenation because a subset was missing. it was easy to find the log file for that subset in order to determine that the file was missing frames. the error reporting didn't stop the calculator, which is a key feature when rapidly analyzing large, possibly error-containing data sets
outstanding issues
	documentation
		we need to document the computer
		is the logging behavior okay? 
			recall problems on OSX when running calculations over a tunnel
			perhaps we should *always* log to the log file and then add a flag that runs it in the background?
	remove the dry-run behavior entirely

