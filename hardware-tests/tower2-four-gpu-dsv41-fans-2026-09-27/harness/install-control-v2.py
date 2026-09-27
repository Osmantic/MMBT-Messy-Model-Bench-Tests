"""Narrow reviewed update bridge. Only the owned study installation is writable."""
import datetime,hashlib,json,subprocess
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');P=B/'fan-control-v2';E=B/'evidence'
FILES=('common.py','policy.py','hardware.py','recovery.py','controller.py','observer.py','model-gate.py','workload.py','status.py','pynvml.py')
UNITS=('mmbt-gpu-control.service','mmbt-native-watchdog.service','mmbt-dsv41.service')
for unit in UNITS:
    state=subprocess.check_output(['systemctl','show','--property=ActiveState','--value',unit],text=True).strip()
    assert state in ('inactive','failed'),(unit,state)
state=json.loads(subprocess.check_output(['docker','inspect','--format','{{json .State}}','mmbt-dsv41'],text=True))
assert state['Running'] and state['Paused'],'Keep loaded runtime paused throughout update'
names=FILES+UNITS+('gpu-profile.json',);hashes={n:hashlib.sha256((P/n).read_bytes()).hexdigest() for n in names}
lease=B/'guard-state/lease';inode=lease.stat().st_ino
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
code='''import hashlib,json,os,pathlib,shutil
s=pathlib.Path('/source');d=pathlib.Path('/destination');u=pathlib.Path('/units');c=pathlib.Path('/config')
backup=d/'backups'/%r;backup.mkdir(parents=True,exist_ok=False)
hashes=json.loads(%r);records=[]
mapping={n:d/n for n in %r};mapping.update({n:u/n for n in %r});mapping['gpu-profile.json']=c/'gpu-profile.json'
for n,t in mapping.items():
    assert hashlib.sha256((s/n).read_bytes()).hexdigest()==hashes[n]
    assert not t.is_symlink() and t.parent.stat().st_uid==0 and not t.parent.stat().st_mode&0o022
    if t.exists():assert t.stat().st_uid==0 and not t.stat().st_mode&0o022
for n,t in mapping.items():
    old=hashlib.sha256(t.read_bytes()).hexdigest() if t.exists() else None
    if t.exists():shutil.copyfile(t,backup/n)
    records.append({'name':n,'destination':str(t),'oldSha256':old,'newSha256':hashes[n]})
for n,t in mapping.items():
    temp=t.with_name(t.name+'.v2-install-tmp');shutil.copyfile(s/n,temp);os.chown(temp,0,0);temp.chmod(0o644);os.replace(temp,t)
    assert hashlib.sha256(t.read_bytes()).hexdigest()==hashes[n]
(backup/'manifest.json').write_text(json.dumps(records,indent=2))
print(json.dumps({'backup':str(backup),'changes':records}))
'''%(stamp,json.dumps(hashes),FILES,UNITS)
args=['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--cap-add','DAC_OVERRIDE','--cap-add','CHOWN','--cap-add','FOWNER','--security-opt','no-new-privileges','-v','/usr:/usr:ro','-v',str(P)+':/source:ro','-v','/opt/mmbt/gpu-control:/destination','-v','/etc/systemd/system:/units','-v','/etc/mmbt:/config','--entrypoint','/usr/bin/python3','ubuntu:24.04','-c',code]
r=subprocess.run(args,text=True,capture_output=True,timeout=30,check=True)
assert lease.stat().st_ino==inode
receipt={'utc':stamp,'rootInstallation':json.loads(r.stdout),'sourceHashes':hashes,'leaseInodeBefore':inode,'leaseInodeAfter':lease.stat().st_ino,'activated':False,'checkpointStillPaused':True}
(E/('v2-control-install-'+stamp+'.json')).write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
