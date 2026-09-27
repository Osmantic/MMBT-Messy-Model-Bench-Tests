"""Hot process failures and ordinary restart, separate from performance timing."""
import json,subprocess,sys,time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');sys.path.insert(0,'/opt/mmbt/gpu-control');import common
phase='v2-hot-loaded-current-source';fixture='fixtures-'+phase+'.json'
subprocess.run([sys.executable,str(B/'build-native-fixtures.py'),'8192','1024',phase],check=True)
child=subprocess.Popen([sys.executable,str(B/'v2-native-trial.py'),phase,fixture,'900','8','2048','--allow-recovery'])
try:
    for role,sig in (('controller','SIGSTOP'),('controller','SIGKILL'),('observer','SIGSTOP'),('observer','SIGKILL'),('both','SIGSTOP'),('controller','RESTART'),('observer','RESTART')):
        for attempt in range(360):
            if child.poll() is not None:raise RuntimeError('Owned loaded fault workload ended prematurely')
            try:
                r=json.loads((common.STATE/'watchdog-status.json').read_text());common.fresh(r,time.monotonic(),common.boot())
                if r.get('healthy') is True and r.get('mode')=='manual' and max(g['coreC'] for g in r['gpus'])>=75:break
            except (FileNotFoundError,ValueError):pass
            time.sleep(1)
        else:raise RuntimeError('Hot >=75C precondition was not reached')
        subprocess.run([sys.executable,str(B/'v2-live-fault.py'),role,sig,'--loaded','--minimum-core','75'],check=True,timeout=50)
        time.sleep(3)
    child.wait(timeout=1050);assert child.returncode==0
except BaseException as error:
    common.suspend('Hot process qualification failed')
    if child.poll() is None:
        child.terminate()
        try:child.wait(timeout=10)
        except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
    path=B/'evidence'/phase/'result.json'
    if path.exists():
        result=json.loads(path.read_text());result.update(status='error',testDriverError=type(error).__name__+': '+str(error),testDriverSha256=__import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest());common.atomic(path,result)
    raise
subprocess.run([sys.executable,str(B/'v2-analyze-trial.py'),phase],check=True)
subprocess.run([sys.executable,str(B/'v2-import-receipts.py')],check=True)
