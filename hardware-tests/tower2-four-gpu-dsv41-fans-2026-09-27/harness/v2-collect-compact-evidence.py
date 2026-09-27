"""Explicit compact publication snapshot; never traverses model-state or keys."""
import hashlib,json,time,zipfile
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence';selected=[]
names=['v2-screen80','v2-screen85','v2-screen-curve','v2-screen-lower1','v2-screen-lower2-coherent','v2-screen-lower2-coherent-r2','v2-c1-default-curve','v2-rolling-pilot85','v2-cold-burst65-transition','v2-cold-burst65-loadedidle-transition','v2-cold-burst65-loadedidle','v2-persistent-config-fault-1790491935843473379']
for pattern in ('v2-matched-*','v2-performance-stop-*','v2-hot-loaded-*','v2-loaded-*','v2-selected-*','v2-final-*','v2-reboot-proof-*','v2-removal-proof-*','v2-bounded-log-maintenance-*'):
    for folder in E.glob(pattern):
        if folder.is_dir() and (folder/'result.json').exists():
            r=json.loads((folder/'result.json').read_text())
            if r.get('status') not in ('starting','running'):names.append(folder.name)
for name in sorted(set(names)):
    folder=E/name
    if not folder.is_dir():continue
    for filename in ('result.json','scheduler-held-original.json','analysis.json','plateau-analysis.json','cycle-alias-diagnostic.json','timing-diagnostic.json','profile.json','temperature-band-summary.json','observations.csv','summary.csv','serial-transition-review.json','speculation-alignment.json','runtime-step-covariates.json','fault-test-source.py'):
        path=folder/filename
        if path.is_file():selected.append(path)
for pattern in ('v2-cpu-proof-*.json','v2-owned-kernel-proof-*.json','v2-control-install-*.json','v2-series-byte-proof-*.json'):
    matches=sorted(E.glob(pattern),key=lambda p:p.stat().st_mtime)
    if matches:selected.append(matches[-1])
for pattern in ('v2-matched-*-spec.json','v2-matched-*-comparison.json'):
    selected.extend(sorted(E.glob(pattern)))
for role in ('controller','observer'):
    for sig in ('SIGSTOP','SIGKILL'):
        folders=sorted((p for p in E.glob('v2-idle-'+role+'-'+sig+'-*') if p.is_dir()))
        if folders:
            result=folders[-1]/'result.json'
            if result.exists():selected.append(result)
assert selected
for name in ('v2-checkpoint-verification.json','v2-plateau-cpu-proof.json','v2-pair-contract-cpu-proof.json','v2-series-byte-cpu-proof.json','v2-sanitized-gpu-slot-map.json','v2-selected-base80-review.json','v2-owner-ended-validation.json','v2-final-persistent-install.json','native-runtime-start.json','v2-final-runtime-routing.json','v2-router-auth-activation.json','v2-final-pixel-routing-accounting.json','v2-final-native-chat-receipt.json','v2-final-routed-chat-receipt.json'):
    if (E/name).is_file():selected.append(E/name)
output=B/('compact-v2-snapshot-'+str(time.time_ns())+'.zip')
with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
    records=[]
    for path in selected:
        assert path.resolve().is_relative_to(E.resolve()) and not path.is_symlink()
        data=path.read_bytes();name=path.relative_to(E).as_posix()
        archive.writestr(name,data);records.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    archive.writestr('snapshot-manifest.json',json.dumps(records,indent=2)+'\n')
print(json.dumps({'path':str(output),'files':len(records),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}))
