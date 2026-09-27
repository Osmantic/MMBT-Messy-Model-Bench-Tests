"""Prospective C8 thermal plateau from six complete workload cycles.

Raw v2 analyses remain unchanged. Cycle averages suppress boundary alias,
not a real heating/cooling trend; raw peaks and caps remain hard constraints.
"""
import argparse,hashlib,json,math,statistics
from pathlib import Path
def slope(points):
    x,y=zip(*points);xm=statistics.mean(x);ym=statistics.mean(y)
    den=sum((t-xm)**2 for t in x);assert den>0
    return 60*sum((t-xm)*(v-ym) for t,v in points)/den
def evaluate(result,analysis,rows,transitions=()):
    reasons=[]
    assert result['status']=='ok' and result['concurrency']==8 and result['seconds']==1800
    assert len(rows)>=170
    for row in rows:
        assert math.isfinite(row['monotonic'])
    assert all(0<b['monotonic']-a['monotonic']<=5 for a,b in zip(rows,rows[1:]))
    assert statistics.median(b['monotonic']-a['monotonic'] for a,b in zip(rows,rows[1:]))<=1.5
    waves=[w for w in result['waves'] if w['endMonotonic']<=rows[-1]['monotonic']][-6:]
    assert len(waves)==6
    assert waves[0]['startMonotonic']>=result['runStartMonotonic']+600
    span=waves[-1]['endMonotonic']-waves[0]['startMonotonic'];assert 170<=span<=240
    assert 0<=rows[-1]['monotonic']-waves[-1]['endMonotonic']<=60
    assert all(w['endMonotonic']>w['startMonotonic'] for w in waves)
    assert all(a['endMonotonic']<=b['startMonotonic'] for a,b in zip(waves,waves[1:]))
    assert all(reason.endswith(': not thermally steady') for reason in analysis['reasons']),analysis['reasons']
    gpu={};uuids=set(analysis['gpu'])
    assert len(uuids)==4
    for row in list(rows)+list(transitions):
        assert len(row['gpus'])==4 and {g['uuid'] for g in row['gpus']}==uuids
        for g in row['gpus']:
            assert g['requestedPowerW']==g['enforcedPowerW']==275
            assert type(g['coreC']) in (int,float) and math.isfinite(g['coreC']) and 0<=g['coreC']<=82
    assert analysis['noiseProxy']['nonuniformSnapshots']==0 and analysis['noiseProxy']['peakRequestedPercent']<92
    for uuid in sorted(uuids):
        assert analysis['gpu'][uuid]['thermalViolationDeltaNanoseconds']==0
        points=[];cycles=[]
        for wave in waves:
            integral=coverage=0
            for left,right in zip(rows,rows[1:]):
                lo=max(left['monotonic'],wave['startMonotonic']);hi=min(right['monotonic'],wave['endMonotonic'])
                if hi>lo:
                    value=next(g['coreC'] for g in left['gpus'] if g['uuid']==uuid)
                    integral+=value*(hi-lo);coverage+=hi-lo
            duration=wave['endMonotonic']-wave['startMonotonic'];assert coverage>=.95*duration
            mean=integral/coverage;mid=(wave['startMonotonic']+wave['endMonotonic'])/2
            points.append((mid,mean));cycles.append({'meanCoreC':mean,'coverageSeconds':coverage,'durationSeconds':duration,'midpointMonotonic':mid})
        trend=slope(points)
        if abs(trend)>.3:reasons.append(uuid+': complete-cycle trend exceeds0.3C/min')
        gpu[uuid]={'completeCycleSlopeCPerMinute':trend,'cycles':cycles,'originalRaw180SlopeCPerMinute':analysis['gpu'][uuid]['steadySlopeCPerMinute']}
    return {'status':'pass' if not reasons else 'not-qualified','reasons':reasons,'method':'last six complete C8 wave time-weighted means; absolute slope<=0.3C/min, span170..240s, all raw peaks<=82C and caps275','cycleSpanSeconds':span,'rawQualificationUnchanged':analysis['quietThermalQualification'],'rawReasonsRetained':analysis['reasons'],'gpu':gpu}
def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('phase');a=p.parse_args();assert Path(a.phase).name==a.phase
    out=a.root/a.phase;raw=(out/'analysis.json').read_bytes();result=json.loads((out/'result.json').read_text());rows=[json.loads(line) for line in (out/'telemetry.jsonl').read_text().splitlines()]
    transition=out/'fan-transitions.jsonl';tr=[json.loads(line)['sample'] for line in transition.read_text().splitlines()] if transition.exists() else []
    receipt=evaluate(result,json.loads(raw),rows,tr);receipt.update(phase=a.phase,originalAnalysisSha256=hashlib.sha256(raw).hexdigest(),analysisSourceSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'plateau-analysis.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
if __name__=='__main__':main()
