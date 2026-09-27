"""Allowlisted actual process-failure qualification with independent NVML reads."""
import argparse,datetime,hashlib,json,subprocess,sys,threading,time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');sys.path.insert(0,'/opt/mmbt/gpu-control')
import pynvml
from common import STATE,atomic,boot,docker_state,fresh
from hardware import Hardware
p=argparse.ArgumentParser();p.add_argument('role',choices=['controller','observer','both']);p.add_argument('signal',choices=['SIGSTOP','SIGKILL','RESTART']);p.add_argument('--loaded',action='store_true');p.add_argument('--minimum-core',type=int,default=0);a=p.parse_args()
assert 0<=a.minimum_core<=82
roles=['controller','observer'] if a.role=='both' else [a.role]
units={'controller':'mmbt-gpu-control.service','observer':'mmbt-native-watchdog.service'};unit=','.join(units[r] for r in roles)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out=B/'evidence'/('v2-'+('loaded-' if a.loaded else 'idle-')+a.role+'-'+a.signal+'-'+stamp);out.mkdir()
def retain_failure(kind,value,traceback):
    atomic(out/'result.json',{'status':'error','utc':stamp,'bootId':boot(),'unit':unit,'signal':a.signal,'loaded':a.loaded,'error':kind.__name__+': '+str(value),'faultHarnessSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'observationsRetained':(out/'observations.jsonl').exists()})
    sys.__excepthook__(kind,value,traceback)
sys.excepthook=retain_failure
samples=[];stop=threading.Event();errors=[];initial=docker_state();assert initial['Running'] and initial['Paused'] is not a.loaded
oldpids={}
for role in roles:
    before=json.loads((STATE/('status.json' if role=='controller' else 'watchdog-status.json')).read_text());fresh(before,time.monotonic(),boot());oldpids[role]=before['pid']
h=Hardware(pynvml);h.open();initial_sample=h.read()
assert max(g['coreC'] for g in initial_sample['gpus'])>=a.minimum_core,'Stack is not warm enough for this proof'
assert max(g['coreC'] for g in initial_sample['gpus'])<=82,'Do not inject a fault without normal thermal margin'
source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/opt/mmbt/gpu-control').glob('*.py') if p.name!='pynvml.py'}
source_hashes['fault-harness.py']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
def sample_loop():
    with (out/'observations.jsonl').open('w') as f:
        while not stop.is_set():
            try:
                row=h.read()
                if max(g['coreC'] for g in row['gpus'])>=90:
                    __import__('common').suspend('Independent fault observer reached90C')
                    raise RuntimeError('Critical thermal cutoff during fault proof')
                assert all(g['requestedPowerW']==275 and g['enforcedPowerW']==275 for g in row['gpus']),'Fault proof cap differs from275W'
                row['docker']=docker_state()
                for name in ('status','watchdog-status','fallback','recovery-episode'):
                    try:row[name]=json.loads((STATE/(name+'.json')).read_text())
                    except (FileNotFoundError,ValueError):row[name]=None
                samples.append(row);f.write(json.dumps(row)+'\n');f.flush()
            except Exception as e:errors.append(str(e))
            stop.wait(.15)
t=threading.Thread(target=sample_loop);t.start();start=time.monotonic()
try:
    for role in roles:
        action=['restart',units[role]] if a.signal=='RESTART' else ['kill','--signal='+a.signal,units[role]]
        subprocess.run([sys.executable,str(B/'root-systemctl.py'),*action],check=True,timeout=35 if a.signal=='RESTART' else 10)
    recovered=None
    while time.monotonic()-start<35:
        time.sleep(.2)
        if not samples:continue
        row=samples[-1];s=row['status'];w=row['watchdog-status'];current={'controller':s,'observer':w}
        changed=all(current[r] and current[r].get('pid')!=oldpids[r] for r in roles)
        if changed and s and w and s.get('ready') is True and w.get('healthy') is True and w.get('mode')=='manual':
            fresh(s,time.monotonic(),boot());fresh(w,time.monotonic(),boot());recovered=time.monotonic();break
    assert recovered is not None,'Did not recover within35s'
    time.sleep(1)
finally:stop.set();t.join(timeout=5);h.close()
auto=[r for r in samples if all(f['policy']==0 for g in r['gpus'] for f in g['fans'])]
receipts=[r['fallback'] for r in samples if r['fallback'] and r['fallback'].get('source')=='automatic-handoff' and r['fallback'].get('verifiedAutomatic') is True and r['fallback']['monotonic']>=start]
assert auto or receipts,'No independent automatic readback or current restoration receipt'
assert not errors,errors
assert all(r['docker']['Running'] and r['docker']['Paused'] is not a.loaded for r in samples),'Workload continuity changed unexpectedly'
assert recovered-start<=30,'Exceeded custom recovery deadline'
result={'utc':stamp,'bootId':__import__('common').boot(),'sourceHashes':source_hashes,'initialMaximumCoreC':max(g['coreC'] for g in initial_sample['gpus']),'minimumStartingCoreC':a.minimum_core,'unit':unit,'signal':a.signal,'loaded':a.loaded,'oldPids':oldpids,'newPids':{r:current[r]['pid'] for r in roles},'elapsedToReady':recovered-start,'automaticDirectSamples':len(auto),'automaticVerifiedReceipts':len(receipts),'earliestAutoSeconds':min([r['monotonic'] for r in auto]+[r['monotonic'] for r in receipts])-start,'capsConfirmedAllSamples':True,'workloadContinuity':True,'sampleCount':len(samples),'maxCoreC':max(g['coreC'] for r in samples for g in r['gpus'])}
result['status']='pass';atomic(out/'result.json',result);print(json.dumps(result))
