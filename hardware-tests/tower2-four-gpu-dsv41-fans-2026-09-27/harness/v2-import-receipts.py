"""Import only this execution's completed authoritative provider receipts."""
import importlib.util,json,subprocess
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');spec=importlib.util.spec_from_file_location('native',str(B/'import-native-generate-evidence.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.TASK='codex-01a0dfd8-b03d-7622-b24f-23e65ad1c861-fan-management-execution'
rows=[m.derive(path) for path in sorted((B/'evidence').glob('v2-*.generate-receipt.json'))];assert rows and len({r['receiptId'] for r in rows})==len(rows)
target=B/'evidence/v2-transcript-mapping.json';target.write_text(json.dumps(rows,indent=2))
report={'receipts':len(rows),'knownCacheSplits':sum(r['cacheSplitKnown'] for r in rows),'task':m.TASK,'import':json.loads(subprocess.check_output(['/home/michael/.local/bin/pixel-local-work-ledger','import-transcripts','--mapping',str(target)],text=True))}
print(json.dumps(report))
