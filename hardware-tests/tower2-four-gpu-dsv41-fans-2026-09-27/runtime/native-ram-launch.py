"""Launch pinned native DSV RAM runtime after completed checkpoint verification."""
import datetime, json, os, secrets, subprocess
from pathlib import Path
b=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926')
model=Path('/mnt/bulk/models/deepseek-ai-DeepSeek-V4.1-Flash-fb2764a5');state=b/'model-state'
receipt=json.loads((state/'verification.json').read_text())
assert receipt['status']=='verified' and receipt['revision']=='fb2764a5cf321eaa5070ca8f9e892818f477c16d'
assert len(receipt['files'])==88
key=state/'api-key'
if not key.exists():
    with os.fdopen(os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as handle:
        handle.write(secrets.token_urlsafe(32))
assert key.stat().st_uid==os.getuid() and key.stat().st_mode&0o777==0o600
image=(b/'evidence/runtime-image-id.txt').read_text().strip()
assert image=='sha256:a30e3c69e6a4de1b82e4893dfa971ab94cba126476e3a26f4d1da5d868fae04f'
for i in range(4):
    subprocess.run(['docker','stop','--timeout','2',f'mmbt-qwen-study-{i}'],capture_output=True,check=True,timeout=8)
index=json.loads((model/'model.safetensors.index.json').read_text())['weight_map']
shards={index[f'layers.{layer}.engram.embed.weight'] for layer in (1,14)}
needed=sum((model/name).stat().st_size for name in shards)+24*2**30
meminfo=Path('/proc/meminfo').read_text()
available=int(next(line.split()[1] for line in meminfo.splitlines() if line.startswith('MemAvailable:')))*1024
assert available>=needed,'Native RAM preflight headroom insufficient'
(b/'evidence/native-ram-baseline.json').write_text(json.dumps({'meminfo':meminfo,
    'vmstat':Path('/proc/vmstat').read_text(),'requiredBytes':needed,'availableBytes':available},indent=2))
armed=b/'guard-state/native-armed.json'
armed.write_text(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'reason':'Independent guard freshness required for native inference'}))
# Restart gating is in the entry point; watchdog owns only the study containers.
args=['docker','run','-d','--name','mmbt-dsv41','--restart','no','--gpus','all','--ipc','host',
      '--cap-add','IPC_LOCK','--ulimit','memlock=-1:-1','-p','127.0.0.1:8010:8010',
      '-v',str(model)+':/models/DeepSeek-V4.1-Flash:ro','-v',str(state)+':/state:rw',
      '-v','mmbt-dsv41-kernel-cache:/root/.cache',
      '-v',str(b/'guard-state')+':/guard:ro',
      '-v',str(b/'serve-verified-offline.py')+':/study/serve-verified-offline.py:ro',
      '-v',str(b/'ram-runtime-sampler.py')+':/study/ram-runtime-sampler.py:ro',
      '-e','OFFLOAD_MODE=ram','-e','CONTEXT_LENGTH=409600','-e','MEMORY_FRACTION=0.85',
      '-e','MAX_RUNNING_REQUESTS=8','-e','CHUNKED_PREFILL_SIZE=2048',
      '--entrypoint','python3',image,'-u','/study/serve-verified-offline.py']
container=subprocess.check_output(args,text=True,timeout=60).strip()
(b/'evidence/native-runtime-start.json').write_text(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'containerId':container,'imageId':image,'checkpointRevision':receipt['revision'],
    'offloadMode':'ram','context':409600,'memoryFraction':0.85,'maxRunningRequests':8,
    'powerLimitPerGpuW':275,'hostKeyMode':'0600','checkpointMountReadOnly':True,'restartPolicy':'no; qualification pending'},indent=2))
print(json.dumps({'started':container,'offloadMode':'ram','keyWrittenWithoutDisclosure':True}))
