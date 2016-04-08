#!/usr/bin/python

import time
from gromacs import *
import os,subprocess,re
from tools import call,status,delve
import MDAnalysis

def gmxread(grofile,trajfile=None):

	"""
	Read a simulation trajectory via MDAnalysis.
	"""

	if trajfile == None: uni = MDAnalysis.Universe(grofile)
	else: uni = MDAnalysis.Universe(grofile,trajfile)
	return uni

def mdasel(uni,select): 

	"""
	Make a selection in MDAnalysis regardless of version.
	"""

	if hasattr(uni,'select_atoms'): return uni.select_atoms(select)
	else: return uni.selectAtoms(select)

def edrcheck(fn,debug=False):

	"""
	Given the path of an EDR file we return its start and end time.
	!!! Perhaps store the EDR data in a more comprehensive format.
	"""

	start,end = None,None
	cmd = gmxpaths['gmxcheck']+' -e %s'%fn
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
	return start,end

def infer_parts_to_slice(start,end,skip,sequence):

	"""
	We collect start/stop times from EDR files before slicing because it's faster than parsing the
	trajectories themselves. But since the timestamps in EDR files are not 1-1 with the trajectories
	we have to infer which trajectory files to use, in a non-strict way.
	"""
	
	sources = []
	for key,span in sequence:
		if None in span and any([i<=end and i>=start for i in span if i!=None]):
			#---lax requirements for adding to sources in the event of corrupted EDR files
			t0 = int(span[0]/float(skip)+1)*float(skip)
			sources.append((key,t0))
		elif any([
			(start <= span[1] and start >= span[0]),
			(end <= span[1] and end >= span[0]),
			(start <= span[0] and end >= span[1])]):
			#---! why is there a skip+1 below? it is wrong at both the beginning and end
			#---! this needs fixed/made sensible
			t0 = int(span[0]/float(skip)+0)*float(skip)
			sources.append((key,t0))
	return sources

def slice_trajectory(start,end,skip,sequence,outkey,postdir,tpr_keyfinder,traj_keyfinder,
	output_format='xtc',pbc=None,group_fn=None):

	"""
	Make a trajectory slice.
	The keyfinders are lambda functions that take keys and return the correct filename.
	"""

	#---commands to create sub-slices
	sources = infer_parts_to_slice(start,end,skip,sequence)
	sn = sources[0][0][0]
	group_flag = '' if not group_fn else ' -n '+group_fn
	pbc_flag = '' if not pbc else ' -pbc %s'%pbc
	cmdlist = []
	for num,source in enumerate(sources):
		keys,t0 = source
		sn = keys[0]
		#---get tpr exist use the previous one (or fail on first source)
		try: tpr = tpr_keyfinder(*keys,strict=False)
		except: pass
		#---assume cursor points to the trajectory we want
		try: traj = traj_keyfinder(*keys)
		except:
			status('could not locate trajectory for %s,%s,%s'%keys)
			continue
		outfile = 'trjconv%d.%s'%(num,output_format)
		tail = ' -b %d -e %d -dt %d -s %s -f %s -o %s%s%s'%(
			t0 if t0>start else start,end,skip,tpr,traj,
			outfile,group_flag,pbc_flag)
		cmdlist.append((outfile,gmxpaths['trjconv']+tail))

	#---make a GRO file of the first frame for reference
	keys,t0 = sources[0]
	sn,sub,fn = keys
	traj = traj_keyfinder(*keys)
	tail = ' -dump %d -s %s -f %s -o %s.gro%s'%(start,tpr,traj,outkey,group_flag)
	if pbc != None: tail = tail + ' -pbc %s'%pbc
	call(gmxpaths['trjconv']+tail,
		cwd=postdir,inpipe='0\n',logfile='log-trjconv-frame')
	
	#---convert relevant trajectories
	start = time.time()
	for ii,(outfile,cmd) in enumerate(cmdlist):
		status('slicing trajectory',i=ii,looplen=len(cmdlist),start=start,tag='SLICE',show_bar=False)
		call(cmd,logfile='log-trjconv-%s'%outfile,cwd=postdir,inpipe='0\n',silent=False)
	
	#---concatenate remaining steps with no errors
	valid_parts = range(len(cmdlist))
	for key in range(len(cmdlist)):
		with open(postdir+'/log-trjconv-%s'%outfile,'r') as fp: lines = fp.readlines()
		if any(filter(lambda x:re.search('(F|f)atal error',x),lines)): valid_parts.remove(key)
	call(gmxpaths['trjcat']+' -o %s.%s -f '%(outkey,output_format)+
		' '.join(zip(*cmdlist)[0]),cwd=postdir,logfile='log-trjcat-%s'%outkey)
		
	#---delete extraneous files
	#---! consider using a temporary directory although it's nice to have things onsite
	for outfile in zip(*cmdlist)[0]:
		os.remove(postdir+'/%s'%outfile)
		os.remove(postdir+'/log-trjconv-%s'%outfile)
	os.remove(postdir+'/log-trjcat-%s'%outkey)
	os.remove(postdir+'log-trjconv-frame')
