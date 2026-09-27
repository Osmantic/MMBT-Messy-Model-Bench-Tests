"""CPU-only wave alignment of actual delivered decode and DSpark receipts."""
import argparse,json,statistics
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926')
p=argparse.ArgumentParser();p.add_argument('phase');a=p.parse_args();assert Path(a.phase).name==a.phase
out=B/'evidence'/a.phase;r=json.loads((out/'result.json').read_text());rows=[]
for w in r['waves']:
    meta=[json.loads((out/(a.phase+'-r'+str(req['index'])+'.delivery.json')).read_text())['finalMetaInfo'] for req in w['requests']]
    rows.append({'endMinutes':(w['endMonotonic']-r['runStartMonotonic'])/60,'decodeTokensPerSecond':w['analysis']['aggregate_rate'],'meanSpecAcceptLength':statistics.mean(m['spec_accept_length'] for m in meta),'meanSpecAcceptRate':statistics.mean(m['spec_accept_rate'] for m in meta),'verifyCount':sum(m['spec_verify_ct'] for m in meta),'acceptedDrafts':sum(m['spec_accepted_drafts'] for m in meta),'proposedDrafts':sum(m['spec_proposed_drafts'] for m in meta)})
summary={'phase':a.phase,'waves':rows,'interpretation':'Provider-reported DSpark acceptance; descriptive covariate, not a throughput normalization or causal explanation.'}
(out/'speculation-alignment.json').write_text(json.dumps(summary,indent=2));print(json.dumps({'phase':a.phase,'first4':rows[:4],'last4':rows[-4:]}))
