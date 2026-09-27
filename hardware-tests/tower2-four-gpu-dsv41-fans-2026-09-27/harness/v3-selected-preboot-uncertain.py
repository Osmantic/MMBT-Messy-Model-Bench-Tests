"""Post-comparison workload coverage, then real hot process faults.

Runs only the exact reviewed curve; formal performance remains unqualified. No model or controller edits.
"""
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence'
sys.path.insert(0,'/opt/mmbt/gpu-control');import common
p=argparse.ArgumentParser();p.add_argument('comparison');arg=p.parse_args();assert Path(arg.comparison).name==arg.comparison and arg.comparison=='v2-selected-base80-review.json'
comparison=E/arg.comparison
c=json.loads(comparison.read_text());assert c['status']=='selected-with-performance-uncertainty' and c['formalComparisonStatus']=='not-qualified' and c['formalPerformanceClaimAccepted'] is False;assert hashlib.sha256(comparison.read_bytes()).hexdigest()=='d6a790707e9a7aa09737be89722a580b5d8aee595f081da6c70e0c7adeefc4d6'
pin=c['candidateProfileSha256'];assert hashlib.sha256(Path('/etc/mmbt/gpu-profile.json').read_bytes()).hexdigest()==pin
out=E/'v2-selected-preboot-workloads';out.mkdir(exist_ok=False)
receipt={'formalPerformanceQualification':False,'selectionStatus':c['status'],'status':'starting','utcStart':common.utc(),'comparisonSha256':hashlib.sha256(comparison.read_bytes()).hexdigest(),'profileSha256':pin,'commands':[], 'criteria':{'C1':'20min, normal thermal/steady qualification','longPrefill':'C1 exact65536 input /2048 output, 180s dispatch plus drain; peak<=82, caps275, no thermal counter increment','bursts':'two quiet-idle to loaded transitions with verified uniform targets and quiet return','hotFaults':'seven actual process cases, each starting75..82C, bounded automatic handoff and custom recovery, workload continuity'}}
common.atomic(out/'result.json',receipt)
def run(script,*args):
    assert hashlib.sha256(Path('/etc/mmbt/gpu-profile.json').read_bytes()).hexdigest()==pin
    command=[sys.executable,str(B/script),*map(str,args)]
    started=common.utc();log=out/(str(len(receipt['commands']))+'-'+script+'.txt')
    with log.open('w') as f:r=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT)
    receipt['commands'].append({'command':command,'utcStart':started,'utcEnd':common.utc(),'exitCode':r.returncode,'sourceSha256':hashlib.sha256((B/script).read_bytes()).hexdigest(),'log':log.name})
    common.atomic(out/'result.json',receipt)
    assert r.returncode==0,(script,log.name,r.returncode)
    print(json.dumps({'completed':script,'args':list(args),'utc':common.utc()}),flush=True)
def trial(name,input_tokens,count,seconds,concurrency,budget):
    run('build-native-fixtures.py',input_tokens,count,name)
    run('v2-native-trial.py',name,'fixtures-'+name+'.json',seconds,concurrency,budget)
    run('v2-analyze-trial.py',name)
    result=json.loads((E/name/'result.json').read_text());a=json.loads((E/name/'analysis.json').read_text())
    assert result['status']=='ok'
    assert all(g['peakCoreC']<=82 and g['requestedCapRangeW']==[275,275] and g['enforcedCapRangeW']==[275,275] and g['thermalViolationDeltaNanoseconds']==0 for g in a['gpu'].values())
    assert a['noiseProxy']['nonuniformSnapshots']==0 and a['noiseProxy']['peakRequestedPercent']<92
    if seconds>=1200:assert a['quietThermalQualification']=='pass',a['reasons']
    return result,a
try:
    assert c['sourceByteVerification']=='all six actual profile, source snapshots, live controller/harness and analysis linkage passed'
    trial('v2-selected-steady-c1',8192,256,1200,1,2048)
    trial('v2-selected-long-prefill',65536,32,180,1,2048)
    for n in (1,2):
        phase='v2-selected-burst-'+str(n)
        run('build-native-fixtures.py',8192,8,phase)
        run('v2-coherent-cold-burst.py',phase,'fixtures-'+phase+'.json')
        run('v2-analyze-trial.py',phase)
        assert json.loads((E/(phase+'-transition')/'result.json').read_text())['status']=='pass'
    run('v2-hot-loaded-faults.py')
    run('v2-import-receipts.py')
    receipt.update(status='pass',utcEnd=common.utc())
except BaseException as error:
    receipt.update(status='error',error=type(error).__name__+': '+str(error),utcEnd=common.utc())
    common.atomic(out/'result.json',receipt)
    common.suspend('Selected preboot qualification failed')
    raise
common.atomic(out/'result.json',receipt)
print(json.dumps({'status':receipt['status'],'phase':out.name,'utcEnd':receipt['utcEnd']}),flush=True)
