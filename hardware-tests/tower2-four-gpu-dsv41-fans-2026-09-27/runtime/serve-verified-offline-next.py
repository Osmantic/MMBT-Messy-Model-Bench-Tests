"""Serve verified native weights with fresh current-boot protection, offline."""
import json,math,os,subprocess,sys,time
from pathlib import Path
UUIDS={'GPU-708ffb68-e356-930d-4f83-980567b5ae3a','GPU-ff71102f-22f8-52bb-da93-2076a6531329','GPU-6b6dd6f9-2850-043f-b545-6ff4a60df2ca','GPU-fe3fb4d0-5ddc-9c05-587b-1bc84c75c1a0'}

def verify_guards(folder=Path('/guard')):
    if (folder/'critical-latch.json').exists():raise RuntimeError('Critical latch blocks native startup')
    current=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    primary=json.loads((folder/'status.json').read_text());observer=json.loads((folder/'watchdog-status.json').read_text());now=time.monotonic()
    target=primary.get('targetPercent')
    if type(target) is not int or not 30<=target<=100:raise ValueError('Uniform fan target differs')
    for record,source in ((primary,'uniform-controller-v2'),(observer,'independent-observer-v2')):
        tick=record.get('monotonic')
        if type(tick) not in (int,float) or not math.isfinite(tick) or not 0<=now-tick<=5 or record.get('bootId')!=current or record.get('source')!=source:raise ValueError('Guard freshness/identity differs')
        rows=record.get('gpus')
        if type(rows) is not list or len(rows)!=4 or {r['uuid'] for r in rows}!=UUIDS:raise ValueError('Four exact GPUs required')
        for r in rows:
            for key,low,high in (('requestedPowerW',275,275),('enforcedPowerW',150,275),('coreC',0,82)):
                value=r.get(key)
                if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:raise ValueError('Startup cap/thermal observation differs')
            fans=r.get('fans')
            if type(fans) is not list or len(fans)!=2 or any(type(f.get('fan')) is not int for f in fans) or {f['fan'] for f in fans}!={0,1}:raise ValueError('Two exact fans required')
            for f in fans:
                if type(f.get('policy')) is not int or f['policy']!=1 or type(f.get('target')) is not int or f['target']!=target:raise ValueError('Manual target differs')
                value=f.get('rpm')
                if type(value) not in (int,float) or not math.isfinite(value) or value<=0:raise ValueError('Positive reported fan RPM required')
    if primary.get('ready') is not True or primary.get('allFansSettled') is not True:raise ValueError('Primary fan settling not complete')
    if observer.get('mode')!='manual' or observer.get('healthy') is not True:raise ValueError('Independent observer not ready')
    return True

def main():
    os.environ['SGLANG_ENABLE_HEALTH_ENDPOINT_GENERATION']='false'
    sys.path.insert(0,'/opt/dsv41');import boot
    verify_guards()
    receipt=json.loads((boot.STATE/'verification.json').read_text())
    assert receipt['revision']==boot.REVISION and receipt['status']=='verified' and len(receipt['files'])==88
    names=set()
    for entry in receipt['files']:
        name=entry['name'];assert name not in names;names.add(name)
        path=boot.MODEL/name;assert path.resolve().is_relative_to(boot.MODEL.resolve())
        info=path.stat()
        assert (info.st_size,info.st_mtime_ns,info.st_ino)==(entry['bytes'],entry['mtime_ns'],entry['inode']),name
    index=json.loads((boot.MODEL/'model.safetensors.index.json').read_text())['weight_map']
    assert set(index.values())<=names
    # Original full SHA verification retained; startup checks file identities.
    verify_guards()
    sampler=subprocess.Popen([sys.executable,'-u','/study/ram-runtime-sampler.py'])
    try:return boot.serve()
    finally:
        sampler.terminate()
        try:sampler.wait(timeout=5)
        except subprocess.TimeoutExpired:sampler.kill();sampler.wait(timeout=5)
if __name__=='__main__':sys.exit(main())
