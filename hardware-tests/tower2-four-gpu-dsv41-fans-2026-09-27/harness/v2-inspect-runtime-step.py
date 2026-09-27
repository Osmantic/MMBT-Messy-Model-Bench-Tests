"""Descriptive covariates around observed throughput changes, CPU only."""
import argparse,json,statistics
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926')
p=argparse.ArgumentParser();p.add_argument('phase');a=p.parse_args();out=B/'evidence'/a.phase;r=json.loads((out/'result.json').read_text());rows=[json.loads(l) for l in (out/'telemetry.jsonl').read_text().splitlines()];start=r['runStartMonotonic'];result={}
for lo,hi in ((8,12),(14,17)):
    samples=[row for row in rows if lo*60<=row['monotonic']-start<hi*60]
    if not samples:continue
    gpu={}
    for u in {g['uuid'] for g in samples[0]['gpus']}:
        gs=[g for row in samples for g in row['gpus'] if g['uuid']==u]
        gpu[u[-4:]]={key:statistics.median(g[key] for g in gs if type(g.get(key)) in (int,float)) for key in ('coreC','smClockMHz','powerW','utilizationGpu','memoryClockMHz')}
    result[str(lo)+'-'+str(hi)+'minutes']={'gpuMedians':gpu,'hostLoadMean':[statistics.mean(row['host']['loadAverage'][i] for row in samples) for i in range(3)],'wholeHostSwapInBytes':(samples[-1]['host']['pswpin']-samples[0]['host']['pswpin'])*samples[0]['host']['pageBytes'],'availableGiBMinimum':min(row['host']['memAvailableBytes'] for row in samples)/2**30}
(out/'runtime-step-covariates.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
