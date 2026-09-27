"""Read-only reboot conflict inventory, without Docker Env or credentials."""
import datetime,json,subprocess
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926')
ids=subprocess.check_output(['docker','ps','-aq'],text=True,timeout=5).split();containers=[]
for cid in ids:
    template='{"name":{{json .Name}},"state":{{json .State.Status}},"paused":{{json .State.Paused}},"restart":{{json .HostConfig.RestartPolicy}},"devices":{{json .HostConfig.DeviceRequests}}}'
    row=json.loads(subprocess.check_output(['docker','inspect','--format',template,cid],text=True,timeout=3));containers.append(row)
result={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'bootId':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'containers':containers,'nvidiaProcesses':subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory','--format=csv,noheader'],text=True,timeout=5),'activeUserServices':subprocess.check_output(['systemctl','--user','list-units','--type=service','--state=running','--no-pager','--no-legend'],text=True,timeout=5),'locks':[]}
for root in (Path('/home/michael/dream-fleet-test'),Path('/home/michael/.local/state/dream-fleet')):
    if root.exists():
        for pattern in ('*.lock','*reservation*.json','*lease*.json'):
            # only root-level lock names; broad project recursion is unnecessary.
            result['locks']+= [{'path':str(p),'bytes':p.stat().st_size} for p in root.glob(pattern) if p.is_file()]
path=B/'evidence'/('v2-reboot-inventory-'+str(__import__('time').time_ns())+'.json');path.write_text(json.dumps(result,indent=2));print(json.dumps({'path':str(path),'containerCount':len(containers),'foreignRunningGpuContainers':[row for row in containers if row['devices'] and row['state']=='running' and not row['name'].startswith('/mmbt-')],'nvidiaProcesses':result['nvidiaProcesses'],'lockPaths':result['locks']}))
