"""Stop only this benchmark scheduler after a completed pair rules out its gate.

The driver and any completed analysis remain preserved. This does not signal
the GPU controllers or native model. Child cleanup is reviewed separately.
"""
import datetime,hashlib,json,math,os,signal,time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence';series='v2-matched-cycle30-lower2'
candidate=json.loads((E/(series+'-p1-candidate')/'result.json').read_text())
reference=json.loads((E/(series+'-p1-ref85')/'result.json').read_text())
assert candidate['status']==reference['status']=='ok'
ratio=candidate['e2eOutputTokensPerSecond']/reference['e2eOutputTokensPerSecond'];assert ratio<.97
pids=[]
for path in Path('/proc').iterdir():
    if not path.name.isdigit():continue
    try:argv=(path/'cmdline').read_bytes().split(b'\0');argv=[x.decode() for x in argv if x]
    except (OSError,UnicodeError):continue
    if len(argv)==2 and argv[1]==str(B/'v3-run-matched-series.py'):pids.append(int(path.name))
assert len(pids)==1,pids
pid=pids[0];os.kill(pid,signal.SIGSTOP)
proof={'status':'scheduler-held-noninferiority-impossible','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'schedulerPid':pid,'completedPair':['v2-matched-cycle30-lower2-p1-ref85','v2-matched-cycle30-lower2-p1-candidate'],'endToEndRatio':ratio,'threshold':.97,'reason':'For n=3, a two-sided95% Student-t log-ratio lower limit with t=4.30265 is at or below the minimum observed pair ratio. One completed ratio below0.97 therefore rules out qualification regardless of the remaining two pairs. This is a prospective stop after observing this pair, not a relabeling of historical runs.','originalSpecSha256':hashlib.sha256((E/(series+'-spec.json')).read_bytes()).hexdigest(),'driverSourceSha256':hashlib.sha256((B/'v3-run-matched-series.py').read_bytes()).hexdigest(),'GPUControllersSignalled':False,'ownedWorkloadStateMustBeVerifiedSeparately':True,'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
folder=E/('v2-performance-stop-'+str(time.time_ns()));folder.mkdir();(folder/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({'path':str(folder),'schedulerPid':pid,'ratio':ratio,'status':proof['status']}))
