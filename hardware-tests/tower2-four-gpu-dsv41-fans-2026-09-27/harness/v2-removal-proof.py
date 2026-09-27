"""Verify removal to automatic fans, then restore the same reviewed services.

Owned inference remains paused. Caps and permanent lease are preserved.
"""
import hashlib,json,subprocess,sys,time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence';C=Path('/opt/mmbt/gpu-control')
sys.path.insert(0,str(C));import common,hardware,pynvml
out=E/('v2-removal-proof-'+str(time.time_ns()));out.mkdir()
profile=Path('/etc/mmbt/gpu-profile.json').read_bytes();inode=(common.STATE/'lease').stat().st_ino
sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in C.glob('*.py')}
record={'status':'starting','utcStart':common.utc(),'profileSha256':hashlib.sha256(profile).hexdigest(),'sources':sources,'leaseInode':inode}
common.atomic(out/'result.json',record)
def unit(action,*names):subprocess.run([sys.executable,str(B/'root-systemctl.py'),action,*names],check=True,timeout=60)
try:
    common.suspend('Qualification: reversible custom-controller removal')
    unit('disable','mmbt-dsv41.service','mmbt-native-watchdog.service','mmbt-gpu-control.service')
    unit('stop','mmbt-native-watchdog.service');unit('stop','mmbt-gpu-control.service')
    for name in ('mmbt-native-watchdog.service','mmbt-gpu-control.service'):
        state=subprocess.check_output(['systemctl','show',name,'--property=ActiveState','--value'],text=True).strip()
        assert state in ('inactive','failed'),(name,state)
    args=['docker','run','--rm','--network','none','--read-only','--gpus','all','--cap-drop','ALL','--cap-add','DAC_OVERRIDE','--security-opt','no-new-privileges','-e','NVIDIA_DRIVER_CAPABILITIES=utility','-v','/usr:/usr:ro','-v',str(C)+':'+str(C)+':ro','-v',str(common.STATE)+':'+str(common.STATE),'-v','/var/run/docker.sock:/var/run/docker.sock','--entrypoint','/usr/bin/python3','ubuntu:24.04',str(C/'recovery.py')]
    subprocess.run(args,check=True,capture_output=True,text=True,timeout=20)
    h=hardware.Hardware(pynvml);h.open()
    try:sample=h.read()
    finally:h.close()
    common.validate_sample(sample,time.monotonic(),common.boot())
    assert all(f['policy']==0 for g in sample['gpus'] for f in g['fans'])
    assert all(g['requestedPowerW']==275 and g['enforcedPowerW']==275 for g in sample['gpus'])
    assert common.docker_state()['Paused'] and (common.STATE/'lease').stat().st_ino==inode
    common.atomic(out/'automatic-sample.json',sample)
    record.update(verifiedAutomaticAllEight=True,caps275=True,ownedInferencePaused=True)
    unit('start','mmbt-gpu-control.service');unit('start','mmbt-native-watchdog.service')
    for _ in range(30):
        gate=subprocess.run([sys.executable,str(C/'model-gate.py')],capture_output=True,text=True)
        if gate.returncode==0:break
        time.sleep(1)
    else:raise RuntimeError('Same reviewed protection did not return to fresh readiness')
    assert Path('/etc/mmbt/gpu-profile.json').read_bytes()==profile and (common.STATE/'lease').stat().st_ino==inode
    assert {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in C.glob('*.py')}==sources
    assert common.docker_state()['Paused']
    record.update(status='pass',restoredReviewedServices=True,sourceAndProfileUnchanged=True,permanentLeaseUnchanged=True,servicesRemainBootDisabled=True,utcEnd=common.utc())
except BaseException as error:
    record.update(status='error',error=type(error).__name__+': '+str(error),utcEnd=common.utc())
    common.atomic(out/'result.json',record)
    raise
common.atomic(out/'result.json',record);print(json.dumps(record))
