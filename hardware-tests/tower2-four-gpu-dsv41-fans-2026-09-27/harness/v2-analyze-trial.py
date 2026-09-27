"""CPU analysis of native completed traces; no hardware actuation."""
import argparse,hashlib,json,math,statistics,sys
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');sys.path.insert(0,'/opt/mmbt/gpu-control');sys.path.insert(0,str(B));from common import UUIDS
from native_sse_parser import parse_sse
def checked_stream(stream):
    ids=stream['finalOutputIds'];events=stream['events'];assert events
    def lines():
        for i,e in enumerate(events):
            n=e['cumulativeTokens'];raw={}
            if n is not None:
                assert type(n) is int and 0<=n<=len(ids)
                raw['output_ids']=ids[:n]
            if i==len(events)-1:raw['meta_info']=stream['finalMetaInfo']
            yield (e['t'],('data:'+json.dumps(raw)).encode())
        yield (events[-1]['t'],b'data: [DONE]')
    parsed=parse_sse(lines())
    assert parsed['final_output_ids']==ids and parsed['final_meta_info']==stream['finalMetaInfo']
    return stream
def slope(rows,key):
    x=[r[0] for r in rows];y=[r[1] for r in rows];xm=statistics.mean(x);ym=statistics.mean(y);den=sum((v-xm)**2 for v in x)
    return 60*sum((a-xm)*(b-ym) for a,b in zip(x,y))/den if den else None
