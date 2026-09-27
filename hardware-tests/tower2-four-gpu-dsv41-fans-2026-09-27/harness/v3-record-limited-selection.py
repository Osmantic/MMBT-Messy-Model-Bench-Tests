"""Retain failed eligibility, verify all six source bytes, select for durability only.

The unchanged formal comparer cannot accept a thermally ineligible run. This
separate receipt reports descriptive intervals without promoting that run.
"""
import datetime,hashlib,importlib.util,json
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence';C=Path('/opt/mmbt/gpu-control')
def sha(p):
    assert p.is_file() and not p.is_symlink(),p
    return hashlib.sha256(p.read_bytes()).hexdigest()
module=importlib.util.spec_from_file_location('frozen_compare',B/'v3-compare-pairs.py');m=importlib.util.module_from_spec(module);module.loader.exec_module(m)
specpath=E/'v2-matched-cycle30-base80-r2-spec.json';spec=json.loads(specpath.read_text())
assert sha(specpath)=='104598321638316d500040f662444dae89c51bd67cbd0f697d0c1067765a1474'
assert sha(B/'v3-compare-pairs.py')==spec['comparisonSourceSha256']
assert sha(B/'v3-temperature-plateau.py')==spec['plateauSourceSha256']
records=[];sources=None;runtime=None;boot=None;fixtures=set();candidate=None;eligibility=[]
for index,pair in enumerate(spec['pairs']):
    row={}
    for role in ('candidate','reference'):
        name=pair[role];assert Path(name).name==name
        folder=E/name;r=json.loads((folder/'result.json').read_text());a=json.loads((folder/'analysis.json').read_text());p=json.loads((folder/'plateau-analysis.json').read_text())
        assert r['status']=='ok' and r['seconds']==1800 and r['inputTokens']==8192 and r['budget']==2048 and r['concurrency']==8 and not r['allowRecoveryFaults']
        assert sha(folder/'profile.json')==r['profileSha256']
        assert sha(folder/'analysis.json')==p['originalAnalysisSha256'] and p['analysisSourceSha256']==spec['plateauSourceSha256']
        assert sha(B/'v2-analyze-trial.py')==a['analysisSourceSha256']
        if sources is None:sources=r['sources']
        assert sources==r['sources']
        for filename,pin in r['sources'].items():
            assert Path(filename).name==filename and sha(folder/'sources'/filename)==pin
            live=C/filename if (C/filename).is_file() else B/filename
            assert sha(live)==pin,filename
        identity=m.runtime_identity(r['runtime'])
        if runtime is None:runtime=identity
        assert runtime==identity
        if boot is None:boot=r['bootId']
        assert boot==r['bootId']
        assert r['fixtureSha256'] not in fixtures;fixtures.add(r['fixtureSha256'])
        profile=json.loads((folder/'profile.json').read_text())
        if role=='reference':assert profile=={'power_limit_w':275,'mode':'fixed','fixed_percent':85}
        else:
            if candidate is None:candidate=r['profileSha256']
            assert candidate==r['profileSha256']
        assert all(g['peakCoreC']<=82 and g['requestedCapRangeW']==[275,275] and g['enforcedCapRangeW']==[275,275] and g['thermalViolationDeltaNanoseconds']==0 for g in a['gpu'].values())
        assert a['warmDecode600']['windowDurationSeconds']==600 and a['warmDecode600']['seconds']>=300
        assert a['noiseProxy']['nonuniformSnapshots']==0 and a['noiseProxy']['peakRequestedPercent']<92
        eligibility.append({'phase':name,'status':p['status'],'reasons':p['reasons'],'resultSha256':sha(folder/'result.json'),'analysisSha256':sha(folder/'analysis.json'),'plateauSha256':sha(folder/'plateau-analysis.json'),'profileSha256':r['profileSha256']})
        row[role]={'result':r,'analysis':a,'phase':name}
    first=min(row,key=lambda role:row[role]['result']['utcStart']);last='reference' if first=='candidate' else 'candidate'
    assert first==('candidate' if index==1 else 'reference') and row[first]['result']['utcEnd']<=row[last]['result']['utcStart']
    records.append(row)
assert candidate==sha(Path('/etc/mmbt/gpu-profile.json'))=='2881a6d108a4c9a145b7c97a1f2cefd72f94a5be403cda356147fdbea518f7f6'
assert len([p for p in eligibility if p['status']!='pass'])==1
metrics={name:m.interval([extract(p['candidate']['analysis']) for p in records],[extract(p['reference']['analysis']) for p in records]) for name,extract in [('warmSimultaneousDecode600',lambda a:a['warmDecode600']['aggregateTokensPerSecond']),('endToEnd',lambda a:a['e2eOutputTokensPerSecond'])]}
for value in metrics.values():value.update(descriptiveOnly=True,formalQualification=False)
receipt={'status':'selected-with-performance-uncertainty','formalComparisonStatus':'not-qualified','formalPerformanceClaimAccepted':False,'thermalEquilibriumClaimAccepted':False,'selectionPurpose':'Unchanged base80 curve for independent workload, hot-fault, update, reboot and soak validation; no further matched repetitions under this amendment.','reason':'Bounded replacement exhausted; last candidate cooled faster than the predeclared absolute plateau limit. Original failed labels remain unchanged. Plan section4 requires reporting unresolved uncertainty.','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'specSha256':sha(specpath),'specFile':specpath.name,'candidateProfileSha256':candidate,'bootId':boot,'sources':sources,'runtime':runtime,'metrics':metrics,'eligibility':eligibility,'pairs':spec['pairs'],'sourceByteVerification':'all six actual profile, source snapshots, live controller/harness and analysis linkage passed','limitations':['Intervals include a thermally ineligible thirdcandidate and are descriptive, not a formal noninferiority proof.','Only two pairs satisfied plateau eligibility.','Replacement is eligibility-conditioned; inlet temperature is unmeasured.','Global quietest or best-performance optimum is not established.'],'sourceSha256':sha(Path(__file__))}
path=E/'v2-selected-base80-review.json';assert not path.exists();path.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'path':str(path),'sha256':sha(path),'status':receipt['status'],'metrics':metrics,'failedEligibility':[p for p in eligibility if p['status']!='pass']}))
