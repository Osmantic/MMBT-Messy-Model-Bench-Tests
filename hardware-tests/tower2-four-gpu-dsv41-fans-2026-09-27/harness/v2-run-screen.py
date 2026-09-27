"""One prospectively defined screen, analysis and authoritative receipt import."""
import argparse,json,subprocess,sys,time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926')
p=argparse.ArgumentParser();p.add_argument('profile',choices=['fixed80','fixed85','curve','lower1','lower2']);p.add_argument('phase');p.add_argument('--seconds',type=int,default=1200);p.add_argument('--after');p.add_argument('--startup-floor',type=int);p.add_argument('--startup-seconds',type=int);a=p.parse_args()
assert a.phase.startswith('v2-') and a.phase.replace('-','').isalnum() and 1200<=a.seconds<=3600
def run(script,*args):subprocess.run([sys.executable,str(B/script),*map(str,args)],check=True)
if a.after:
    assert a.after.startswith('v2-') and a.after.replace('-','').isalnum()
    print('Waiting for prior owned trial to finish: '+a.after,flush=True)
    for attempt in range(120):
        r=json.loads((B/'evidence'/a.after/'result.json').read_text())
        if r['status']=='ok':break
        assert r['status']=='starting',r.get('error')
        time.sleep(1)
    else:raise RuntimeError('Prior trial did not complete in120s')
options=[]
if a.startup_floor is not None:options+=['--startup-floor',a.startup_floor]
if a.startup_seconds is not None:options+=['--startup-seconds',a.startup_seconds]
run('v2-set-profile.py',a.profile,*options);run('build-native-fixtures.py',8192,1024,a.phase)
for attempt in range(25):
    r=subprocess.run([sys.executable,'/opt/mmbt/gpu-control/model-gate.py'],capture_output=True,text=True)
    if r.returncode==0:break
    time.sleep(1)
else:raise RuntimeError(r.stderr)
run('v2-native-trial.py',a.phase,'fixtures-'+a.phase+'.json',a.seconds,8,2048)
run('v2-analyze-trial.py',a.phase);run('v2-import-receipts.py')
