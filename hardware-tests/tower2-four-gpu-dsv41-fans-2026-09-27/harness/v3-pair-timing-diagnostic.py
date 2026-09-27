"""Completed trace timing decomposition; no throughput normalization or gates."""
import argparse,hashlib,json,statistics
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence'
p=argparse.ArgumentParser();p.add_argument('phase');a=p.parse_args();assert Path(a.phase).name==a.phase
out=E/a.phase;r=json.loads((out/'result.json').read_text());assert r['status']=='ok'
analysis=json.loads((out/'analysis.json').read_text());rows=[]
for index,w in enumerate(r['waves']):
    streams=[json.loads((out/(a.phase+'-r'+str(q['index'])+'.delivery.json')).read_text()) for q in w['requests']]
    firsts=[];lasts=[]
    for s in streams:
        prior=0;positive=[]
        for event in s['events']:
            n=event['cumulativeTokens']
            if n is None:continue
            assert n>=prior
            if n>prior:positive.append(event['t'])
            prior=n
        assert prior==2048 and positive
        firsts.append(positive[0]);lasts.append(positive[-1])
    duration=w['endMonotonic']-w['startMonotonic']
    rows.append({'endMinutes':(w['endMonotonic']-r['runStartMonotonic'])/60,'waveDurationSeconds':duration,'latestFirstDeliverySeconds':max(firsts),'commonDecodeSeconds':min(lasts)-max(firsts),'allStreamsLastPositiveSeconds':max(lasts),'postLastPositiveSeconds':duration-max(lasts),'postLastRawEventSeconds':duration-max(s['events'][-1]['t'] for s in streams),'betweenWaveGapSeconds':w['startMonotonic']-r['waves'][index-1]['endMonotonic'] if index else 0,'meanSpecAcceptLength':statistics.mean(s['finalMetaInfo']['spec_accept_length'] for s in streams)})
def aggregate(selected):
    return {'waves':len(selected),**{key:statistics.mean(w[key] for w in selected) for key in rows[0] if key!='endMinutes'}}
d={'phase':a.phase,'status':'descriptive','sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'whole':aggregate(rows),'first10Minutes':aggregate([w for w in rows if w['endMinutes']<=10]),'last10Minutes':aggregate([w for w in rows if w['endMinutes']>r['totalElapsed']/60-10]),'decode600':analysis['warmDecode600'],'e2e':analysis['e2eOutputTokensPerSecond'],'ttftMedianSeconds':analysis['ttftMedianSeconds'],'ttftP95Seconds':analysis['ttftP95Seconds'],'latencyMedianSeconds':analysis['latencyMedianSeconds'],'paging':analysis['paging'],'gpu':analysis['gpu'],'waves':rows,'interpretation':'Post-delivery time includes client parsing, persistence, analysis and any final metadata wait. Recorded timing is descriptive, not isolated CPU cost or a causal thermal explanation. All declared comparison metrics and labels remain unchanged.'}
(out/'timing-diagnostic.json').write_text(json.dumps(d,indent=2)+'\n')
print(json.dumps({k:v for k,v in d.items() if k not in ('gpu','waves','paging')}))
