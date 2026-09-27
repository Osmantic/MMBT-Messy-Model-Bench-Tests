"""Read-only installed status with a bounded independent NVIDIA observation."""
import argparse, hashlib, json, subprocess, sys, time
from pathlib import Path
from common import STATE, boot, docker_state, fresh, validate_sample

UNITS=('nvidia-powerlimit.service','mmbt-gpu-control.service','mmbt-native-watchdog.service','mmbt-dsv41.service')

def main():
    p=argparse.ArgumentParser();p.add_argument('--nvml-child',action='store_true');a=p.parse_args()
    if a.nvml_child:
        import pynvml
        from hardware import Hardware
        h=Hardware(pynvml)
        try:h.open();print(json.dumps(h.read()))
        finally:h.close()
        return 0
    result={'bootId':boot(),'observations':{},'units':{},'errors':[],'sourceHashes':{}}
    for name in ('status','watchdog-status'):
        try:
            s=json.loads((STATE/(name+'.json')).read_text());fresh(s,time.monotonic(),boot());validate_sample(s,time.monotonic(),boot());result['observations'][name]=s
        except Exception as e:result['errors'].append(name+': '+type(e).__name__)
    for unit in UNITS:
        try:
            raw=subprocess.check_output(['systemctl','show',unit,'--property=ActiveState,SubState,MainPID,UnitFileState'],text=True,timeout=3)
            result['units'][unit]=dict(line.split('=',1) for line in raw.splitlines() if '=' in line)
        except Exception as e:result['errors'].append(unit+': '+type(e).__name__)
    try:
        state=docker_state();result['docker']={k:state[k] for k in ('Running','Paused','Pid','OOMKilled')}
        result['docker']['healthStatus']=state.get('Health',{}).get('Status')
    except Exception as e:result['errors'].append('owned workload: '+type(e).__name__)
    try:
        raw=subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--nvml-child'],text=True,stderr=subprocess.DEVNULL,timeout=12)
        result['independentGpuSample']=json.loads(raw)
    except Exception as e:result['errors'].append('independent GPUs: '+type(e).__name__)
    for source in Path(__file__).resolve().parent.glob('*.py'):
        result['sourceHashes'][source.name]=hashlib.sha256(source.read_bytes()).hexdigest()
    result['criticalLatchPresent']=(STATE/'critical-latch.json').exists()
    for name,sample in [*result['observations'].items(),('independentGpuSample',result.get('independentGpuSample'))]:
        try:fresh(sample,time.monotonic(),boot());validate_sample(sample,time.monotonic(),boot())
        except Exception as e:result['errors'].append(name+' at final decision: '+type(e).__name__)
    s=result['observations'].get('status',{});w=result['observations'].get('watchdog-status',{})
    sample=result.get('independentGpuSample',{});gpus=sample.get('gpus',[]);fans=[f for g in gpus for f in g['fans']];target=s.get('targetPercent')
    result['hottestCoreC']=max((g['coreC'] for g in gpus),default=None)
    result['normalTemperatureRange']=result['hottestCoreC'] is not None and result['hottestCoreC']<=82
    readback_ok=type(target) is int and 30<=target<=100 and len(fans)==8 and all(f['policy']==1 and f['target']==target and f['rpm']>0 and abs(f['current']-target)<=8 for f in fans)
    result['fanReadbackMeaning']='NVML-reported operating percentage/RPM; no independent physical tachometer'
    result['status']='ready' if not result['errors'] and not result['criticalLatchPresent'] and s.get('ready') is True and s.get('source')=='uniform-controller-v2' and w.get('source')=='independent-observer-v2' and w.get('mode')=='manual' and w.get('healthy') is True and readback_ok and result['hottestCoreC']<90 else 'not-ready'
    print(json.dumps(result,indent=2));return 0 if result['status']=='ready' else 1
if __name__=='__main__':raise SystemExit(main())
