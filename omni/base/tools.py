#!/usr/bin/python

import os,sys,re,inspect,subprocess,time,collections
import traceback
import yaml

def flatten(k):
	while any([type(j)==list for j in k]): k = [i for j in k for i in j] 
	return k
def unique(k): return list(set(k))
def delve(o,*k): return delve(o[k[0]],*k[1:]) if len(k)>1 else o[k[0]]
def delve_dev(o,*k): 
	print "[STATUS] delving: %s,%s"%(str(o),str(k))
	try: sendup = delve(o[k[0]],*k[1:]) if len(k)>1 else o[k[0]]
	except:
		print "[ERROR] delve got stuck"
		import pdb;pdb.set_trace()
	return sendup
#---! debuggable delve
#delve = delve_dev
unescape = lambda x: re.sub(r'\\(.)',r'\1',x)
argsort = lambda seq : [x for x,y in sorted(enumerate(seq), key = lambda x: x[1])]
def path_expand(fn): return os.path.abspath(os.path.expanduser(fn))
tupleflat = lambda x: [j for k in [list([i]) if type(i)!=tuple else list(i) for i in x] for j in k]

#---! use ordered dictionary in yaml ... this is now deprecated because of problems with interpret_specs
if 0:
	_mapping_tag = yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG
	def dict_representer(dumper,data): return dumper.represent_dict(data.iteritems())
	def dict_constructor(loader,node): return collections.OrderedDict(loader.construct_pairs(node))
	yaml.add_representer(collections.OrderedDict,dict_representer)
	yaml.add_constructor(_mapping_tag,dict_constructor)

def unpacker(fn,name=None):

	"""
	Read a py or yaml file and return a variable by name.
	"""
	
	if re.match('^.+\.py',os.path.basename(fn)):
		incoming = {}
		execfile(fn,incoming)
		return incoming if not name else incoming[name]
	elif re.match('^.+\.yaml',os.path.basename(fn)):
		with open(fn) as fp: incoming = yaml.load(fp.read())
		return incoming if not name else incoming[name]
	else: raise Exception('unpacker can only read py or yaml files, not %s'%fn)

def catalog(base,path=None):

	"""
	Traverse all paths in a nested dictionary.
	"""

	if not path: path=[]
	if isinstance(base,dict):
		for x in base.keys():
			local_path = path[:]+[x]
			for b in catalog(base[x],local_path): yield b
	else: yield path,base

def asciitree(obj,depth=0,wide=2,last=[],recursed=False):

	"""
	Print a dictionary as a tree to the terminal.
	Includes some simuluxe-specific quirks.
	"""

	corner = u'\u251C'
	horizo = u'\u2500'
	vertic = u'\u2502'
	corner_ur = u'\u2510'
	corner_ul = u'\u250C'
	corner_ll = u'\u2514'
	corner_lr = u'\u2518'

	spacer = {0:'\n',
		1:' '*(wide+1)*(depth-1)+corner+horizo*wide,
		2:' '*(wide+1)*(depth-1)
		}[depth] if depth <= 1 else (
		''.join([(vertic if d not in last else ' ')+' '*wide for d in range(1,depth)])
		)+corner+horizo*wide
	if type(obj) in [str,float,int,bool]:
		if depth == 0: print spacer+str(obj)+'\n'+horizo*len(obj)
		else: print spacer+str(obj)
	elif type(obj) == dict and all([type(i) in [str,float,int,bool] for i in obj.values()]) and depth==0:
		asciitree({'HASH':obj},depth=1,recursed=True)
	elif type(obj) == list:
		for ind,item in enumerate(obj):
			if type(item) in [str,float,int,bool]: print spacer+str(item)
			elif item != {}:
				print spacer+'('+str(ind)+')'
				asciitree(item,depth=depth+1,
					last=last+([depth] if ind==len(obj)-1 else []),
					recursed=True)
			else: print 'unhandled tree object'
	elif type(obj) == dict and obj != {}:
		for ind,key in enumerate(obj.keys()):
			if type(obj[key]) in [str,float,int,bool]: print spacer+key+' = '+str(obj[key])
			#---special: print single-item lists of strings on the same line as the key
			elif type(obj[key])==list and len(obj[key])==1 and type(obj[key][0]) in [str,float,int,bool]:
				print spacer+(''.join(key) if type(key)==tuple else key)+' = '+str(obj[key])
			#---special: skip lists if blank dictionaries
			elif type(obj[key])==list and all([i=={} for i in obj[key]]):
				print spacer+(''.join(key) if type(key)==tuple else key)+' = (empty)'
			elif obj[key] != {}:
				#---fancy border for top level
				if depth == 0:
					print '\n'+corner_ul+horizo*(len(key)+0)+corner_ur+spacer+vertic+str(key)+vertic+'\n'+\
						corner_ll+horizo*len(key)+corner_lr+'\n'+vertic
				else: print spacer+(''.join(key) if type(key)==tuple else key)
				asciitree(obj[key],depth=depth+1,
					last=last+([depth] if ind==len(obj)-1 else []),
					recursed=True)
			elif type(obj[key])==list and obj[key]==[]:
				print spacer+'(empty)'
			else: print 'unhandled tree object'
	else: print 'unhandled tree object'
	if not recursed: print '\n'

