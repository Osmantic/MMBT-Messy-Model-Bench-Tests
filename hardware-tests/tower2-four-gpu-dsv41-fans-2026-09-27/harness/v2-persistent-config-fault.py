"""Real persistent bad-config case: auto first, then production-owned pause.

An independent test observer enforces only visibility/caps and the 90C
experimental cutoff; it does not impose the production 30s deadline. The
reviewed configuration is restored in finally, and critical latches block
automatic test resumption.
"""
import argparse, concurrent.futures, hashlib, importlib.util, json, shutil, subprocess, sys, threading, time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');sys.path.insert(0,str(B));sys.path.insert(0,'/opt/mmbt/gpu-control')
spec=importlib.util.spec_from_file_location('trial',B/'v2-native-trial.py');t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)

def write_config(raw):
    code='''import os,pathlib
p=pathlib.Path('/config/gpu-profile.json');assert not p.is_symlink() and p.stat().st_uid==0
tmp=p.with_name('gpu-profile.fault-test-tmp');tmp.write_bytes(%r);os.chown(tmp,0,0);tmp.chmod(0o644);os.replace(tmp,p)
'''%raw
    subprocess.run(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--cap-add','DAC_OVERRIDE','--cap-add','CHOWN','--cap-add','FOWNER','--security-opt','no-new-privileges','-v','/usr:/usr:ro','-v','/etc/mmbt:/config','--entrypoint','/usr/bin/python3','ubuntu:24.04','-c',code],check=True,capture_output=True,timeout=10)

def main():
    p=argparse.ArgumentParser();p.add_argument('fixtures');a=p.parse_args()
    phase='v2-persistent-config-fault-'+str(time.time_ns());out=B/'evidence'/phase;out.mkdir()
    original=Path('/etc/mmbt/gpu-profile.json').read_bytes();(out/'profile.json').write_bytes(original);shutil.copyfile(__file__,out/'fault-test-source.py')
    state=t.common.docker_state();assert state['Running'] and not state['Paused']
    t.guards();assert not (t.common.STATE/'critical-latch.json').exists()
    key=t.client._read_api_key();t.client._verify_docker_image();runtime=t.client._verify_runtime(key)
    f,sha=t.load_fixture(a.fixtures);assert len(f['records'])>=128
    for earlier in (B/'evidence').glob('v2-persistent-config-fault-*/result.json'):
        assert json.loads(earlier.read_text()).get('fixtureSha256')!=sha,'Do not reuse fault fixtures'
    h=t.hardware.Hardware(t.pynvml);h.open();start=time.monotonic();stop=threading.Event();lock=threading.Lock();cursor=0;completed=[];errors=[];observations=[];bad_start=None;production_pause=None
    result={'phase':phase,'status':'starting','utcStart':t.common.utc(),'profileSha256':hashlib.sha256(original).hexdigest(),'fixtureSha256':sha,'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    t.common.atomic(out/'result.json',result)
    def worker():
        nonlocal cursor
        while not stop.is_set():
            with lock:
                rec=f['records'][cursor];cursor+=1
            try:
                _,compact=t.one(key,rec,2048,start,out,runtime)
                with lock:completed.append(compact['requestIndex'])
            except Exception as e:
                with lock:errors.append(type(e).__name__+': '+str(e))
                stop.set();raise
    def observe(log):
        row=h.read();row['docker']=t.common.docker_state()
        for name in ('status','watchdog-status','fallback','recovery-episode','suspension'):
            try:row[name]=json.loads((t.common.STATE/(name+'.json')).read_text())
            except (FileNotFoundError,ValueError):row[name]=None
        assert max(g['coreC'] for g in row['gpus'])<90,'90C experimental cutoff'
        assert all(g['requestedPowerW']==275 and 150<=g['enforcedPowerW']<=275 for g in row['gpus'])
        observations.append(row);log.write(json.dumps(row)+'\n');log.flush();return row
    pool=concurrent.futures.ThreadPoolExecutor(max_workers=8);jobs=[pool.submit(worker) for _ in range(8)]
    try:
        with (out/'observations.jsonl').open('w') as log:
            while time.monotonic()-start<15:
                row=observe(log)
                if all(g['utilizationGpu']>=10 for g in row['gpus']):break
                time.sleep(.15)
            else:raise RuntimeError('Did not establish all-card native load')
            bad_start=time.monotonic();write_config(json.dumps({'power_limit_w':275,'mode':'intentionally-invalid'}).encode())
            while time.monotonic()-bad_start<40:
                row=observe(log)
                if errors:raise RuntimeError(errors[0])
                if row['docker']['Running'] and row['docker']['Paused']:
                    # Docker's flag can precede the root-owned atomic receipt.
                    receipt=row['suspension']
                    if receipt and receipt['monotonic']>=bad_start and (t.common.STATE/'suspension.json').stat().st_uid==0:
                        production_pause=row;stop.set();break
                assert row['docker']['Running'],'Owned runtime stopped unexpectedly'
                time.sleep(.15)
            assert production_pause is not None,'Production did not pause within40s'
            receipt=production_pause['suspension'];assert receipt and receipt['monotonic']>=bad_start
            assert (t.common.STATE/'suspension.json').stat().st_uid==0,'Pause receipt was not production owned'
            autos=[r for r in observations if bad_start<=r['monotonic'] and all(fan['policy']==0 for g in r['gpus'] for fan in g['fans'])]
            assert autos,'No independent automatic-fan readback'
            episode=[r['recovery-episode'] for r in observations if r.get('recovery-episode') and r['recovery-episode'].get('bootId')==t.common.boot()]
            assert episode,'No persisted recovery episode'
            first=min(e['monotonic'] for e in episode);elapsed=receipt['monotonic']-first
            assert 30<=elapsed<=35,'Production did not obey persistent30s deadline'
            result.update(status='pass',automaticHandoffSeconds=autos[0]['monotonic']-bad_start,productionPauseSecondsSinceEpisode=elapsed,productionPauseReason=receipt['reason'],productionPauseReceiptOwnerUid=0,independentObserverEnforcedDeadline=False,maxCoreC=max(g['coreC'] for r in observations for g in r['gpus']),capsConfirmed=True)
    except Exception as e:
        result.update(status='failed',error=type(e).__name__+': '+str(e));stop.set();t.common.suspend('Persistent config fault test failed')
    finally:
        stop.set();write_config(original);h.close()
        # Resume is an explicit test recovery only if no critical event occurred.
        if result['status']=='pass' and not (t.common.STATE/'critical-latch.json').exists() and t.common.docker_state()['Paused']:
            subprocess.run([sys.executable,str(B/'v2-resume-owned.py')],check=True,timeout=35)
        for job in jobs:
            try:job.result(timeout=120)
            except Exception as e:errors.append(type(e).__name__+': '+str(e))
        pool.shutdown(wait=True,cancel_futures=True)
        if errors:result.update(status='failed',streamErrors=errors)
        result.update(utcEnd=t.common.utc(),callsComplete=len(completed),restoredProfileSha256=hashlib.sha256(Path('/etc/mmbt/gpu-profile.json').read_bytes()).hexdigest())
        assert result['restoredProfileSha256']==result['profileSha256']
        t.common.atomic(out/'result.json',result);print(json.dumps(result),flush=True)
    return 0 if result['status']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
