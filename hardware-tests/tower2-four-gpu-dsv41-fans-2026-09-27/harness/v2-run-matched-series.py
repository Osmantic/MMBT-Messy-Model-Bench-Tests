"""Execute the prospectively defined six-run series, without overlapping loads."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926')
p=argparse.ArgumentParser();p.add_argument('candidate',choices=('curve','lower1','lower2'));p.add_argument('series');a=p.parse_args()
assert a.series.startswith('v2-') and a.series.replace('-','').isalnum()
spec={'referenceProfile':'fixed85','candidateProfile':a.candidate,'candidateStartupFloor':65,'candidateStartupSeconds':15,'pairs':[{'reference':a.series+'-p'+str(i)+'-ref85','candidate':a.series+'-p'+str(i)+'-candidate'} for i in (1,2,3)]}
specpath=B/'evidence'/(a.series+'-spec.json');assert not specpath.exists()
assert all(not (B/'evidence'/name).exists() for pair in spec['pairs'] for name in pair.values())
specpath.write_text(json.dumps(spec,indent=2)+'\n')
print(json.dumps({'prospectiveSpec':str(specpath),'sha256':hashlib.sha256(specpath.read_bytes()).hexdigest(),'counterbalance':['reference/candidate','candidate/reference','reference/candidate']}),flush=True)
for i,pair in enumerate(spec['pairs']):
    for role in (('candidate','reference') if i==1 else ('reference','candidate')):
        profile=a.candidate if role=='candidate' else 'fixed85'
        args=[sys.executable,str(B/'v2-run-screen.py'),profile,pair[role]]
        if role=='candidate':args+=['--startup-floor','65','--startup-seconds','15']
        subprocess.run(args,check=True)
        analysis=json.loads((B/'evidence'/pair[role]/'analysis.json').read_text())
        assert analysis['quietThermalQualification']=='pass',(pair[role],analysis['reasons'])
subprocess.run([sys.executable,str(B/'v2-compare-pairs.py'),str(B/'evidence'),str(specpath),str(B/'evidence'/(a.series+'-comparison.json'))],check=True)
