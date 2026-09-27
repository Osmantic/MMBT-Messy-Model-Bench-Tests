"""Request the authorized real reboot only against a fresh exact before receipt.

Codex must independently review foreign jobs before invoking this helper.
No force/reboot syscall or foreign container mutation is used.
"""
import argparse, datetime, hashlib, json, subprocess, sys, time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence';C=Path('/opt/mmbt/gpu-control')
p=argparse.ArgumentParser();p.add_argument('before_file');p.add_argument('comparison');a=p.parse_args()
for name in (a.before_file,a.comparison):assert Path(name).name==name
old=json.loads((E/a.before_file).read_text());comparison=json.loads((E/a.comparison).read_text())
assert old['status']=='before-real-reboot' and comparison['status']=='selected-with-performance-uncertainty' and comparison['formalComparisonStatus']=='not-qualified'
assert hashlib.sha256((E/a.comparison).read_bytes()).hexdigest()=='d6a790707e9a7aa09737be89722a580b5d8aee595f081da6c70e0c7adeefc4d6'
now=datetime.datetime.now(datetime.timezone.utc)
assert 0<=(now-datetime.datetime.fromisoformat(old['utc'])).total_seconds()<=120
assert old['bootId']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert old['profileSha256']==comparison['candidateProfileSha256']==hashlib.sha256(Path('/etc/mmbt/gpu-profile.json').read_bytes()).hexdigest()
assert old['sourceHashes']=={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in sorted(C.glob('*.py'))}
for name in ('mmbt-gpu-control.service','mmbt-native-watchdog.service','mmbt-dsv41.service'):
    assert subprocess.check_output(['systemctl','is-enabled',name],text=True,timeout=3).strip()=='enabled'
protection=json.loads(subprocess.check_output([sys.executable,str(C/'status.py')],text=True,timeout=30))
assert protection['status']=='ready' and not protection['criticalLatchPresent'] and protection['bootId']==old['bootId']
assert all(g['requestedPowerW']==g['enforcedPowerW']==275 for g in protection['independentGpuSample']['gpus'])
receipt={'formalPerformanceQualification':False,'selectionReceipt':a.comparison,'status':'reboot-requested','utc':now.isoformat(),'beforeFile':a.before_file,'comparisonSha256':hashlib.sha256((E/a.comparison).read_bytes()).hexdigest(),'bootIdBefore':old['bootId'],'foreignJobReview':'required separately by invoking Codex','sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
folder=E/('v2-reboot-request-'+str(time.time_ns()));folder.mkdir();path=folder/'result.json'
path.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'status':receipt['status'],'evidence':str(path),'bootIdBefore':old['bootId']}),flush=True)
command=['docker','run','--rm','--pull','never','--network','none','--read-only','--pid','host','--cap-drop','ALL','--security-opt','no-new-privileges','--security-opt','apparmor=unconfined','-v','/usr:/usr:ro','-v','/run/systemd:/run/systemd:ro','--entrypoint','/usr/bin/systemctl','sha256:008173c23f95b170204355c12626cb5a965d779a7e1283b09e9cffbb1bf33ca3','reboot','--no-block']
r=subprocess.run(command,timeout=15)
receipt.update(systemctlExitCode=r.returncode,status='request-accepted' if r.returncode==0 else 'request-error')
path.write_text(json.dumps(receipt,indent=2)+'\n');raise SystemExit(r.returncode)
