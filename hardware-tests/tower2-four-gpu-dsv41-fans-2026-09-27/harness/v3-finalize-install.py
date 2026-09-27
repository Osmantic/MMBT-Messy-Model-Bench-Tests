"""Install exact measured bytes and enable persistence, without a new benchmark."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence';C=Path('/opt/mmbt/gpu-control');P=B/'fan-control-v2'
sys.path.insert(0,str(C));import common,hardware,pynvml
selection=E/'v2-selected-base80-review.json';assert hashlib.sha256(selection.read_bytes()).hexdigest()=='d6a790707e9a7aa09737be89722a580b5d8aee595f081da6c70e0c7adeefc4d6'
s=json.loads(selection.read_text());assert s['status']=='selected-with-performance-uncertainty'
profile=Path('/etc/mmbt/gpu-profile.json').read_bytes();assert hashlib.sha256(profile).hexdigest()==s['candidateProfileSha256']
for name in ('common.py','policy.py','hardware.py','recovery.py','controller.py','observer.py','model-gate.py','workload.py','status.py','pynvml.py'):
    assert (P/name).read_bytes()==(C/name).read_bytes(),name
for name in ('mmbt-gpu-control.service','mmbt-native-watchdog.service','mmbt-dsv41.service'):
    assert (P/name).read_bytes()==(Path('/etc/systemd/system')/name).read_bytes(),name
(P/'gpu-profile.json').write_bytes(profile)
before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in C.glob('*.py')};inode=(common.STATE/'lease').stat().st_ino
def unit(action,*names):subprocess.run([sys.executable,str(B/'root-systemctl.py'),action,*names],check=True,timeout=60)
common.suspend('Finalize byte-identical controller installation')
assert common.docker_state()['Running'] and common.docker_state()['Paused']
assert subprocess.check_output(['systemctl','show','mmbt-dsv41.service','--property=ActiveState','--value'],text=True).strip() in ('inactive','failed')
assert subprocess.check_output(['systemctl','show','mmbt-dsv41.service','--property=MainPID','--value'],text=True).strip()=='0'
unit('stop','mmbt-native-watchdog.service');unit('stop','mmbt-gpu-control.service')
h=hardware.Hardware(pynvml);h.open()
try:auto=h.read()
finally:h.close()
common.validate_sample(auto,time.monotonic(),common.boot())
assert all(f['policy']==0 for g in auto['gpus'] for f in g['fans']) and all(g['requestedPowerW']==g['enforcedPowerW']==275 for g in auto['gpus'])
subprocess.run([sys.executable,str(B/'install-control-v2.py')],check=True,timeout=40)
unit('daemon-reload');unit('start','mmbt-gpu-control.service');unit('start','mmbt-native-watchdog.service')
for _ in range(30):
    gate=subprocess.run([sys.executable,str(C/'model-gate.py')],capture_output=True,text=True)
    if gate.returncode==0:break
    time.sleep(1)
else:raise RuntimeError(gate.stderr)
unit('enable','mmbt-gpu-control.service','mmbt-native-watchdog.service','mmbt-dsv41.service')
assert {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in C.glob('*.py')}==before
assert Path('/etc/mmbt/gpu-profile.json').read_bytes()==profile and (common.STATE/'lease').stat().st_ino==inode
receipt={'status':'pass','utc':common.utc(),'bootId':common.boot(),'profileSha256':s['candidateProfileSha256'],'sourceHashes':before,'sourceBytesUnchanged':True,'leaseInode':inode,'leasePreserved':True,'verifiedAutomaticAllEightDuringInstallation':True,'caps275DuringInstallation':True,'freshGate':gate.stdout.strip(),'bootUnitsEnabled':['mmbt-gpu-control.service','mmbt-native-watchdog.service','mmbt-dsv41.service'],'modelStillPaused':common.docker_state()['Paused'],'formalPerformanceQualification':False,'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
path=E/'v2-final-persistent-install.json';assert not path.exists();common.atomic(path,receipt)
print(json.dumps({'status':receipt['status'],'profileSha256':receipt['profileSha256'],'bootUnitsEnabled':receipt['bootUnitsEnabled'],'allEightAutomaticVerified':True,'leasePreserved':True,'modelStillPaused':receipt['modelStillPaused']}))
