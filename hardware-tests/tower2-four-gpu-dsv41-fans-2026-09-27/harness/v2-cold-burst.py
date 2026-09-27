"""One C1 burst from stable loaded idle, then a verified return to quiet."""
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');sys.path.insert(0,'/opt/mmbt/gpu-control');import common,pynvml
from hardware import Hardware
p=argparse.ArgumentParser();p.add_argument('phase');p.add_argument('fixtures');a=p.parse_args();assert a.phase.startswith('v2-') and Path(a.phase).name==a.phase
out=B/'evidence'/(a.phase+'-transition');out.mkdir();profile=Path('/etc/mmbt/gpu-profile.json').read_bytes();h=Hardware(pynvml);h.open();rows=[];quiet_since=None;stable_since=None;previous_target=None;safety_failure=False
def observe(f):
    assert Path('/etc/mmbt/gpu-profile.json').read_bytes()==profile
    global safety_failure
    try:
        row=h.read();common.validate_sample(row,time.monotonic(),common.boot())
        assert max(g['coreC'] for g in row['gpus'])<90
    except Exception:safety_failure=True;raise
    for name in ('status','watchdog-status'):
        row[name]=json.loads((common.STATE/(name+'.json')).read_text());common.fresh(row[name],time.monotonic(),common.boot())
    row['phaseElapsed']=time.monotonic()-begin;rows.append(row);f.write(json.dumps(row)+'\n');f.flush();return row
begin=time.monotonic();result={'phase':a.phase,'status':'starting','utcStart':common.utc(),'profileSha256':hashlib.sha256(profile).hexdigest(),'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
try:
    with (out/'observations.jsonl').open('w') as f:
        while time.monotonic()-begin<180:
            row=observe(f);fans=[fan for g in row['gpus'] for fan in g['fans']]
            idle=all(g['coreC']<65 and g['utilizationGpu']<10 for g in row['gpus'])
            if idle:
                if quiet_since is None:quiet_since=time.monotonic()
            else:quiet_since=None
            target=row['status']['targetPercent']
            if target!=previous_target:stable_since=time.monotonic();previous_target=target
            if quiet_since is not None and time.monotonic()-quiet_since>=30 and time.monotonic()-stable_since>=20 and 30<=target<=45 and row['status'].get('allFansSettled') is True and all(fan['policy']==1 and fan['target']==target for fan in fans):break
            time.sleep(1)
        else:raise RuntimeError('Stable quiet loaded idle not reached in180s')
        idle_target=target;idle_peak=max(g['coreC'] for g in row['gpus'])
        subprocess.run([sys.executable,'/opt/mmbt/gpu-control/model-gate.py'],check=True,capture_output=True,timeout=5)
        burst_begin=time.monotonic()
        child=subprocess.Popen([sys.executable,str(B/'v2-native-trial.py'),a.phase,a.fixtures,'0','1','512'])
        while child.poll() is None:observe(f);time.sleep(1)
        assert child.returncode==0
        burst_end=time.monotonic();quiet_return=None
        while time.monotonic()-burst_end<120:
            row=observe(f);fans=[fan for g in row['gpus'] for fan in g['fans']]
            target=row['status']['targetPercent']
            if all(g['utilizationGpu']<10 for g in row['gpus']) and row['status'].get('allFansSettled') is True and target<=idle_target+2 and all(fan['policy']==1 and fan['target']==target for fan in fans):quiet_return=time.monotonic();break
            time.sleep(1)
        assert quiet_return is not None,'Quiet return not reached in120s'
        burst_rows=[r for r in rows if r['monotonic']>=burst_begin]
        assert all(len({fan['target'] for g in r['gpus'] for fan in g['fans']})==1 for r in burst_rows)
        result.update(status='pass',coldWaitSeconds=burst_begin-begin,idleRequestedPercent=idle_target,idlePeakCoreC=idle_peak,burstSeconds=burst_end-burst_begin,quietReturnSeconds=quiet_return-burst_end,quietReturnedPercent=target,peakRequestedPercent=max(r['status']['targetPercent'] for r in burst_rows),peakCoreC=max(g['coreC'] for r in burst_rows for g in r['gpus']),uniformAllSnapshots=True,caps275AllSnapshots=all(g['requestedPowerW']==275 and g['enforcedPowerW']==275 for r in rows for g in r['gpus']))
except Exception as exc:
    result.update(status='failed',error=type(exc).__name__+': '+str(exc))
    if safety_failure:common.suspend('Cold burst safety observation failed')
finally:
    h.close();result['utcEnd']=common.utc();common.atomic(out/'result.json',result)
print(json.dumps(result),flush=True);raise SystemExit(0 if result['status']=='pass' else 1)
