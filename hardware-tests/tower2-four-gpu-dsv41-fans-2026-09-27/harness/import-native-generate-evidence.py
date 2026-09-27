"""Map actual native provider receipts, retaining unavailable cache split."""
import argparse, hashlib, json, subprocess
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926/evidence')
TASK='codex-01a0dfd8-b03d-7622-b24f-23e65ad1c861-four-gpu-dsv41'
def integer(v):assert type(v) is int and v>=0;return v
def derive(path):
    data=json.loads(path.read_text());assert data['provider']=='sglang-native-generate' and data['worker']=='tower2'
    assert data['runtime']['checkpointRevision']=='fb2764a5cf321eaa5070ca8f9e892818f477c16d'
    assert data['runtime']['imageId']=='sha256:a30e3c69e6a4de1b82e4893dfa971ab94cba126476e3a26f4d1da5d868fae04f'
    assert {r['id'] for r in data['verifiedModels']['data']}=={'deepseek-v4.1-flash'}
    r=data['response'];meta=r['meta_info'];prompt=integer(meta['prompt_tokens']);completion=integer(meta['completion_tokens'])
    ids=r['output_ids'];assert isinstance(ids,list) and len(ids)==completion and all(type(i) is int and i>=0 for i in ids)
    reason=meta['finish_reason'];assert type(reason) is dict and reason['type'] in ('length','stop')
    if reason['type']=='length':assert integer(reason['length'])==completion
    receipt=meta['id'];assert isinstance(receipt,str) and receipt
    cached=meta.get('cached_tokens');known=cached is not None
    row={'receiptId':receipt,'task':TASK,'phase':path.name.removesuffix('.generate-receipt.json'),
         'worker':'tower2','model':'deepseek-v4.1-flash','promptTokens':prompt,'completionTokens':completion,
         'outcome':'native-'+reason['type'],'cacheSplitKnown':known,
         'evidence':str(path)+';sha256='+hashlib.sha256(path.read_bytes()).hexdigest()}
    if known:
        cached=integer(cached);assert cached<=prompt
        row.update(cached=cached,fresh=prompt-cached)
    return row
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    rows=[derive(path) for path in sorted(B.glob('*.generate-receipt.json'))]
    assert rows and len({r['receiptId'] for r in rows})==len(rows)
    target=B/'native-transcript-mapping.json';target.write_text(json.dumps(rows,indent=2))
    report={'receipts':len(rows),'knownCacheSplits':sum(r['cacheSplitKnown'] for r in rows)}
    if args.apply:report['import']=json.loads(subprocess.check_output([
        '/home/michael/.local/bin/pixel-local-work-ledger','import-transcripts','--mapping',str(target)],text=True))
    print(json.dumps(report,indent=2))
