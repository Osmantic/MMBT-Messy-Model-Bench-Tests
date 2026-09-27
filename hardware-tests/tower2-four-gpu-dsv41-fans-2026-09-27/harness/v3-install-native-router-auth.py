"""Install reviewed router authentication with an owner-only key file reference."""
import datetime,hashlib,json,os,shutil,stat,subprocess,urllib.request
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence';S=Path('/home/michael/.local/lib/dream-fleet/router/dream_fleet_router.py');P=Path('/home/michael/.config/dream-fleet/router.json');N=B/'model-router-after.py';K=B/'model-state/api-key'
assert hashlib.sha256(S.read_bytes()).hexdigest()=='91cde241fb5bc05223f90bd61edd73928bb1e5202d15e4ad2f85dc3efa408f5f'
assert hashlib.sha256(N.read_bytes()).hexdigest()=='5dff90c2adde45f28f6ddc2a79ae42e9130ea16eacaa6c1a5740756bb1da8b34'
assert stat.S_ISREG(K.lstat().st_mode) and K.stat().st_uid==os.getuid() and stat.S_IMODE(K.stat().st_mode)==0o600
with urllib.request.urlopen('http://127.0.0.1:18080/health',timeout=3) as response:health=json.load(response)
assert all(e['active']==0 for e in health['endpoints']),'Do not interrupt routed work'
cfg=json.loads(P.read_text());endpoint=next(e for e in cfg['endpoints'] if e['name']=='tower2')
assert endpoint['url']=='http://127.0.0.1:8010' and endpoint['priority']==0
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
backup=Path('/home/michael/.local/state/dream-fleet/router-backups')/stamp;backup.mkdir(parents=True);backup.chmod(0o700)
shutil.copyfile(S,backup/'dream_fleet_router.py');shutil.copyfile(P,backup/'router.json');(backup/'router.json').chmod(0o600)
endpoint.update(api_key_file=str(K),max_active=8)
tmp=S.with_name(S.name+'.dsv-update');shutil.copyfile(N,tmp);tmp.chmod(0o644);os.replace(tmp,S)
tmp=P.with_name(P.name+'.dsv-update');tmp.write_text(json.dumps(cfg,indent=2)+'\n');tmp.chmod(0o600);os.replace(tmp,P)
subprocess.run(['systemctl','--user','restart','dream-fleet-model-router.service'],check=True,timeout=15)
receipt={'status':'installed','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'oldSourceSha256':hashlib.sha256((backup/'dream_fleet_router.py').read_bytes()).hexdigest(),'newSourceSha256':hashlib.sha256(S.read_bytes()).hexdigest(),'nativeEndpoint':'tower2','priority':0,'maximumActive':8,'ownerOnlyKeyFileReference':True,'keyValueExported':False,'oldRequestsDrained':True,'backupPath':str(backup),'newConfigSha256':hashlib.sha256(P.read_bytes()).hexdigest(),'remainingWork':'Actual authenticated native and routed inference required.'}
(E/'v2-router-auth-activation.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
