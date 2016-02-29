#!/usr/bin/python

from gromacs import *
import os,subprocess,re
from tools import call,status

def edrcheck(fn,debug=False):

	"""
	Find the corresponding EDR file for a trajectory and return its energy time stamps.
	"""

	start,end = None,None
	edr_fn = fn[:-3]+'edr'
	if os.path.isfile(edr_fn):
		cmd = gmxpaths['gmxcheck']+' -e %s'%edr_fn
		p = subprocess.Popen(cmd,stdout=subprocess.PIPE,stdin=subprocess.PIPE,stderr=subprocess.PIPE,shell=True)
		catch = p.communicate(input=None)
		log = re.sub('\\\r','\n','\n'.join(catch)).split('\n')
		start,end = None,None
		try: 
			start = map(lambda y:re.findall('^.+time\s*([0-9]+\.?[0-9]+)',y)[0],
				filter(lambda z:re.match('\s*(R|r)eading energy frame',z),log))[0]
			end = map(lambda y:re.findall('^.+time\s*([0-9]+\.?[0-9]+)',y)[0],
				filter(lambda z:re.match('\s*(L|l)ast energy',z),log))[0]
		except: pass
		start = float(start) if start!=None else start
		end = float(end) if end!=None else end
	if debug: 
		import pdb;pdb.set_trace()
	return start,end

def slice_trajectory(start,end,skip,seq_time_fn,outkey='TMP',
	path=None,rootdir='',postdir='',groupfn='',pbc=None,suffix='xtc',toc='toc'):

	"""
	Make a trajectory slice.
	"""

	#---relaxing enforcement of ps-denominated time stamps to allow for very small skips
	if 0: start,end,skip = int(start),int(end),int(skip)

	chop = []
	seq = seq_time_fn
	for span,key in seq:
		if None in span and any([i<=end and i>=start for i in span if i!=None]):
			#---lax requirements for adding to chop in the event of corrupted EDR files
			t0 = int(span[0]/float(skip)+1)*float(skip)
			chop.append((key,t0))
		elif any([
			(start <= span[1] and start >= span[0]),
			(end <= span[1] and end >= span[0]),
			(start <= span[0] and end >= span[1])]):
			#---! why is there a skip+1 below? it is wrong at both the beginning and end
			#---! this needs fixed/made sensible
			t0 = int(span[0]/float(skip)+0)*float(skip)
			chop.append((key,t0))
	#---make the XTC files
	cmdlist = []
	for num,val in enumerate(chop):
		sn,sub,fn = val[0]
		t0 = val[1]
		full = rootdir+path(sn,sub,fn,toc=toc)
		full = rootdir+path(sn,sub,fn,toc=toc)
		#---assume each XTC has a corresponding TPR
		tpr = full[:-3]+'tpr'
		if not os.path.isfile(tpr): raise Exception('[ERROR] cannot find TPR for %s'%full)
		#---we deal with XTC files only
		tail = ' -b %d -e %d -dt %d -s %s -f %s -o %s -n %s'%(
			t0 if t0>start else start,end,skip,tpr,full,'trjconv%d.%s'%(num,suffix),groupfn)
		if pbc != None: tail = tail + ' -pbc %s'%pbc
		cmdlist.append(gmxpaths['trjconv']+tail)

	#---make a GRO file of the first frame for reference
	key,t0 = chop[0]
	sn,sub,fn = key
	full = rootdir+path(sn,sub,fn)
	tpr = full[:-3]+'tpr'
	tail = ' -dump %d -s %s -f %s -o %s.gro -n %s'%(start,tpr,full,
		outkey,groupfn)
	if pbc != None: tail = tail + ' -pbc %s'%pbc
	call(gmxpaths['trjconv']+tail,
		cwd=postdir,inpipe='0\n',logfile='log-trjconv-frame')
	
	#---convert relevant trajectories
	for ii,cmd in enumerate(cmdlist):
		status('slicing trajectory',i=ii,looplen=len(cmdlist),tag='SLICE')
		call(cmd,logfile='log-trjconv-%d'%ii,cwd=postdir,inpipe='0\n',silent=False)
	
	#---concatenate remaining steps with no errors
	valid_parts = range(len(chop))
	for key in range(len(chop)):
		with open(postdir+'/log-trjconv-%d'%key,'r') as fp: lines = fp.readlines()
		if any(filter(lambda x:re.search('(F|f)atal error',x),lines)): valid_parts.remove(key)
	call(gmxpaths['trjcat']+' -o %s.%s -f '%(outkey,suffix)+
		' '.join(['trjconv%d.%s'%(key,suffix) for key in valid_parts]),
		cwd=postdir,logfile='log-trjcat-%s'%outkey)
		
	#---delete extraneous files
	for key in valid_parts:
		os.remove(postdir+'/trjconv%d.%s'%(key,suffix))
		os.remove(postdir+'/log-trjconv-%d'%key)
	os.remove(postdir+'/log-trjcat-%s'%outkey)
	os.remove(postdir+'log-trjconv-frame')

