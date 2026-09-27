"""Export only the pinned checkpoint's verified file hashes and sizes."""
import hashlib,json,re
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926')
source=B/'model-state/verification.json';raw=source.read_bytes();d=json.loads(raw)
assert d['status']=='verified' and d['revision']=='fb2764a5cf321eaa5070ca8f9e892818f477c16d' and len(d['files'])==88
files=[]
for item in d['files']:
    name=item['name'];digest=item['digest']
    assert not Path(name).is_absolute() and '..' not in Path(name).parts and re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}',digest)
    assert type(item['bytes']) is int and item['bytes']>0
    files.append({'name':name,'bytes':item['bytes'],'digest':digest,'algorithm':'SHA256 file content' if len(digest)==64 else 'Git blob SHA1 (blob size NUL plus file content)'})
assert sum(item['bytes'] for item in files)==510313345146
record={'status':'verified','revision':d['revision'],'fileCount':88,'totalBytes':sum(item['bytes'] for item in files),'privateVerificationReceiptSha256':hashlib.sha256(raw).hexdigest(),'files':files,'verificationImplementation':'Pinned upstream boot.py full SHA256 for LFS objects and Git blob SHA1 for other files; startup metadata checks are separate from full hashing.','excluded':'API key, model weights, owner filesystem metadata'}
out=B/'evidence/v2-checkpoint-verification.json';out.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'path':str(out),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'files':88,'bytes':record['totalBytes']}))
