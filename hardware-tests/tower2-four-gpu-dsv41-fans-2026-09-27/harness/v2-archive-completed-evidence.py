"""Curated completed/failed v2 evidence archive, with exact hashes and key scan."""
import datetime,hashlib,json,tarfile,time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence'
key=(B/'model-state/api-key').read_bytes().strip();assert len(key)>=20
selected=[];phases=[];fixture_hashes=set()
for folder in sorted(E.glob('v2-*')):
    if not folder.is_dir() or not (folder/'result.json').exists():continue
    r=json.loads((folder/'result.json').read_text())
    if r.get('status') in ('starting','running'):continue
    phases.append(folder.name)
    fixture=r.get('fixtureSha256')
    if type(fixture) is str:fixture_hashes.add(fixture)
    elif type(fixture) is list:
        fixture_hashes.update(item['sha256'] for item in fixture)
    for p in sorted(folder.rglob('*')):
        if p.is_file() and p.suffix in ('.json','.jsonl','.csv','.py','.txt'):
            assert not p.is_symlink();selected.append(p)
    selected.extend(sorted(E.glob(folder.name+'-r*.generate-receipt.json')))
# Retain exact used input corpora. Hash linkage excludes unrelated or still
# running trials, and future fixture generation cannot recreate their nonces.
found_fixtures=set()
for path in sorted(E.glob('fixtures-*.json')):
    assert not path.is_symlink() and path.resolve().is_relative_to(E.resolve())
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    if sha in fixture_hashes:
        selected.append(path);found_fixtures.add(sha)
assert fixture_hashes<=found_fixtures,'A completed phase input corpus is missing'
for pattern in ('v2-cpu-proof*.json','v2-control-install-*.json','v2-owned-kernel-proof-*.json','v2-competing-writer-proof-*.json','v2-helper-timeout-proof-*.json','v2-series-byte-proof-*.json'):
    selected.extend(sorted(E.glob(pattern)))
for pattern in ('v2-matched-*-spec.json','v2-matched-*-comparison.json'):
    selected.extend(sorted(E.glob(pattern)))
for pattern in ('v2-reboot-proof-before-*.json','v2-ram-records-before-bounded-*.jsonl'):
    selected.extend(sorted(E.glob(pattern)))
for name in ('v2-sanitized-gpu-slot-map.json','v2-pre-reboot-lock-owners.json','v2-temperature-thresholds.json','v2-checkpoint-verification.json','v2-plateau-cpu-proof.json','v2-pair-contract-cpu-proof.json','v2-series-byte-cpu-proof.json','v2-selected-base80-review.json','v2-owner-ended-validation.json','v2-final-persistent-install.json','native-runtime-start.json','v2-final-runtime-routing.json','v2-router-auth-activation.json','v2-final-pixel-routing-accounting.json','v2-final-native-chat-receipt.json','v2-final-routed-chat-receipt.json'):
    if (E/name).is_file():selected.append(E/name)
selected=sorted(set(selected));assert selected
records=[]
for p in selected:
    assert p.resolve().is_relative_to(E.resolve()) and not p.is_symlink()
    data=p.read_bytes()
    assert key not in data,'Sensitive material in selected export; value omitted'
    records.append({'path':p.relative_to(E).as_posix(),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
stamp=str(time.time_ns());manifest=B/('v2-archive-manifest-'+stamp+'.json')
manifest.write_text(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'phases':phases,'files':records,'privateNativeKeyScan':'no matches in selected plaintext; key value omitted','excluded':'model-state, checkpoint weights, arbitrary host records, incomplete runs'},indent=2)+'\n')
output=B/('v2-completed-evidence-'+stamp+'.tar.gz')
with tarfile.open(output,'x:gz',compresslevel=6) as archive:
    for p in selected:archive.add(p,arcname=p.relative_to(E).as_posix(),recursive=False)
    archive.add(manifest,arcname='archive-manifest.json',recursive=False)
print(json.dumps({'path':str(output),'manifest':str(manifest),'phases':len(phases),'files':len(records),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}))
