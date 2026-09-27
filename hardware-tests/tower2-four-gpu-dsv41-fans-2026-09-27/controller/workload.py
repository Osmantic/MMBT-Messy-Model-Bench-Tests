"""Bounded control of the one owned native runtime, independent of Docker RPC."""
import json,os,re,stat,subprocess,time
from pathlib import Path
from common import CONTAINER,boot

IMAGE='sha256:a30e3c69e6a4de1b82e4893dfa971ab94cba126476e3a26f4d1da5d868fae04f'
CACHE=Path('/run/mmbt-dsv41-identity.json')
PROC=Path('/proc');CGROUP=Path('/sys/fs/cgroup')

def inspect():
    template='{"id":{{json .Id}},"image":{{json .Image}},"state":{{json .State}}}'
    row=json.loads(subprocess.check_output(['docker','inspect','--format',template,CONTAINER],text=True,timeout=2))
    state=row['state']
    if row['image']!=IMAGE or not re.fullmatch('[0-9a-f]{64}',row['id']):raise ValueError('Owned runtime identity differs')
    if any(type(state.get(k)) is not bool for k in ('Running','Paused')):raise ValueError('Unknown runtime state')
    return row

def process_identity(pid):
    if type(pid) is not int or pid<=1:raise ValueError('Invalid owned PID')
    # comm can contain spaces and parentheses. Fields after its final ) begin at3.
    start=int((PROC/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[19])
    lines=(PROC/str(pid)/'cgroup').read_text().splitlines()
    if len(lines)!=1 or not lines[0].startswith('0::'):raise ValueError('Unified cgroup required')
    return start,lines[0][3:]

def validate(identity):
    if identity.get('bootId')!=boot() or identity.get('image')!=IMAGE:raise ValueError('Foreign/stale runtime cache')
    cid=identity.get('id');pid=identity.get('pid')
    if type(cid) is not str or not re.fullmatch('[0-9a-f]{64}',cid):raise ValueError('Invalid container identity')
    expected='/system.slice/docker-'+cid+'.scope'
    if identity.get('cgroup')!=expected:raise ValueError('Foreign cgroup')
    start,cgroup=process_identity(pid)
    if type(identity.get('startTicks')) is not int or start!=identity['startTicks'] or cgroup!=expected:raise ValueError('PID reused or moved')
    path=CGROUP/expected.lstrip('/')
    if path.is_symlink() or path.resolve()!=path:raise ValueError('Symlink cgroup rejected')
    if str(pid) not in (path/'cgroup.procs').read_text().splitlines():raise ValueError('Owned main PID absent')
    return path

def remember(row):
    state=row['state']
    if not state['Running']:return
    start,cgroup=process_identity(state['Pid'])
    identity={'bootId':boot(),'id':row['id'],'image':row['image'],'pid':state['Pid'],'startTicks':start,'cgroup':cgroup}
    validate(identity)
    # Root-owned /run parent protects against replacing the identity cache.
    if CACHE.parent.stat().st_uid!=0 or CACHE.parent.stat().st_mode&0o022:raise ValueError('Untrusted cache parent')
    try:
        if cached()==identity:return
    except Exception:pass
    temp=CACHE.with_name(CACHE.name+'.tmp.'+str(os.getpid()))
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'w') as f:json.dump(identity,f);f.flush();os.fsync(f.fileno())
        os.replace(temp,CACHE)
    finally:temp.unlink(missing_ok=True)

def cached():
    fd=os.open(CACHE,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd) as f:
        info=os.fstat(f.fileno())
        if info.st_uid!=0 or info.st_mode&0o022 or not stat.S_ISREG(info.st_mode) or info.st_size>4096:raise ValueError('Untrusted runtime cache')
        identity=json.load(f)
    validate(identity)
    return identity

def kernel_freeze(frozen=True):
    identity=cached();path=validate(identity)
    fd=os.open(path/'cgroup.freeze',os.O_WRONLY|os.O_NOFOLLOW)
    try:os.write(fd,b'1' if frozen else b'0')
    finally:os.close(fd)
    deadline=time.monotonic()+2
    while True:
        if ('frozen '+('1' if frozen else '0')) in (path/'cgroup.events').read_text().splitlines():break
        if time.monotonic()>=deadline:raise RuntimeError('Owned kernel freezer did not confirm')
        time.sleep(.02)
    validate(identity)
    return {'running':True,'paused':frozen,'method':'owned-cgroup-freezer','id':identity['id']}

def pause():
    """Bounded Docker attempts plus a2s independently verified kernel fallback."""
    try:row=inspect()
    except Exception:return kernel_freeze()
    state=row['state']
    if not state['Running'] or state['Paused']:return {'running':state['Running'],'paused':state['Paused'],'method':'docker-state'}
    try:remember(row)
    except Exception:pass # A cache failure must not prevent ordinary Docker pause.
    try:subprocess.run(['docker','pause',CONTAINER],capture_output=True,check=True,timeout=2)
    except Exception:return kernel_freeze()
    # Prefer independent kernel confirmation. A cache write failure must not
    # prevent a successful ordinary Docker pause from being verified.
    try:return kernel_freeze()
    except Exception:
        confirmed=inspect()['state']
        if confirmed['Running'] and not confirmed['Paused']:raise RuntimeError('Pause unconfirmed')
        return {'running':confirmed['Running'],'paused':confirmed['Paused'],'method':'docker-state'}

def stop_critical():
    """Only for persistent >=90C GPU activity after an attempted pause."""
    identity=cached();path=validate(identity)
    fd=os.open(path/'cgroup.kill',os.O_WRONLY|os.O_NOFOLLOW)
    try:os.write(fd,b'1')
    finally:os.close(fd)
    return {'method':'owned-cgroup-kill','id':identity['id']}

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=['remember','freeze','unfreeze']);a=p.parse_args()
    if a.action=='remember':remember(inspect());result={'identityCached':True}
    elif a.action=='freeze':result=kernel_freeze()
    else:
        # Explicit human/orchestrator resume only; guards never invoke this path.
        import subprocess,sys
        subprocess.run([sys.executable,str(Path(__file__).with_name('model-gate.py'))],check=True,timeout=5)
        result=kernel_freeze(False)
    print(json.dumps(result))
if __name__=='__main__':main()