def analyze(out):
    result=json.loads((out/'result.json').read_text());samples=[json.loads(line) for line in (out/'telemetry.jsonl').read_text().splitlines()];assert len(samples)>=2
    end=samples[-1]['monotonic'];begin=end-180;steady=[r for r in samples if r['monotonic']>=begin];gaps=[b['monotonic']-a['monotonic'] for a,b in zip(steady,steady[1:])];reasons=[]
    if result['status']!='ok':reasons.append('Trial did not complete')
    if result['seconds']<1200:reasons.append('Shorter than20-minute screen')
    if len(steady)<170 or steady[-1]['monotonic']-steady[0]['monotonic']<170 or max(gaps)>5 or statistics.median(gaps)>1.5:reasons.append('Insufficient steady telemetry coverage')
    transition_path=out/'fan-transitions.jsonl'
    raw_transitions=[json.loads(line) for line in transition_path.read_text().splitlines()] if transition_path.exists() else []
    raw_samples=[r['sample'] for r in raw_transitions]
    for r in raw_samples:
        assert {g['uuid'] for g in r['gpus']}==UUIDS and len(r['gpus'])==4
        assert all(g['requestedPowerW']==275 and 150<=g['enforcedPowerW']<=275 for g in r['gpus'])
    gpu={};fanchanges=0;lasttarget=None;time_total=0;target_integral=0;actual_integral=0;targets=[];mixed=0
    for i,r in enumerate(samples):
        assert {g['uuid'] for g in r['gpus']}==UUIDS and len(r['gpus'])==4
        assert all(g['requestedPowerW']==275 and 150<=g['enforcedPowerW']<=275 for g in r['gpus'])
        fans=[f for g in r['gpus'] for f in g['fans']];assert len(fans)==8
        ts={f['target'] for f in fans};mixed+=len(ts)!=1 or any(f['policy']!=1 for f in fans)
        target=r.get('primary',{}).get('targetPercent') if r.get('primary') else None
        if target is not None:
            targets.append(target)
            if lasttarget is not None and lasttarget!=target:fanchanges+=1
            lasttarget=target
            if i<len(samples)-1:
                dt=samples[i+1]['monotonic']-r['monotonic'];assert 0<dt<=5
                time_total+=dt;target_integral+=target*dt;actual_integral+=statistics.mean(f['current'] for f in fans)*dt
    for u in sorted(UUIDS):
        alltemps=[g['coreC'] for r in samples+raw_samples for g in r['gpus'] if g['uuid']==u];ss=[(r['monotonic'],g['coreC']) for r in steady for g in r['gpus'] if g['uuid']==u];s=slope(ss,u)
        observations=[g for r in samples for g in r['gpus'] if g['uuid']==u]
        powers=[g['powerW'] for g in observations if type(g.get('powerW')) in (int,float)];clocks=[g['smClockMHz'] for g in observations if type(g.get('smClockMHz')) in (int,float)]
        masks=[g['clockEventMask'] for g in observations if type(g.get('clockEventMask')) is int]
        gpu[u]={'peakCoreC':max(alltemps),'steadyMeanCoreC':statistics.mean(v for t,v in ss),'steadyMinCoreC':min(v for t,v in ss),'steadyMaxCoreC':max(v for t,v in ss),'steadySlopeCPerMinute':s,'reportedPeakPowerW':max(powers) if powers else None,'smClockMedianMHz':statistics.median(clocks) if clocks else None,'observedClockEventMasks':sorted(set(masks))}
        cap_observations=observations+[g for r in raw_samples for g in r['gpus'] if g['uuid']==u]
        gpu[u]['requestedCapRangeW']=[min(g['requestedPowerW'] for g in cap_observations),max(g['requestedPowerW'] for g in cap_observations)]
        gpu[u]['enforcedCapRangeW']=[min(g['enforcedPowerW'] for g in cap_observations),max(g['enforcedPowerW'] for g in cap_observations)]
        for name in ('thermalViolation','powerViolation'):
            values=[g[name]['violationTimeNanoseconds'] for g in observations if isinstance(g.get(name),dict) and 'violationTimeNanoseconds' in g[name]]
            gpu[u][name+'DeltaNanoseconds']=values[-1]-values[0] if len(values)>=2 else None
        if max(alltemps)>82:reasons.append(u+': exceeded82C')
        if s is None or abs(s)>.3:reasons.append(u+': not thermally steady')
    if mixed:reasons.append('Nonuniform/manual snapshots require review: '+str(mixed))
    cfg=json.loads((out/'profile.json').read_text())
    if cfg['mode']=='fixed' and any(v!=cfg['fixed_percent'] for v in targets):reasons.append('Fixed profile needed protective override')
    if any(v>=92 for v in targets):reasons.append('Emergency cooling needed')
    decode_tokens=0;decode_seconds=0;warm_tokens=0;warm_seconds=0;ttfts=[];latencies=[]
    for w in result['waves']:
        streams=[checked_stream(json.loads((out/(out.name+'-r'+str(request['index'])+'.delivery.json')).read_text())) for request in w['requests']]
        positives=[]
        for stream in streams:
            p=[];prev=0
            for e in stream['events']:
                n=e['cumulativeTokens']
                if n is None:continue
                assert n>=prev
                if n>prev:p.append((w['startMonotonic']+e['t'],n-prev))
                prev=n
            assert p and prev==result['budget'];positives.append(p)
            ttfts.append(stream['firstTokenSeconds']);latencies.append(stream['latencySeconds'])
        a=max(begin,max(p[0][0] for p in positives));b=min(end,min(p[-1][0] for p in positives))
        if b>a:
            decode_seconds+=b-a;decode_tokens+=sum(delta for p in positives for t,delta in p if a<t<=b)
        wa=max(end-600,max(p[0][0] for p in positives));wb=min(end,min(p[-1][0] for p in positives))
        if wb>wa:
            warm_seconds+=wb-wa;warm_tokens+=sum(delta for p in positives for t,delta in p if wa<t<=wb)
    if decode_seconds<60:reasons.append('Steady simultaneous decode coverage below60s')
    hostfirst=samples[0]['host'];hostlast=samples[-1]['host']
    processfirst={p['pid']:p for p in samples[0]['modelProcesses'] if 'majorFaults' in p};processlast={p['pid']:p for p in samples[-1]['modelProcesses'] if 'majorFaults' in p}
    model_faults={str(pid):processlast[pid]['majorFaults']-row['majorFaults'] for pid,row in processfirst.items() if pid in processlast}
    def quantile(values,q):return sorted(values)[min(len(values)-1,math.ceil(q*len(values))-1)]
    summary={'phase':out.name,'quietThermalQualification':'pass' if not reasons else 'not-qualified','reasons':reasons,'gpu':gpu,'noiseProxy':{'timeWeightedRequestedPercent':target_integral/time_total if time_total else None,'timeWeightedActualEightFanMeanPercent':actual_integral/time_total if time_total else None,'peakRequestedPercent':max(targets) if targets else None,'commandChangesPerMinute':fanchanges/((end-samples[0]['monotonic'])/60),'nonuniformSnapshots':mixed},'steadyDecode':{'tokens':decode_tokens,'seconds':decode_seconds,'aggregateTokensPerSecond':decode_tokens/decode_seconds if decode_seconds else None},'e2eOutputTokensPerSecond':result.get('e2eOutputTokensPerSecond'),'ttftMedianSeconds':statistics.median(ttfts),'ttftP95Seconds':quantile(ttfts,.95),'latencyMedianSeconds':statistics.median(latencies),'latencyP95Seconds':quantile(latencies,.95),'paging':{'wholeHostSwapInBytes':(hostlast['pswpin']-hostfirst['pswpin'])*hostfirst['pageBytes'],'wholeHostSwapOutBytes':(hostlast['pswpout']-hostfirst['pswpout'])*hostfirst['pageBytes'],'modelProcessMetricsRecorded':True,'attribution':'Process major-fault and VmSwap observations available; aggregate host traffic alone does not establish model attribution'},'ambientTemperatureC':None,'thermalPerformanceComparisonPending':True,'elapsedSeconds':end-samples[0]['monotonic'],'minimumAvailableGiB':min(r['host']['memAvailableBytes'] for r in samples)/2**30}
    summary['paging']['modelMajorFaultDeltaByPid']=model_faults
    summary['paging']['sameModelProcessSetObserved']=set(processfirst)==set(processlast)
    summary['paging']['modelPrivateSwapStartBytes']=sum(p.get('VmSwap',0) for p in processfirst.values())
    summary['paging']['modelPrivateSwapEndBytes']=sum(p.get('VmSwap',0) for p in processlast.values())
    summary['warmDecode600']={'tokens':warm_tokens,'seconds':warm_seconds,'aggregateTokensPerSecond':warm_tokens/warm_seconds if warm_seconds else None,'windowDurationSeconds':600,'minimumComparisonCoverageSeconds':300,'prefillAndDrainGapsExcluded':True}
    summary['analysisSourceSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    summary['fanObservationMethod']={'accepted':'bounded coherent readback when recorded; older raw snapshots retained unchanged','transitionBudgetSeconds':.25,'retainedRejectedRawObservations':len(raw_samples),'rawMixedTargetSnapshots':sum(len({f['target'] for g in r['gpus'] for f in g['fans']})!=1 for r in raw_samples),'rawTransitionTemperaturesIncludedInPeak':True,'unresolvedMismatchFailsTrial':True}
    summary['fanReadbackMeaning']='Historical Actual fields mean NVML-reported operating speed, not independent physical tachometry'
    fan_seconds=fan_requested=fan_reported=0
    for left,right in zip(samples,samples[1:]):
        a=max(end-600,left['monotonic']);b=min(end,right['monotonic'])
        if b>a:
            dt=b-a;fan_seconds+=dt
            fan_requested+=left['primary']['targetPercent']*dt
            fan_reported+=statistics.mean(f['current'] for g in left['gpus'] for f in g['fans'])*dt
    summary['noiseProxy']['steady600RequestedPercent']=fan_requested/fan_seconds if fan_seconds else None
    summary['noiseProxy']['steady600ReportedPercent']=fan_reported/fan_seconds if fan_seconds else None
    summary['noiseProxy']['steady600CoverageSeconds']=fan_seconds
    (out/'analysis.json').write_text(json.dumps(summary,indent=2));return summary
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase');a=p.parse_args();assert Path(a.phase).name==a.phase
    print(json.dumps(analyze(B/'evidence'/a.phase),indent=2))
