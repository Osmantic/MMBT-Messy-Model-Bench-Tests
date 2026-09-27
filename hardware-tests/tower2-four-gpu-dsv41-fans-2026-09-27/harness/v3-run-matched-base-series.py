"""New prospective30min series; never reinterpret a v2 failed run."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence';series='v2-matched-cycle30-base80'
spec={'referenceProfile':'fixed85','candidateProfile':'curve','candidateStartupFloor':80,'candidateStartupSeconds':30,'runSeconds':1800,'thermalPlateauMethod':'last6completeC8cycleMeans','plateauSourceSha256':hashlib.sha256((B/'v3-temperature-plateau.py').read_bytes()).hexdigest(),'comparisonSourceSha256':hashlib.sha256((B/'v3-compare-pairs.py').read_bytes()).hexdigest(),'pairs':[{'reference':series+'-p'+str(i)+'-ref85','candidate':series+'-p'+str(i)+'-candidate'} for i in (1,2,3)],'protocolReason':'The lower2/65-percent15-second-startup candidate completed its first new30min pair with end-to-end ratio0.960035, making the declared n3 two-sided95-percent lower>=0.97 gate impossible. It also failed the prospective six-cycle top-card slope gate (+0.373758C/min), while raw180 screening passed/peak81/no thermal counters. That series terminated without a second pair. This entirely new series tests the original screened curve plus80-percent30-second startup; both configuration components are assessed together. No historical labels, sources, thresholds or throughput definitions are changed.','unchangedRequirements':['four exact275W requested/enforced caps','all raw peaks<=82C including rejected transition reads','no thermal-counter increment','uniform manual accepted samples','same boot/runtime/executable source and candidate bytes','three paired95% Student-t lower bounds>=0.97 for BOTH final600 decode and end-to-end','candidate final600 fan effort below85%']}
path=E/(series+'-spec.json');assert not path.exists();assert all(not (E/name).exists() for pair in spec['pairs'] for name in pair.values())
path.write_text(json.dumps(spec,indent=2)+'\n');print(json.dumps({'prospectiveSpec':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'runSeconds':1800,'thermalMethod':spec['thermalPlateauMethod']}),flush=True)
record_folder=E/(series+'-runner');record_folder.mkdir();record={'status':'starting','specSha256':hashlib.sha256(path.read_bytes()).hexdigest(),'completed':[]};(record_folder/'result.json').write_text(json.dumps(record))
try:
    for i,pair in enumerate(spec['pairs']):
        for role in (('candidate','reference') if i==1 else ('reference','candidate')):
            assert hashlib.sha256((B/'v3-temperature-plateau.py').read_bytes()).hexdigest()==spec['plateauSourceSha256']
            command=[sys.executable,str(B/'v2-run-screen.py'),'curve' if role=='candidate' else 'fixed85',pair[role],'--seconds','1800']
            if role=='candidate':command+=['--startup-floor','80','--startup-seconds','30']
            subprocess.run(command,check=True)
            subprocess.run([sys.executable,str(B/'v3-temperature-plateau.py'),str(E),pair[role]],check=True)
            plateau=json.loads((E/pair[role]/'plateau-analysis.json').read_text());assert plateau['status']=='pass',plateau['reasons']
            record['completed'].append(pair[role]);(record_folder/'result.json').write_text(json.dumps(record))
    assert hashlib.sha256((B/'v3-compare-pairs.py').read_bytes()).hexdigest()==spec['comparisonSourceSha256']
    subprocess.run([sys.executable,str(B/'v3-compare-pairs.py'),str(E),str(path),str(E/(series+'-comparison.json'))],check=True)
    record.update(status='complete',comparisonStatus=json.loads((E/(series+'-comparison.json')).read_text())['status'])
except BaseException as error:
    record.update(status='error',error=type(error).__name__+': '+str(error));(record_folder/'result.json').write_text(json.dumps(record));raise
(record_folder/'result.json').write_text(json.dumps(record));print(json.dumps(record),flush=True)
