"""Actual installed controller launch is refused by its occupied kernel lease.

The probe container has no GPU devices and no Docker/systemd sockets, so an
unexpected free lease cannot change GPU settings or the owned workload.
"""
import datetime, json, subprocess, sys, time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');sys.path.insert(0,'/opt/mmbt/gpu-control')
import common
before=json.loads((common.STATE/'status.json').read_text());common.fresh(before,time.monotonic(),common.boot());assert before['ready'] is True
inode=(common.STATE/'lease').stat().st_ino;state=common.docker_state();began=time.monotonic()
args=['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--cap-add','DAC_OVERRIDE','--security-opt','no-new-privileges','-v','/usr:/usr:ro','-v','/opt/mmbt/gpu-control:/control:ro','-v',str(common.STATE)+':'+str(common.STATE), '--entrypoint','/usr/bin/python3','ubuntu:24.04','/control/controller.py']
r=subprocess.run(args,capture_output=True,text=True,timeout=10)
assert r.returncode!=0 and 'BlockingIOError' in r.stderr and 'Resource temporarily unavailable' in r.stderr,'Launch did not fail at the occupied lease'
after=json.loads((common.STATE/'status.json').read_text());common.fresh(after,time.monotonic(),common.boot())
assert after['pid']==before['pid'] and after['ready'] is True and (common.STATE/'lease').stat().st_ino==inode
later=common.docker_state();assert all(state[k]==later[k] for k in ('Running','Paused','Pid'))
common.validate_sample(after,time.monotonic(),common.boot())
assert all(f['policy']==1 and f['target']==before['targetPercent'] for g in after['gpus'] for f in g['fans'])
receipt={'utc':common.utc(),'actualInstalledControllerRefused':True,'probeHadGpuDevices':False,'probeHadHostDockerOrSystemdSocket':False,'samePrimaryPid':after['pid'],'sameLeaseInode':inode,'capsConfirmed':True,'fanTargetsPreserved':True,'workloadStatePreserved':True,'elapsedSeconds':time.monotonic()-began,'errorType':'BlockingIOError'}
path=B/'evidence'/('v2-competing-writer-'+str(time.time_ns())+'.json');common.atomic(path,receipt);print(json.dumps(receipt))
