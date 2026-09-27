import datetime,hashlib,json,os,signal,subprocess,sys,tempfile,time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');P=B/'fan-control-v2'
sys.path.insert(0,str(P));from common import Lease
r=subprocess.run([sys.executable,'-m','unittest','-v','test_control'],cwd=P,capture_output=True,text=True)
assert r.returncode==0,r.stderr
with tempfile.TemporaryDirectory() as directory:
    lock=Path(directory)/'lease';script='import sys,time;sys.path.insert(0,%r);from common import Lease;\nwith Lease(%r):\n print("owned",flush=True);time.sleep(120)'%(str(P),str(lock))
    p=subprocess.Popen([sys.executable,'-c',script],stdout=subprocess.PIPE,text=True)
    assert p.stdout.readline().strip()=='owned';inode=lock.stat().st_ino
    os.kill(p.pid,signal.SIGSTOP)
    try:
        with Lease(lock):raise AssertionError('Stopped process lost exclusive lease')
    except BlockingIOError:pass
    os.kill(p.pid,signal.SIGKILL);p.wait(timeout=5)
    with Lease(lock):assert lock.stat().st_ino==inode
receipt={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'cpuTests':r.stderr,'kernelLeaseStoppedOwnerBlocks':True,'kernelKilledOwnerReleases':True,'sameInode':True,'sourceHashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in P.iterdir() if p.is_file()}}
target=B/'evidence'/('v2-cpu-proof-'+str(time.time_ns())+'.json');target.write_text(json.dumps(receipt,indent=2));print(json.dumps({k:v for k,v in receipt.items() if k not in ('cpuTests','sourceHashes')}))
