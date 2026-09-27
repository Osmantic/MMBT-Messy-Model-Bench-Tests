"""Exact owned-runtime cold maintenance; requires paused model and qualified curve.

Does not start the replacement, change GPU policy, or touch foreign containers.
"""
import argparse,datetime,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence'
M=Path('/mnt/bulk/models/deepseek-ai-DeepSeek-V4.1-Flash-fb2764a5');S=B/'model-state'
IMG='sha256:a30e3c69e6a4de1b82e4893dfa971ab94cba126476e3a26f4d1da5d868fae04f'
OLD='7b25db6a9d1a6bd3f6b3e35077b5ccae0aa8e7ee9829b966e8098d0f6b016971'
def run(args,timeout=10):return subprocess.check_output(args,text=True,stderr=subprocess.PIPE,timeout=timeout).strip()
def main():
    p=argparse.ArgumentParser();p.add_argument('qualified_comparison',nargs='?');p.add_argument('--check-only',action='store_true');a=p.parse_args()
    if not a.check_only:
        assert a.qualified_comparison and Path(a.qualified_comparison).name==a.qualified_comparison
        comparison_path=E/a.qualified_comparison;comparison=json.loads(comparison_path.read_text());assert comparison['status']=='qualified'
        assert comparison['candidateProfileSha256']==hashlib.sha256(Path('/etc/mmbt/gpu-profile.json').read_bytes()).hexdigest(),'Restore the qualified candidate before maintenance'
    assert run(['systemctl','show','mmbt-dsv41.service','--property=ActiveState','--value']) in ('inactive','failed')
    old=json.loads(run(['docker','inspect','mmbt-dsv41']))[0]
    assert old['Id']==OLD and old['Image']==IMG and old['State']['Running']
    if not a.check_only:assert old['State']['Paused'],'Pause the owned runtime before cold maintenance'
    assert old['HostConfig']['RestartPolicy']['Name']=='no' and old['HostConfig']['IpcMode']=='host'
    assert old['HostConfig']['CapAdd']==['CAP_IPC_LOCK']
    assert old['HostConfig']['Ulimits']==[{'Name':'memlock','Hard':-1,'Soft':-1}]
    devices=old['HostConfig']['DeviceRequests'];assert len(devices)==1 and devices[0]['Count']==-1 and devices[0]['Capabilities']==[['gpu']]
    assert old['Config']['Entrypoint']==['python3'] and old['Config']['Cmd']==['-u','/study/serve-verified-offline.py']
    assert old['HostConfig']['PortBindings']=={'8010/tcp':[{'HostIp':'127.0.0.1','HostPort':'8010'}]}
    expected={str(M):('/models/DeepSeek-V4.1-Flash',False),str(S):('/state',True),str(B/'guard-state'):('/guard',False),str(B/'serve-verified-offline.py'):('/study/serve-verified-offline.py',False),str(B/'ram-runtime-sampler.py'):('/study/ram-runtime-sampler.py',False)}
    binds={m['Source']:(m['Destination'],m['RW']) for m in old['Mounts'] if m['Type']=='bind'};assert binds==expected
    volumes=[m for m in old['Mounts'] if m['Type']=='volume'];assert len(volumes)==1 and volumes[0]['Name']=='mmbt-dsv41-kernel-cache' and volumes[0]['Destination']=='/root/.cache'
    values=dict(v.split('=',1) for v in old['Config']['Env'])
    env={'OFFLOAD_MODE':'ram','CONTEXT_LENGTH':'409600','MEMORY_FRACTION':'0.85','MAX_RUNNING_REQUESTS':'8','CHUNKED_PREFILL_SIZE':'2048'}
    assert all(values[k]==v for k,v in env.items())
    # Never silently drop extra operator overrides from the old container.
    image_env=dict(v.split('=',1) for v in json.loads(run(['docker','image','inspect',IMG]))[0]['Config']['Env'])
    assert values=={**image_env,**env},'Additional environment override requires explicit review'
    new_sampler=B/'ram-runtime-sampler-bounded.py';assert new_sampler.is_file() and not new_sampler.is_symlink()
    if a.check_only:
        print(json.dumps({'status':'read-only-preflight-pass','exactOwnedImageAndContainer':True,'originalEnvironmentAndMountsReviewed':True,'currentLogConfig':old['HostConfig']['LogConfig'],'samplerSha256':hashlib.sha256(new_sampler.read_bytes()).hexdigest(),'mutationPerformed':False}));return
    run(['/usr/bin/python3','/opt/mmbt/gpu-control/model-gate.py'])
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');backup_name='mmbt-dsv41-pre-log-'+stamp
    source=B/'ram-runtime-sampler.py';backup=B/('ram-runtime-sampler-before-log-'+stamp+'.py')
    old_source_sha=hashlib.sha256(source.read_bytes()).hexdigest();new_source_sha=hashlib.sha256(new_sampler.read_bytes()).hexdigest()
    # Stop only the paused, exact owned runtime. No restart policy can relaunch it.
    run(['docker','stop','--timeout','2','mmbt-dsv41'],timeout=15)
    state=json.loads(run(['docker','inspect','--format','{{json .State}}','mmbt-dsv41']));assert not state['Running']
    telemetry=S/'ram-runtime-telemetry.jsonl';archived=None
    if telemetry.exists():
        archived=E/('v2-ram-records-before-bounded-'+stamp+'.jsonl');shutil.copyfile(telemetry,archived)
        assert hashlib.sha256(telemetry.read_bytes()).digest()==hashlib.sha256(archived.read_bytes()).digest()
        # Start the bounded stream empty, rather than rotating an oversized
        # legacy file into a supposedly bounded generation. Its bytes remain
        # in the verified archive, and the old sampler has exited with Docker.
        empty=telemetry.with_name(telemetry.name+'.bounded-empty');empty.write_bytes(b'');os.replace(empty,telemetry)
    shutil.copyfile(source,backup);tmp=source.with_name(source.name+'.bounded-tmp');shutil.copyfile(new_sampler,tmp);os.replace(tmp,source)
    run(['docker','rename','mmbt-dsv41',backup_name])
    args=['docker','create','--name','mmbt-dsv41','--restart','no','--gpus','all','--ipc','host','--cap-add','IPC_LOCK','--ulimit','memlock=-1:-1','--log-driver','json-file','--log-opt','max-size=20m','--log-opt','max-file=3','-p','127.0.0.1:8010:8010']
    for src,(dest,writable) in expected.items():args+=['-v',src+':'+dest+('' if writable else ':ro')]
    args+=['-v','mmbt-dsv41-kernel-cache:/root/.cache']
    for k,v in env.items():args+=['-e',k+'='+v]
    args+=['--entrypoint','python3',IMG,'-u','/study/serve-verified-offline.py']
    try:new_id=run(args,timeout=30)
    except Exception:
        # Leave the original stopped and restore its name; do not start it blindly.
        run(['docker','rename',backup_name,'mmbt-dsv41']);shutil.copyfile(backup,source);raise
    new=json.loads(run(['docker','inspect','mmbt-dsv41']))[0];assert new['Id']==new_id and new['Image']==IMG and not new['State']['Running']
    assert new['HostConfig']['LogConfig']=={'Type':'json-file','Config':{'max-size':'20m','max-file':'3'}}
    runtime_path=E/'native-runtime-start.json';original=runtime_path.read_bytes();(E/('native-runtime-start-before-log-'+stamp+'.json')).write_bytes(original)
    runtime=json.loads(original);runtime.update(containerId=new_id,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),logConfig=new['HostConfig']['LogConfig'],samplerSha256=new_source_sha,maintenance='Exact-image replacement with bounded Docker and RAM logs; creation leaves it stopped, to start through the fresh-gated systemd service separately')
    tmp=runtime_path.with_name(runtime_path.name+'.bounded-tmp');tmp.write_text(json.dumps(runtime,indent=2)+'\n');os.replace(tmp,runtime_path)
    result={'status':'pass','utc':stamp,'qualifiedComparison':a.qualified_comparison,'comparisonSha256':hashlib.sha256(comparison_path.read_bytes()).hexdigest(),'oldContainerId':OLD,'backupContainerName':backup_name,'newContainerId':new_id,'imageId':IMG,'oldSamplerSha256':old_source_sha,'newSamplerSha256':new_source_sha,'nativeLogConfig':new['HostConfig']['LogConfig'],'ramLogActiveMaximumBytes':16*2**20,'ramLogBackups':3,'archivedRamTelemetry':None if archived is None else {'name':archived.name,'bytes':archived.stat().st_size,'sha256':hashlib.sha256(archived.read_bytes()).hexdigest()},'started':False,'foreignContainersTouched':False}
    folder=E/('v2-bounded-log-maintenance-'+stamp);folder.mkdir();(folder/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
