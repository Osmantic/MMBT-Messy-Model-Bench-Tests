"""Read-only before/after evidence for an independently initiated real reboot."""
import argparse,datetime,hashlib,importlib.util,json,subprocess,sys,time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence';C=Path('/opt/mmbt/gpu-control')
UNITS=('nvidia-powerlimit.service','docker.service','mmbt-gpu-control.service','mmbt-native-watchdog.service','mmbt-dsv41.service')
OWNED=UNITS[2:]
def command(args,timeout=5):return subprocess.check_output(args,text=True,timeout=timeout).strip()
def snapshot():
    record={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'bootId':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'uptimeSeconds':float(Path('/proc/uptime').read_text().split()[0]),'units':{},'sourceHashes':{},'profileSha256':hashlib.sha256(Path('/etc/mmbt/gpu-profile.json').read_bytes()).hexdigest(),'leaseInode':(B/'guard-state/lease').stat().st_ino}
    for unit in UNITS:
        text=command(['systemctl','show',unit,'--property=ActiveState,SubState,MainPID,UnitFileState,ExecMainStartTimestampMonotonic,ExecMainExitTimestampMonotonic,ActiveEnterTimestampMonotonic'])
        record['units'][unit]=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
    for path in sorted(C.glob('*.py')):record['sourceHashes'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    template='{"containerId":{{json .Id}},"image":{{json .Image}},"startedAt":{{json .State.StartedAt}},"running":{{json .State.Running}},"paused":{{json .State.Paused}},"restart":{{json .HostConfig.RestartPolicy.Name}},"health":{{if .State.Health}}{{json .State.Health.Status}}{{else}}null{{end}}}'
    record['runtime']=json.loads(command(['docker','inspect','--format',template,'mmbt-dsv41']))
    props=command(['docker','inspect','--format','{{json .HostConfig.LogConfig}}','mmbt-dsv41'])
    record['nativeLogConfiguration']=json.loads(props)
    return record
def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('before','after'));p.add_argument('--before-file');a=p.parse_args()
    record=snapshot()
    if a.mode=='before':
        assert a.before_file is None
        record['status']='before-real-reboot';record['foreignJobsMustBeReviewedSeparately']=True
    else:
        assert a.before_file and Path(a.before_file).name==a.before_file
        old=json.loads((E/a.before_file).read_text());assert old['status']=='before-real-reboot'
        assert old['bootId']!=record['bootId'],'No real host reboot observed'
        assert old['sourceHashes']==record['sourceHashes'] and old['profileSha256']==record['profileSha256'],'Installed contract changed across reboot'
        assert old['leaseInode']==record['leaseInode'],'Permanent lease inode changed'
        for unit in OWNED:
            state=record['units'][unit];assert state['UnitFileState']=='enabled' and state['ActiveState']=='active',(unit,state)
        assert record['units']['nvidia-powerlimit.service']['UnitFileState']=='enabled'
        cap_exit=int(record['units']['nvidia-powerlimit.service']['ExecMainExitTimestampMonotonic'])
        assert cap_exit>0 and cap_exit<=int(record['units']['docker.service']['ExecMainStartTimestampMonotonic'])
        assert cap_exit<=int(record['units']['mmbt-dsv41.service']['ExecMainStartTimestampMonotonic'])
        assert record['runtime']['running'] and not record['runtime']['paused'] and record['runtime']['restart']=='no'
        assert old['runtime']['containerId']==record['runtime']['containerId'] and old['runtime']['image']==record['runtime']['image']
        raw=command([sys.executable,str(C/'status.py')],timeout=30);protection=json.loads(raw)
        assert protection['status']=='ready' and protection['normalTemperatureRange']
        assert protection['bootId']==record['bootId'] and not protection['criticalLatchPresent']
        for name in ('status','watchdog-status'):
            obs=protection['observations'][name];assert obs['bootId']==record['bootId']
        primary=protection['observations']['status'];observer=protection['observations']['watchdog-status']
        assert primary['pid']==int(record['units']['mmbt-gpu-control.service']['MainPID'])
        assert observer['pid']==int(record['units']['mmbt-native-watchdog.service']['MainPID'])
        assert all(g['requestedPowerW']==275 and g['enforcedPowerW']==275 for g in protection['independentGpuSample']['gpus'])
        lease=(B/'guard-state/lease').stat();owners=[]
        for line in Path('/proc/locks').read_text().splitlines():
            fields=line.split()
            if len(fields)<6 or fields[1]!='FLOCK':continue
            major,minor,inode=fields[5].split(':')
            if int(inode)==lease.st_ino and int(major,16)==__import__('os').major(lease.st_dev) and int(minor,16)==__import__('os').minor(lease.st_dev):owners.append(int(fields[4]))
        assert owners==[primary['pid']],('Exactly one permanent writer lease owner required',owners)
        spec=importlib.util.spec_from_file_location('native_client',B/'native-wave-client.py');client=importlib.util.module_from_spec(spec);spec.loader.exec_module(client)
        client.HTTP_TIMEOUT=5;client._verify_docker_image();native=client._verify_runtime(client._read_api_key())
        record.update(status='pass',beforeEvidence=a.before_file,protection=protection,leaseOwnerPids=owners,nativeIdentity=native,capAppliedBeforeDocker=True,capAppliedBeforeOwnedInference=True,sameOwnedContainer=True,criticalLatchAbsent=True,actualInferenceReceiptRequiredSeparately=True)
    folder=E/('v2-reboot-proof-'+a.mode+'-'+str(time.time_ns()));folder.mkdir()
    (folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    # Also retain a simple name for the after command's exact pre-reboot input.
    if a.mode=='before':
        name=folder.name+'.json';(E/name).write_text(json.dumps(record,indent=2)+'\n')
    else:name=None
    print(json.dumps({'path':str(folder/'result.json'),'beforeFile':name,'status':record['status'],'bootId':record['bootId'],'readOnly':True}))
if __name__=='__main__':main()
