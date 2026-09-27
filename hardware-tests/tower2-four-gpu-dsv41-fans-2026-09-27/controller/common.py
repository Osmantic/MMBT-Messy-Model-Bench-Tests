"""Shared fixed hardware contract; no model or network decisions."""
import datetime,fcntl,json,math,os,socket,subprocess,time,uuid
from pathlib import Path
BASE=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926')
STATE=BASE/'guard-state'
UUIDS=frozenset({'GPU-708ffb68-e356-930d-4f83-980567b5ae3a','GPU-ff71102f-22f8-52bb-da93-2076a6531329','GPU-6b6dd6f9-2850-043f-b545-6ff4a60df2ca','GPU-fe3fb4d0-5ddc-9c05-587b-1bc84c75c1a0'})
CONTAINER='mmbt-dsv41'
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def real(value,low=0,high=float('inf')):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:raise ValueError('Invalid finite number')
    return value
def boot():
    value=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if str(uuid.UUID(value))!=value:raise ValueError('Invalid boot identity')
    return value
def atomic(path,data):
    tmp=path.with_name(path.name+'.tmp.'+str(os.getpid()))
    with tmp.open('w') as f:json.dump(data,f,allow_nan=False);f.flush();os.fsync(f.fileno())
    tmp.replace(path)
def event(kind,**fields):
    path=STATE/'events.jsonl'
    # Independent processes use separate log files to avoid rotation races.
    path=path.with_name('events-'+Path(__import__('sys').argv[0]).stem+'.jsonl')
    if path.exists() and path.stat().st_size>8*2**20:
        for i in (2,1):
            src=path.with_name(path.name+'.'+str(i));dst=path.with_name(path.name+'.'+str(i+1))
            if src.exists():src.replace(dst)
        path.replace(path.with_name(path.name+'.1'))
    with path.open('a') as f:f.write(json.dumps({'utc':utc(),'monotonic':time.monotonic(),'kind':kind,**fields},allow_nan=False)+'\n')
def notify(message):
    address=os.environ.get('NOTIFY_SOCKET')
    if address:
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as s:s.sendto(message.encode(),('\0'+address[1:]) if address.startswith('@') else address)
class Lease:
    def __init__(self,path=STATE/'lease'):self.path=path;self.fd=None
    def __enter__(self):
        self.fd=os.open(self.path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:os.close(self.fd);self.fd=None;raise
        return self
    def __exit__(self,*args):
        if self.fd is not None:os.close(self.fd);self.fd=None
def docker_state():
    result=subprocess.check_output(['docker','inspect','--format','{{json .State}}',CONTAINER],text=True,timeout=3)
    state=json.loads(result)
    if type(state) is not dict or any(type(state.get(k)) is not bool for k in ('Running','Paused')):raise ValueError('Unknown workload state')
    return state
def suspend(reason):
    """Only the owned runtime. Verified pause preserves the loaded RAM table."""
    from workload import pause
    result=pause()
    receipt={'utc':utc(),'bootId':boot(),'monotonic':time.monotonic(),'reason':reason,**result}
    atomic(STATE/'suspension.json',receipt)
    return receipt
def latch(reason,sample=None):
    path=STATE/'critical-latch.json'
    if not path.exists():atomic(path,{'utc':utc(),'bootId':boot(),'monotonic':time.monotonic(),'reason':reason,'sample':sample})
def fresh(record,now,current_boot,maximum=5):
    if type(record) is not dict or record.get('bootId')!=current_boot:raise ValueError('Boot/record differs')
    real(now-real(record.get('monotonic')),0,maximum)
    return record

def validate_sample(sample,now,current_boot):
    fresh(sample,now,current_boot)
    rows=sample.get('gpus')
    if type(rows) is not list or len(rows)!=4:raise ValueError('Four GPU samples required')
    seen=set()
    for g in rows:
        if type(g) is not dict or type(g.get('uuid')) is not str or g['uuid'] not in UUIDS or g['uuid'] in seen:raise ValueError('GPU sample identity differs')
        seen.add(g['uuid']);real(g.get('coreC'),0,120);real(g.get('utilizationGpu'),0,100)
        if real(g.get('requestedPowerW'))!=275:raise ValueError('Requested cap differs')
        real(g.get('enforcedPowerW'),150,275)
        fans=g.get('fans')
        if type(fans) is not list or len(fans)!=2 or any(type(f) is not dict or type(f.get('fan')) is not int for f in fans) or {f['fan'] for f in fans}!={0,1}:raise ValueError('Two exact fans required')
        for f in fans:
            if type(f.get('policy')) is not int or f['policy'] not in (0,1):raise ValueError('Fan policy differs')
            real(f.get('target'),0,100);real(f.get('current'),0,100);real(f.get('rpm'),0,10000)
    return sample

def recovery_since(reason,now=None):
    """A process restart cannot renew an existing current-boot deadline."""
    now=time.monotonic() if now is None else real(now)
    path=STATE/'recovery-episode.json';current=boot()
    try:old=json.loads(path.read_text())
    except FileNotFoundError:old=None
    if old is not None and old.get('bootId')==current:
        since=real(old.get('monotonic'),0,now)
        return since
    atomic(path,{'bootId':current,'monotonic':now,'utc':utc(),'reason':reason})
    return now