def status(string,i=0,looplen=None,bar_character=None,width=25,tag='',start=None,show_bar=True):

	"""
	Show a status bar and counter for a fixed-length operation.
	"""

	#---use unicode if not piping to a log file
	logfile = sys.stdout.isatty()==False
	if not logfile: left,right,bb = u'\u2590',u'\u258C',(u'\u2592' if bar_character==None else bar_character)
	else: left,right,bb = '|','|','='
	string = '[%s] '%tag.upper()+string if tag != '' else string
	if not looplen:
		if not logfile: print string
		else: sys.stdout.write(string+'\n')
	else:
		if start != None:
			esttime = (time.time()-start)/(float(i+1)/looplen)
			timestring = ' %s minutes'%str(abs(round((esttime-(time.time()-start))/60.,1)))
			width = 15
		else: timestring = ''
		countstring = str(i+1)+'/'+str(looplen)
		if show_bar: 
			bar = ' %s%s%s '%(left,int(width*(i+1)/looplen)*bb+' '*(width-int(width*(i+1)/looplen)),right)
		else: bar = ' '
		if not logfile: 
			print unicode(u'\r'+string+bar+countstring+timestring+' '),
		else: sys.stdout.write('\r'+string+bar+countstring+timestring+' ')
		if i+1<looplen and show_bar: sys.stdout.flush()
		else: print '\n',

def call(command,logfile=None,cwd=None,silent=False,inpipe=None,suppress_stdout=False):

	"""
	Wrapper for system calls in a different directory with a dedicated log file.
	"""

	if inpipe != None:
		if logfile == None: output=None
		else: 
			output = open(('' if cwd == None else cwd)+logfile,'wb')
			if not silent: print '[BASH] executing command: "'+str(command)+'" logfile = '+logfile
		if type(command) == list: command = ' '.join(command)
		p = subprocess.Popen(command,stdout=output,stdin=subprocess.PIPE,stderr=output,cwd=cwd,shell=True)
		catch = p.communicate(input=inpipe)[0]
	else:
		if type(command) == list: command = ' '.join(command)
		if logfile != None:
			output = open(('' if cwd == None else cwd)+logfile,'wb')
			if type(command) == list: command = ' '.join(command)
			if not silent: print '[BASH] executing command: "'+str(command)+'" logfile = '+logfile
			try:
				subprocess.check_call(command,
					shell=True,
					stdout=output,
					stderr=output,
					cwd=cwd)
			except: 
				if logfile[-3:] == '-cg' and re.search('mdrun-em',logfile):
					if not silent: print 'warning: failed conjugate gradient descent but will procede'
				else: raise Exception('[ERROR] BASH execution error\nsee '+cwd+logfile)
			output.close()
		else: 
			if not silent: print '[BASH] executing command: "'+str(command)+'"'
			if str(sys.stdout.__class__) == "<class 'amx.tools.tee'>": stderr = sys.stdout.files[0]
			else: stderr = sys.stdout
			try: 
				if suppress_stdout: 
					devnull = open('/dev/null','w')
					subprocess.check_call(command,shell=True,stderr=devnull,cwd=cwd,stdout=devnull)
				else: subprocess.check_call(command,shell=True,stderr=None,cwd=cwd)
			except: 
				raise Exception('[ERROR] BASH execution error\nsee \ncommand: '+\
					command+'\ncwd: '+cwd)

def framelooper(total,start=None,text='frame'):

	"""
	When performing parallel calculations with joblib we pass a generator to count the number of 
	tasks and report the time.
	"""

	for fr in range(total):
		status(text,i=fr,looplen=total,tag='parallel',start=start)
		yield fr

def tracer_deprecated(e):

	"""
	Print a traceback and continue. Use this with exceptions.
	"""

	s = traceback.format_exc()
	print "[TRACE] > "+"\n[TRACE] > ".join(s.split('\n'))
	print "[ERROR] failed to make slice"

def tracer(e,all=True,exit=False):

	"""
	Report an error concisely to the terminal to avoid overwhelming the user.
	"""

	exc_type, exc_obj, exc_tb = sys.exc_info()
	fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
	status('%s in %s at line %d'%(str(exc_type),fname,exc_tb.tb_lineno),tag='error')
	status('%s'%e,tag='error')
	if all: status(re.sub('\n','\n[TRACEBACK] ',traceback.format_exc()),tag='traceback')
	if exit: sys.exit(1)
