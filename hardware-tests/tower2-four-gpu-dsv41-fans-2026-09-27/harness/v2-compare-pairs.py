"""Predeclared three-pair performance/noninferiority analysis, CPU only.

Compare actual aggregate decode and end-to-end rates. The experimental unit
is the matched pair, not every token or request. Small-n uncertainty remains
visible, with a two-sided 95% Student-t interval on paired log rate ratios.
"""
import argparse, datetime, hashlib, json, math, statistics
from pathlib import Path

T95_DF2=4.302652729911275

def runtime_identity(runtime):
    # OpenAI-compatible model listing creation times are query-time metadata.
    r=json.loads(json.dumps(runtime))
    for item in r['verifiedModels']['data']:item.pop('created',None)
    return r

def interval(candidate,reference):
    assert len(candidate)==len(reference)==3
    logs=[]
    for c,r in zip(candidate,reference):
        assert type(c) in (int,float) and type(r) in (int,float) and math.isfinite(c) and math.isfinite(r) and min(c,r)>0
        logs.append(math.log(c/r))
    mean=statistics.mean(logs);half=T95_DF2*statistics.stdev(logs)/math.sqrt(3)
    return {'ratios':[math.exp(v) for v in logs],'geometricMeanRatio':math.exp(mean),'twoSided95PercentLower':math.exp(mean-half),'twoSided95PercentUpper':math.exp(mean+half),'experimentalUnits':3,'method':'paired log rate ratio, Student t, df=2','minimumAcceptableRatio':.97,'noninferiorityQualified':math.exp(mean-half)>=.97}

def compare(root,spec):
    assert len(spec['pairs'])==3 and spec['referenceProfile']=='fixed85'
    records=[];phases=set();source_pin=None;candidate_pin=None;runtime_pin=None;boot_pin=None;fixtures=set()
    for i,pair in enumerate(spec['pairs']):
        checked=[]
        for role in ('candidate','reference'):
            name=pair[role];assert Path(name).name==name and name not in phases;phases.add(name)
            out=root/name;result=json.loads((out/'result.json').read_text());analysis=json.loads((out/'analysis.json').read_text());profile=json.loads((out/'profile.json').read_text())
            assert result['status']=='ok' and analysis['quietThermalQualification']=='pass',(name,analysis['reasons'])
            assert all(g['requestedCapRangeW']==[275,275] and g['enforcedCapRangeW']==[275,275] for g in analysis['gpu'].values()),'Matched caps differed from275W'
            assert result['seconds']==1200 and result['inputTokens']==8192 and result['budget']==2048 and result['concurrency']==8 and not result['allowRecoveryFaults']
            assert result['fixtureSha256'] not in fixtures;fixtures.add(result['fixtureSha256'])
            # Profile snapshots are included separately; all executable sources match.
            if source_pin is None:source_pin=result['sources']
            assert result['sources']==source_pin,'Executable source mismatch'
            identity=runtime_identity(result['runtime'])
            if runtime_pin is None:runtime_pin=identity
            assert identity==runtime_pin,'Native runtime mismatch'
            if boot_pin is None:boot_pin=result['bootId']
            assert result['bootId']==boot_pin,'Matched series crossed a reboot'
            if role=='reference':assert profile=={'power_limit_w':275,'mode':'fixed','fixed_percent':85}
            else:
                if candidate_pin is None:candidate_pin=result['profileSha256']
                assert result['profileSha256']==candidate_pin,'Candidate changed during paired qualification'
            checked.append({'role':role,'phase':name,'result':result,'analysis':analysis})
        c,r=checked
        expected='candidate' if i==1 else 'reference'
        first=min(checked,key=lambda item:item['result']['utcStart'])
        assert first['role']==expected,'Counterbalanced order was not followed'
        # The two runs may not overlap; a pause between them is allowed.
        later=max(checked,key=lambda item:item['result']['utcStart'])
        assert first['result']['utcEnd']<=later['result']['utcStart'],'Runs overlapped'
        records.append({'candidate':c,'reference':r})
    metrics={}
    for p in records:
        for role in ('candidate','reference'):
            a=p[role]['analysis'];assert a['warmDecode600']['windowDurationSeconds']==600 and a['warmDecode600']['seconds']>=300
    for name,extract in [('warmSimultaneousDecode600',lambda a:a['warmDecode600']['aggregateTokensPerSecond']),('endToEnd',lambda a:a['e2eOutputTokensPerSecond'])]:
        metrics[name]=interval([extract(p['candidate']['analysis']) for p in records],[extract(p['reference']['analysis']) for p in records])
    noise=[p['candidate']['analysis']['noiseProxy'] for p in records]
    quiet=all(a['steady600CoverageSeconds']>=590 and a['steady600RequestedPercent']<85 for a in noise)
    return {'status':'qualified' if quiet and all(v['noninferiorityQualified'] for v in metrics.values()) else 'not-qualified','scope':'three matched counterbalanced C8 exact8k/2k pairs on one host and boot, final600s simultaneous decode after at least10min warmup, unmeasured inlet conditions','metrics':metrics,'candidateProfileSha256':candidate_pin,'candidateNoiseProxyByPair':noise,'quieterThan85Reference':quiet,'limitations':['Fan percentage is the owner-selected relative noise proxy; no dBA claim.','The confidence interval assumes independent paired log-ratio errors; three pairs cannot validate that distribution.','Paging and host variation remain recorded conditions, rather than isolated GPU effects.'],'pairs':[{'candidate':p['candidate']['phase'],'reference':p['reference']['phase'],'candidatePaging':p['candidate']['analysis']['paging'],'referencePaging':p['reference']['analysis']['paging'],'candidateFinal180Decode':p['candidate']['analysis']['steadyDecode'],'referenceFinal180Decode':p['reference']['analysis']['steadyDecode']} for p in records]}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('spec',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    raw=a.spec.read_bytes();result=compare(a.root,json.loads(raw));result['specSha256']=hashlib.sha256(raw).hexdigest();result['utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
