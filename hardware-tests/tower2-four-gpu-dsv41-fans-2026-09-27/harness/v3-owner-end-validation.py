"""End only this owned extra qualification run; preserve partial observations."""
import datetime,hashlib,json,os,signal,sys,time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence'
sys.path.insert(0,'/opt/mmbt/gpu-control');import common
phase='v2-selected-steady-c1'
expected=(['python3',str(B/'v3-selected-preboot-uncertain.py'),'v2-selected-base80-review.json'],
          ['/usr/bin/python3',str(B/'v2-native-trial.py'),phase,'fixtures-'+phase+'.json','1200','1','2048'])
targets=[]
for p in Path('/proc').iterdir():
    if not p.name.isdecimal():continue
    try:
        args=[a.decode() for a in (p/'cmdline').read_bytes().split(b'\0') if a]
        if args in expected:targets.append({'pid':int(p.name),'args':args,'startTicks':(p/'stat').read_text().rsplit(')',1)[1].split()[19]})
    except (FileNotFoundError,PermissionError):pass
assert 1<=len(targets)<=2,targets
pause=common.suspend('Owner ended additional qualification and waived two-hour soak')
for target in targets:
    p=Path('/proc')/str(target['pid'])
    try:
        assert (p/'stat').read_text().rsplit(')',1)[1].split()[19]==target['startTicks']
        os.kill(target['pid'],signal.SIGTERM)
    except FileNotFoundError:pass
time.sleep(1)
folder=E/phase;path=folder/'result.json';result=json.loads(path.read_text())
result.update(status='owner-interrupted',utcEnd=common.utc(),interruptionReason='Owner ended further qualification and explicitly waived the two-hour soak; no thermal or controller failure implied.')
common.atomic(path,result)
driver=E/'v2-selected-preboot-workloads/result.json';r=json.loads(driver.read_text());r.update(status='owner-interrupted',utcEnd=common.utc(),reason=result['interruptionReason']);common.atomic(driver,r)
receipt={'status':'ended-by-owner','utc':common.utc(),'bootId':common.boot(),'targets':targets,'workloadPause':pause,'soakWaived':True,'preservedPartialPhase':phase,'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
out=E/'v2-owner-ended-validation.json';assert not out.exists();common.atomic(out,receipt)
print(json.dumps({'status':receipt['status'],'targets':[t['pid'] for t in targets],'soakWaived':True,'retained':phase}))
