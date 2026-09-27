"""Thermal/noise and replenishment qualification of continuous native traces."""
import argparse, importlib.util, json, math, statistics
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926')
spec=importlib.util.spec_from_file_location('cohort_analysis',B/'v2-analyze-trial.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def occupancy(streams,begin,end):
    assert end>begin
    edges=[]
    for s in streams:
        a=s['requestStartMonotonic'];b=s['httpEndMonotonic']
        assert type(a) in (int,float) and type(b) in (int,float) and math.isfinite(a) and math.isfinite(b) and 0<b-a<=125
        if b>begin and a<end:edges.extend([(max(begin,a),1),(min(end,b),-1)])
    count=0;previous=begin;integral=0;full=0;peak=0
    for stamp,delta in sorted(edges):
        dt=stamp-previous;assert dt>=0
        integral+=count*dt
        if count==8:full+=dt
        count+=delta;peak=max(peak,count);assert count>=0;previous=stamp
    assert count==0
    return {'meanHttpConcurrency':integral/(end-begin),'fractionWithEightHttpStreams':full/(end-begin),'peakHttpConcurrency':peak,'windowSeconds':end-begin}

def analyze(out):
    result=json.loads((out/'result.json').read_text());samples=[json.loads(line) for line in (out/'telemetry.jsonl').read_text().splitlines()];reasons=[]
    if result['status']!='ok':reasons.append('Trial did not complete')
    deadline=result['runStartMonotonic']+result['seconds'];rows=[r for r in samples if r['monotonic']<=deadline];begin=max(result['runStartMonotonic'],deadline-180);steady=[r for r in rows if r['monotonic']>=begin]
    gaps=[b['monotonic']-a['monotonic'] for a,b in zip(steady,steady[1:])]
    if result['seconds']<1200:reasons.append('Pilot shorter than20 minutes')
    if len(steady)<170 or not gaps or steady[-1]['monotonic']-steady[0]['monotonic']<170 or max(gaps)>5 or statistics.median(gaps)>1.5:reasons.append('Insufficient steady coverage')
    transition_path=out/'fan-transitions.jsonl'
    raw_transitions=[json.loads(line) for line in transition_path.read_text().splitlines()] if transition_path.exists() else []
    raw_samples=[r['sample'] for r in raw_transitions]
    for r in raw_samples:
        assert {g['uuid'] for g in r['gpus']}==m.UUIDS and len(r['gpus'])==4
        assert all(g['requestedPowerW']==275 and 150<=g['enforcedPowerW']<=275 for g in r['gpus'])
    gpu={};mixed=0;targets=[];target_integral=0;reported_integral=0;duration=0;changes=0;previous=None
    for i,r in enumerate(rows):
        assert {g['uuid'] for g in r['gpus']}==m.UUIDS and len(r['gpus'])==4
        assert all(g['requestedPowerW']==275 and 150<=g['enforcedPowerW']<=275 for g in r['gpus'])
        fans=[f for g in r['gpus'] for f in g['fans']];assert len(fans)==8
        target=r['primary']['targetPercent'];targets.append(target);mixed+=len({f['target'] for f in fans})!=1 or any(f['policy']!=1 for f in fans)
        if previous is not None and previous!=target:changes+=1
        previous=target
        if i<len(rows)-1:
            dt=rows[i+1]['monotonic']-r['monotonic'];assert 0<dt<=5
            duration+=dt;target_integral+=target*dt;reported_integral+=statistics.mean(f['current'] for f in fans)*dt
    for u in sorted(m.UUIDS):
        temps=[g['coreC'] for r in samples+raw_samples for g in r['gpus'] if g['uuid']==u];ss=[(r['monotonic'],g['coreC']) for r in steady for g in r['gpus'] if g['uuid']==u]
        slope=m.slope(ss,u) if len(ss)>1 else None
        gpu[u]={'peakCoreCIncludingDrain':max(temps),'steadyMeanCoreC':statistics.mean(v for t,v in ss) if ss else None,'steadySlopeCPerMinute':slope}
        observations=[g for r in samples for g in r['gpus'] if g['uuid']==u]
        all_caps=observations+[g for r in raw_samples for g in r['gpus'] if g['uuid']==u]
        gpu[u]['requestedCapRangeW']=[min(g['requestedPowerW'] for g in all_caps),max(g['requestedPowerW'] for g in all_caps)]
        gpu[u]['enforcedCapRangeW']=[min(g['enforcedPowerW'] for g in all_caps),max(g['enforcedPowerW'] for g in all_caps)]
        for name in ('smClockMHz','memoryClockMHz','powerW'):
            values=[g[name] for g in observations if type(g.get(name)) in (int,float)]
            gpu[u][name+'Median']=statistics.median(values) if values else None
        gpu[u]['observedClockEventMasks']=sorted({g['clockEventMask'] for g in observations if type(g.get('clockEventMask')) is int})
        for name in ('thermalViolation','powerViolation'):
            values=[g[name]['violationTimeNanoseconds'] for g in observations if isinstance(g.get(name),dict) and 'violationTimeNanoseconds' in g[name]]
            gpu[u][name+'DeltaNanoseconds']=values[-1]-values[0] if len(values)>=2 else None
        if max(temps)>82:reasons.append(u+': exceeded82C')
        if slope is None or abs(slope)>.3:reasons.append(u+': not thermally steady')
    if mixed:reasons.append('Nonuniform/manual snapshots: '+str(mixed))
    if max(targets)>=92:reasons.append('Emergency cooling needed')
    streams={};delivered=0;ttfts=[];latencies=[]
    for record in result['requests']:
        index=record['index'];s=m.checked_stream(json.loads((out/(out.name+'-r'+str(index)+'.delivery.json')).read_text()));streams[index]=s
        assert len(s['finalOutputIds'])==result['budget'] and s['finalMetaInfo']['prompt_tokens']==result['inputTokens']
        previous=0
        for event in s['events']:
            count=event['cumulativeTokens']
            if count is None:continue
            absolute=result['runStartMonotonic']+event['t']
            if begin<absolute<=deadline:delivered+=count-previous
            previous=count
        ttfts.append(s['firstTokenSeconds']);latencies.append(s['latencySeconds'])
    assert len(streams)==result['callsComplete']==len(result['dispatches'])==len(result['httpCompletions'])
    assert result['outputTokens']==len(streams)*result['budget']
    delays=[]
    for completion,dispatch in zip(result['httpCompletions'],result['dispatches'][8:]):
        assert completion['observedMonotonic']<deadline
        delay=dispatch['monotonic']-streams[completion['index']]['httpEndMonotonic'];assert math.isfinite(delay) and delay>=0;delays.append(delay)
    def q(values,quantile):return sorted(values)[min(len(values)-1,math.ceil(quantile*len(values))-1)]
    replenishment={'replacements':len(delays),'p95Seconds':q(delays,.95) if delays else None,'maximumSeconds':max(delays) if delays else None,'proof':'each HTTP EOF replenished before its recorder completes; eight HTTP streams targeted, at most sixteen total worker jobs'}
    if not delays or max(delays)>1 or q(delays,.95)>.25:reasons.append('Replenishment latency exceeds prospective bound')
    serving=occupancy(streams.values(),max(result['runStartMonotonic'],begin),deadline)
    if serving['meanHttpConcurrency']<7.5 or serving['peakHttpConcurrency']>8:reasons.append('Continuous C8 occupancy not established')
    from rolling_decode import measure
    summary={'phase':out.name,'quietContinuousQualification':'pass' if not reasons else 'not-qualified','reasons':reasons,'gpu':gpu,'noiseProxy':{'timeWeightedRequestedPercent':target_integral/duration if duration else None,'timeWeightedReportedEightFanMeanPercent':reported_integral/duration if duration else None,'peakRequestedPercent':max(targets),'commandChangesPerMinute':changes/(duration/60),'nonuniformSnapshots':mixed},'replenishment':replenishment,'steadyHttpOccupancy':serving,'steadyDeliveredTokensPerSecond':delivered/(deadline-begin),'deliveryWindowSeconds':deadline-begin,'steadyRateMeaning':'recorded deliveries in up-to-final180s before dispatch deadline, includes serving/prefill mix; not matched-cohort simultaneous decode','e2eOutputTokensPerSecond':result.get('e2eOutputTokensPerSecond'),'ttftMedianSeconds':statistics.median(ttfts) if ttfts else None,'latencyMedianSeconds':statistics.median(latencies) if latencies else None,'minimumAvailableGiB':min(r['host']['memAvailableBytes'] for r in samples)/2**30,'ambientTemperatureC':None,'soakDurationQualified':result['seconds']>=7200,'performanceComparisonPending':True}
    summary['simultaneousDecode180']=measure(streams.values(),result['runStartMonotonic'],begin,deadline,8)
    summary['simultaneousDecode600']=measure(streams.values(),result['runStartMonotonic'],max(result['runStartMonotonic'],deadline-600),deadline,8)
    summary['analysisSourceSha256']=__import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest()
    summary['decodeHelperSha256']=__import__('hashlib').sha256(Path(__file__).with_name('rolling_decode.py').read_bytes()).hexdigest()
    summary['fanObservationMethod']={'transitionRetryBudgetSeconds':.25,'retainedRejectedRawObservations':len(raw_samples),'rawMixedTargetSnapshots':sum(len({f['target'] for g in r['gpus'] for f in g['fans']})!=1 for r in raw_samples),'rawTransitionTemperaturesIncludedInPeak':True,'unresolvedMismatchFailsTrial':True}
    fan_seconds=fan_requested=fan_reported=0
    for left,right in zip(rows,rows[1:]):
        a=max(deadline-600,left['monotonic']);b=min(deadline,right['monotonic'])
        if b>a:
            dt=b-a;fan_seconds+=dt;fan_requested+=left['primary']['targetPercent']*dt
            fan_reported+=statistics.mean(f['current'] for g in left['gpus'] for f in g['fans'])*dt
    summary['noiseProxy'].update(steady600RequestedPercent=fan_requested/fan_seconds if fan_seconds else None,steady600ReportedPercent=fan_reported/fan_seconds if fan_seconds else None,steady600CoverageSeconds=fan_seconds)
    first=samples[0]['host'];last=samples[-1]['host']
    summary['paging']={'wholeHostSwapInBytes':(last['pswpin']-first['pswpin'])*first['pageBytes'],'wholeHostSwapOutBytes':(last['pswpout']-first['pswpout'])*first['pageBytes'],'modelProcessMetricsRecorded':True}
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase');a=p.parse_args();assert Path(a.phase).name==a.phase
    out=B/'evidence'/a.phase;summary=analyze(out);(out/'analysis.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
