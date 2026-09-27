"""Secondary time-weighted hottest-core bands, without changing qualification."""
import argparse,hashlib,json
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence'
def bands(samples,start,end):
    totals={k:0.0 for k in ('below75','75through80','above80through82','above82')}
    for left,right in zip(samples,samples[1:]):
        duration=min(end,right['monotonic'])-max(start,left['monotonic'])
        if duration<=0:continue
        assert right['monotonic']-left['monotonic']<=5
        hottest=max(g['coreC'] for g in left['gpus'])
        label='below75' if hottest<75 else '75through80' if hottest<=80 else 'above80through82' if hottest<=82 else 'above82'
        totals[label]+=duration
    coverage=sum(totals.values());assert coverage>0
    return {'coverageSeconds':coverage,'seconds':totals,'percent':{k:100*v/coverage for k,v in totals.items()}}
def main():
    p=argparse.ArgumentParser();p.add_argument('phase');a=p.parse_args();assert Path(a.phase).name==a.phase
    out=E/a.phase;r=json.loads((out/'result.json').read_text());assert r['status']=='ok'
    path=out/'telemetry.jsonl';raw=path.read_bytes();samples=[json.loads(s) for s in raw.splitlines()]
    end=min(samples[-1]['monotonic'],r['runStartMonotonic']+r['seconds']) if r.get('workload')=='continuous-replenishment-C8' else samples[-1]['monotonic']
    assert end-samples[0]['monotonic']>=600
    result={'phase':a.phase,'method':'Left-held time integral of hottest recorded core; accepted telemetry only; raw rejected transitions remain included in main peak analysis.','telemetrySha256':hashlib.sha256(raw).hexdigest(),'final600':bands(samples,end-600,end),'final180':bands(samples,end-180,end),'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (out/'temperature-band-summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
