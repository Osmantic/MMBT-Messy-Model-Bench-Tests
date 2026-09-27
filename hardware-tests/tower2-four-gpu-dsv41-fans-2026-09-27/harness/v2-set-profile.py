"""Allowlisted atomic root configuration update with versioned rollback."""
import argparse,datetime,hashlib,json,subprocess,sys
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');sys.path.insert(0,'/opt/mmbt/gpu-control');from policy import DEFAULT_CURVE,settings
p=argparse.ArgumentParser();p.add_argument('profile',choices=['fixed80','fixed85','curve','lower1','lower2']);p.add_argument('--startup-floor',type=int);p.add_argument('--startup-seconds',type=int);a=p.parse_args()
if a.profile.startswith('fixed') and (a.startup_floor is not None or a.startup_seconds is not None):raise ValueError('Startup parameters apply only to curves')
offset={'curve':0,'lower1':1,'lower2':2}.get(a.profile,0)
cfg={'power_limit_w':275,'mode':'fixed','fixed_percent':int(a.profile[-2:])} if a.profile.startswith('fixed') else {'power_limit_w':275,'mode':'curve','curve':[[c,v-offset if 70<=c<=80 else v] for c,v in DEFAULT_CURVE],'startup_floor':80 if a.startup_floor is None else a.startup_floor,'startup_seconds':30 if a.startup_seconds is None else a.startup_seconds}
settings(cfg);raw=json.dumps(cfg,indent=2)+'\n';sha=hashlib.sha256(raw.encode()).hexdigest();stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
code='''import hashlib,json,os,pathlib,shutil
p=pathlib.Path('/config/gpu-profile.json');assert not p.is_symlink() and p.stat().st_uid==0 and not p.stat().st_mode&0o022
old=p.read_bytes();raw=%r;assert hashlib.sha256(raw.encode()).hexdigest()==%r
backup=p.with_name('gpu-profile.backup-'+%r+'.json');shutil.copyfile(p,backup)
tmp=p.with_name('gpu-profile.v2-tmp');tmp.write_text(raw);os.chown(tmp,0,0);tmp.chmod(0o644);os.replace(tmp,p)
print(json.dumps({'oldSha256':hashlib.sha256(old).hexdigest(),'newSha256':hashlib.sha256(p.read_bytes()).hexdigest(),'backup':str(backup)}))
'''%(raw,sha,stamp)
r=subprocess.run(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--cap-add','DAC_OVERRIDE','--cap-add','CHOWN','--cap-add','FOWNER','--security-opt','no-new-privileges','-v','/usr:/usr:ro','-v','/etc/mmbt:/config','--entrypoint','/usr/bin/python3','ubuntu:24.04','-c',code],check=True,capture_output=True,text=True,timeout=10)
receipt={'utc':stamp,'profile':a.profile,'settings':cfg,'update':json.loads(r.stdout)};(B/'evidence'/('v2-profile-'+stamp+'.json')).write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
