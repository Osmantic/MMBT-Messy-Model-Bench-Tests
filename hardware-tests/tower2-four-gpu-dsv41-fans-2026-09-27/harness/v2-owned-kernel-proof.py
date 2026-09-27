"""Real owned-runtime freeze with the probe's Docker RPC deliberately absent.

Does not stop/restart Docker or alter any foreign container. Production guards
stay active. Explicit fresh-gated resume occurs only after confirmed freeze.
"""
import hashlib,json,subprocess,time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926')
state=json.loads(subprocess.check_output(['docker','inspect','--format','{{json .State}}','mmbt-dsv41'],text=True))
assert state['Running'] and not state['Paused']
before=json.loads((B/'guard-state/status.json').read_text());inode=(B/'guard-state/lease').stat().st_ino
code='''import json,os,sys,time
sys.path.insert(0,'/opt/mmbt/gpu-control');import common,workload
assert os.environ['DOCKER_HOST']=='unix:///deliberately-absent-docker.sock'
begin=time.monotonic();receipt=common.suspend('Qualification: owned kernel fallback with Docker RPC absent')
assert receipt['method']=='owned-cgroup-freezer' and receipt['paused']
identity=workload.cached();path=workload.validate(identity)
assert 'frozen 1' in (path/'cgroup.events').read_text().splitlines()
print(json.dumps({'freeze':receipt,'elapsedSeconds':time.monotonic()-begin,'rootUid':os.getuid(),'kernelFrozenVerified':True}))
'''
args=['docker','run','--rm','--network','none','--read-only','--pid','host','--cgroupns','host','--cap-drop','ALL','--cap-add','DAC_OVERRIDE','--security-opt','no-new-privileges','--security-opt','apparmor=unconfined','-e','DOCKER_HOST=unix:///deliberately-absent-docker.sock','-v','/usr:/usr:ro','-v','/opt/mmbt/gpu-control:/opt/mmbt/gpu-control:ro','-v','/run/mmbt-dsv41-identity.json:/run/mmbt-dsv41-identity.json:ro','-v','/sys/fs/cgroup:/sys/fs/cgroup','-v',str(B/'guard-state')+':'+str(B/'guard-state'),'-v',str(B/'model-state/verification.json')+':'+str(B/'model-state/verification.json')+':ro','--entrypoint','/usr/bin/python3','ubuntu:24.04','-c',code]
r=subprocess.run(args,capture_output=True,text=True,timeout=15)
if r.returncode!=0:raise RuntimeError(r.stderr) # preserve freeze on unconfirmed error
receipt=json.loads(r.stdout)
assert receipt['elapsedSeconds']<=8
time.sleep(2)
after=json.loads((B/'guard-state/status.json').read_text())
assert after['pid']==before['pid'] and (B/'guard-state/lease').stat().st_ino==inode
assert max(g['coreC'] for g in after['gpus'])<90
assert all(g['requestedPowerW']==275 and g['enforcedPowerW']==275 for g in after['gpus'])
# Docker did not issue the pause, so its Paused flag may remain false. Resume
# the exact validated cgroup only after the installed gate has freshly passed.
resume_code="import sys;sys.path.insert(0,'/opt/mmbt/gpu-control');import workload;workload.main()"
resume=args.copy();resume[resume.index('DOCKER_HOST=unix:///deliberately-absent-docker.sock')]='DOCKER_HOST=unix:///var/run/docker.sock'
resume[resume.index('--entrypoint'):]=['-v','/var/run/docker.sock:/var/run/docker.sock','--entrypoint','/usr/bin/python3','ubuntu:24.04','-c',resume_code,'unfreeze']
u=subprocess.run(resume,capture_output=True,text=True,timeout=12,check=True)
receipt.update(explicitResume=json.loads(u.stdout.strip().splitlines()[-1]),primaryPidUnchanged=True,permanentLeaseInodeUnchanged=True,caps275=True,sourceSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),foreignDockerDaemonUntouched=True)
path=B/'evidence'/('v2-owned-kernel-proof-'+str(time.time_ns())+'.json');path.write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
