"""Prospectively repeat a thermally ineligible third pair; retain its record.

The first two valid pairs and every acceptance threshold remain unchanged.
"""
import hashlib,json,subprocess,sys
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence'
old=E/'v2-matched-lower2-spec.json';spec=json.loads(old.read_text())
failed=E/spec['pairs'][2]['reference'];a=json.loads((failed/'analysis.json').read_text())
assert a['quietThermalQualification']=='not-qualified' and a['reasons'] and all(reason.endswith(': not thermally steady') for reason in a['reasons'])
assert json.loads((failed/'result.json').read_text())['status']=='ok'
assert all(g['peakCoreC']<=82 and g['requestedCapRangeW']==[275,275] and g['enforcedCapRangeW']==[275,275] and g['thermalViolationDeltaNanoseconds']==0 for g in a['gpu'].values())
assert not (E/spec['pairs'][2]['candidate']).exists()
for pair in spec['pairs'][:2]:
    for name in pair.values():assert json.loads((E/name/'analysis.json').read_text())['quietThermalQualification']=='pass'
spec['pairs'][2]={'reference':'v2-matched-lower2-r2-p3-ref85','candidate':'v2-matched-lower2-r2-p3-candidate'}
spec['amendment']={'originalSpecSha256':hashlib.sha256(old.read_bytes()).hexdigest(),'retainedPairs':[1,2],'excludedReference':failed.name,'excludedAnalysisSha256':hashlib.sha256((failed/'analysis.json').read_bytes()).hexdigest(),'reason':a['reasons'],'decision':'Repeat entire third pair with new fixtures, before any third candidate data; retain original failed reference. No thresholds, source, runtime, boot or accepted pair results change.','repetitionLimit':1}
new=E/'v2-matched-lower2-r2-spec.json';assert not new.exists();new.write_text(json.dumps(spec,indent=2)+'\n')
rejection=E/'v2-matched-lower2-thermal-rejection';rejection.mkdir()
(rejection/'result.json').write_text(json.dumps({'status':'not-qualified','originalSeries':'v2-matched-lower2','failedPhase':failed.name,'reasons':a['reasons'],'replacementSpec':new.name,'originalFailedTraceRetained':True},indent=2)+'\n')
print(json.dumps({'prospectiveAmendedSpec':new.name,'sha256':hashlib.sha256(new.read_bytes()).hexdigest(),'excludedReference':failed.name}),flush=True)
for role in ('reference','candidate'):
    profile='fixed85' if role=='reference' else 'lower2'
    command=[sys.executable,str(B/'v2-run-screen.py'),profile,spec['pairs'][2][role]]
    if role=='candidate':command+=['--startup-floor','65','--startup-seconds','15']
    subprocess.run(command,check=True)
    analysis=json.loads((E/spec['pairs'][2][role]/'analysis.json').read_text())
    assert analysis['quietThermalQualification']=='pass',analysis['reasons']
subprocess.run([sys.executable,str(B/'v2-compare-pairs.py'),str(E),str(new),str(E/'v2-matched-lower2-r2-comparison.json')],check=True)
