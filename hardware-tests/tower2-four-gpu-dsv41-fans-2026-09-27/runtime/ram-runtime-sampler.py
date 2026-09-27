"""Run inside the isolated DSV container; no command-line/credential capture."""
import datetime, json, os, signal, threading, time
from pathlib import Path
stop=threading.Event()
def kb_fields(path):
    result={}
    for line in path.read_text().splitlines():
        if ':' not in line:continue
        key,value=line.split(':',1);parts=value.split()
        if parts and parts[0].isdigit():result[key]=int(parts[0])*(1024 if len(parts)>1 and parts[1]=='kB' else 1)
    return result
# Keep at most16MiB in the active file and three previous generations.
MAX_LOG_BYTES=16*2**20
def append_record(target,record,maximum=MAX_LOG_BYTES):
    data=(json.dumps(record,allow_nan=False)+'\n').encode('utf-8')
    if len(data)>maximum:raise ValueError('Single RAM record exceeds log budget')
    if target.exists() and target.stat().st_size+len(data)>maximum:
        for index in (2,1):
            old=target.with_name(target.name+'.'+str(index))
            if old.exists():old.replace(target.with_name(target.name+'.'+str(index+1)))
        target.replace(target.with_name(target.name+'.1'))
    # Reopen after rotation; never continue writing through the old inode.
    with target.open('ab') as handle:handle.write(data)

def main():
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *args:stop.set())
    target=Path(os.environ.get('STATE_PATH','/state'))/'ram-runtime-telemetry.jsonl'
    while not stop.is_set():
        record={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'monotonic':time.monotonic(),
                'meminfo':kb_fields(Path('/proc/meminfo')),'processes':[],'errors':[]}
        vm={k:int(v) for k,v in (line.split() for line in Path('/proc/vmstat').read_text().splitlines())}
        record['vmstat']={k:vm[k] for k in ('pswpin','pswpout','pgmajfault','oom_kill')}
        pressure=Path('/proc/pressure/memory');record['memoryPressure']=pressure.read_text() if pressure.exists() else None
        for directory in Path('/proc').iterdir():
            if not directory.name.isdigit() or int(directory.name)==os.getpid():continue
            try:
                comm=(directory/'comm').read_text().strip()
                if not ('python' in comm or 'sglang' in comm):continue
                stat=(directory/'stat').read_text();tail=stat[stat.rfind(')')+2:].split()
                record['processes'].append({'pid':int(directory.name),'comm':comm,'startTicks':int(tail[19]),
                    'majorFaults':int(tail[9]),'status':{k:v for k,v in kb_fields(directory/'status').items()
                                                      if k in ('VmRSS','VmLck','VmSwap','VmPeak','VmSize')},
                    'smapsRollup':kb_fields(directory/'smaps_rollup')})
            except FileNotFoundError:pass  # Process exited during this sample.
            except Exception as exc:record['errors'].append({'pid':int(directory.name),'error':type(exc).__name__})
        append_record(target,record);stop.wait(2)

if __name__=='__main__':main()
