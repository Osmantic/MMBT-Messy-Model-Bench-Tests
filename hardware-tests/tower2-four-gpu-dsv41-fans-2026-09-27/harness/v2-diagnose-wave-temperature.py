"""Descriptive phase-alias diagnostic, never changes qualification labels."""
import hashlib,json,statistics,sys
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence'
phase=sys.argv[1];assert Path(phase).name==phase
p=E/phase;r=json.loads((p/'result.json').read_text());a=json.loads((p/'analysis.json').read_text());rows=[json.loads(line) for line in (p/'telemetry.jsonl').read_text().splitlines()]
def slope(points):
    x,y=zip(*points);xm=statistics.mean(x);ym=statistics.mean(y)
    return 60*sum((t-xm)*(v-ym) for t,v in points)/sum((t-xm)**2 for t in x)
waves=[w for w in r['waves'] if w['endMonotonic']<=rows[-1]['monotonic']][-6:]
assert len(waves)==6
output={'status':'diagnostic-only','phase':phase,'originalQualificationUnchanged':a['quietThermalQualification'],'originalReasons':a['reasons'],'profileSha256':r['profileSha256'],'completeCycleSpanSeconds':waves[-1]['endMonotonic']-waves[0]['startMonotonic'],'gpu':{}}
for uuid,g in a['gpu'].items():
    points=[];means=[]
    for wave in waves:
        integral=coverage=0
        for left,right in zip(rows,rows[1:]):
            lo=max(left['monotonic'],wave['startMonotonic']);hi=min(right['monotonic'],wave['endMonotonic'])
            if hi>lo:
                value=next(item['coreC'] for item in left['gpus'] if item['uuid']==uuid)
                integral+=value*(hi-lo);coverage+=hi-lo
        assert coverage>=.95*(wave['endMonotonic']-wave['startMonotonic'])
        mean=integral/coverage;points.append(((wave['startMonotonic']+wave['endMonotonic'])/2,mean));means.append(mean)
    output['gpu'][uuid]={'originalRaw180SlopeCPerMinute':g['steadySlopeCPerMinute'],'completeCycleMeanSlopeCPerMinute':slope(points),'cycleMeanCoreC':means,'originalRaw180RangeC':[g['steadyMinCoreC'],g['steadyMaxCoreC']]}
out=p/'cycle-alias-diagnostic.json';out.write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output))
