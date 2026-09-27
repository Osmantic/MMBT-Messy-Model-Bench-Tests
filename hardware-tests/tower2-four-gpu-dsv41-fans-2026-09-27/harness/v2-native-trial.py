"""Native DSV study: strict provider receipts, compact delivery traces, 1Hz sensors."""
import argparse,concurrent.futures,datetime,hashlib,importlib.util,json,os,re,shutil,statistics,subprocess,sys,threading,time,urllib.request
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');sys.path.insert(0,'/opt/mmbt/gpu-control');sys.path.insert(0,str(B))
import pynvml,common,hardware,native_sse_parser as parser,coherent_fans
spec=importlib.util.spec_from_file_location('client',str(B/'native-wave-client.py'));client=importlib.util.module_from_spec(spec);spec.loader.exec_module(client)
_pause_lock=threading.Lock()
def pause_owned_for_trial(reason):
    # Monitor and main can report the same failure together; serialize Docker
    # pause so a successful first suspension is not mistaken for a failed race.
    with _pause_lock:return common.suspend(reason)

def load_fixture(name):
    assert Path(name).name==name
    path=B/'evidence'/name;raw=path.read_bytes();f=json.loads(raw);assert f['count']==len(f['records'])
    assert 512<=f['inputTokens']<=65536
    seen=set()
    for r in f['records']:
        assert r['nonce'] not in seen;seen.add(r['nonce'])
        assert len(r['input_ids'])==f['inputTokens'] and all(type(v) is int and v>=0 for v in r['input_ids'])
        assert hashlib.sha256(json.dumps(r['input_ids'],separators=(',',':')).encode()).hexdigest()==r['inputIdsSha256']
    return f,hashlib.sha256(raw).hexdigest()

def guards(allow_recovery=False):
    s=json.loads((common.STATE/'status.json').read_text());w=json.loads((common.STATE/'watchdog-status.json').read_text());now=time.monotonic();current=common.boot()
    assert s.get('source')=='uniform-controller-v2' and w.get('source')=='independent-observer-v2'
    common.fresh(w,now,current);common.validate_sample(w,now,current)
    if allow_recovery:
        assert w.get('mode') in ('manual','automatic','starting') and not w.get('suspend') and not w.get('critical')
    else:
        common.fresh(s,now,current);common.validate_sample(s,now,current)
        assert type(s.get('ready')) is bool
        if w['mode']=='manual':assert s['ready'] is True and w['healthy'] is True
        else:
            # A legitimate idle-to-load fan ramp withdraws settled readiness.
            # The independent observer must still bound that ramp to 15s.
            assert w['mode']=='starting' and w['requestRecovery'] is False and w['suspend'] is False
            common.real(now-common.real(w['degradedSince']),0,15)
    assert not (common.STATE/'critical-latch.json').exists()
    return s,w

def host_metrics():
    mem={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if len(line.split())==3 and line.split()[-1]=='kB'}
    vm={line.split()[0]:int(line.split()[1]) for line in Path('/proc/vmstat').read_text().splitlines()}
    return {'memAvailableBytes':mem['MemAvailable'],'swapUsedBytes':mem['SwapTotal']-mem['SwapFree'],'pswpin':vm['pswpin'],'pswpout':vm['pswpout'],'pgmajfault':vm['pgmajfault'],'loadAverage':list(os.getloadavg()),'pageBytes':os.sysconf('SC_PAGE_SIZE')}

def process_metrics():
    pids=subprocess.check_output(['docker','top','mmbt-dsv41','-eo','pid'],text=True,timeout=3).splitlines()[1:];rows=[]
    for pid in pids:
        p=Path('/proc')/pid.strip()
        try:
            mem={line.split(':')[0]:int(line.split()[1])*1024 for line in (p/'status').read_text().splitlines() if line.startswith(('VmRSS:','VmSwap:','VmLck:'))}
            stat=(p/'stat').read_text().rsplit(')',1)[1].split()
            rows.append({'pid':int(pid),'majorFaults':int(stat[9]),**mem})
        except (FileNotFoundError,PermissionError):rows.append({'pid':int(pid),'unavailable':True})
    return rows

def extras(h,sample):
    n=h.n
    for g in sample['gpus']:
        handle=h.handles[g['uuid']]
        def violation(kind):
            v=n.nvmlDeviceGetViolationStatus(handle,kind)
            return {'referenceTimeNanoseconds':int(v.referenceTime),'violationTimeNanoseconds':int(v.violationTime)}
        calls={'powerW':lambda:n.nvmlDeviceGetPowerUsage(handle)/1000,'smClockMHz':lambda:n.nvmlDeviceGetClockInfo(handle,n.NVML_CLOCK_SM),'memoryClockMHz':lambda:n.nvmlDeviceGetClockInfo(handle,n.NVML_CLOCK_MEM),'performanceState':lambda:n.nvmlDeviceGetPerformanceState(handle),'clockEventMask':lambda:n.nvmlDeviceGetCurrentClocksThrottleReasons(handle),'thermalViolation':lambda:violation(n.NVML_PERF_POLICY_THERMAL),'powerViolation':lambda:violation(n.NVML_PERF_POLICY_POWER)}
        for key,fn in calls.items():
            try:g[key]=fn()
            except Exception as e:g[key]={'unavailable':type(e).__name__}

class Monitor:
    def __init__(self,out,profile,recovery):self.out=out;self.profile=profile;self.recovery=recovery;self.stop=threading.Event();self.error=None;self.thread=None;self.degraded=None
    def run(self):
        h=hardware.Hardware(pynvml);h.open();lastproc=-100;procs=None
        try:
            with (self.out/'telemetry.jsonl').open('w') as f, (self.out/'fan-transitions.jsonl').open('w') as transition_file:
                while not self.stop.is_set():
                    began=time.monotonic()
                    try:
                        assert Path('/etc/mmbt/gpu-profile.json').read_bytes()==self.profile,'Profile changed'
                        def retain_transition(raw):
                            transition_file.write(json.dumps(raw,allow_nan=False)+'\n');transition_file.flush()
                        row=h.read() if self.recovery else coherent_fans.read(h,lambda:json.loads((common.STATE/'status.json').read_text()),retain_transition)
                        if self.recovery:
                            try:
                                s,w=guards(True)
                                if w.get('mode')=='manual':self.degraded=None
                                elif self.degraded is None:self.degraded=began
                            except Exception as e:
                                if (common.STATE/'critical-latch.json').exists():raise RuntimeError('Critical latch during fault qualification')
                                if self.degraded is None:self.degraded=began
                                s=None;w={'qualificationIndependentVisibility':True,'guardTransition':type(e).__name__}
                            if self.degraded is not None and began-self.degraded>30:raise RuntimeError('Fault qualification recovery exceeded30s')
                            # Fault qualification has its own fresh NVML observer.
                            assert all(f['policy'] in (0,1) for g in row['gpus'] for f in g['fans'])
                        else:s,w=guards()
                        extras(h,row);row.update(primary=s,observer=w,host=host_metrics(),docker=common.docker_state())
                        assert row['docker']['Running'] and not row['docker']['Paused'],'Runtime suspended'
                        assert max(g['coreC'] for g in row['gpus'])<90,'Critical thermal cutoff'
                        if began-lastproc>=10:procs=process_metrics();lastproc=began
                        row['modelProcesses']=procs;row['processSampleMonotonic']=lastproc
                        f.write(json.dumps(row,allow_nan=False)+'\n');f.flush()
                    except Exception as e:self.error=type(e).__name__+': '+str(e);pause_owned_for_trial('Trial observer failed: '+self.error);break
                    self.stop.wait(max(0,1-(time.monotonic()-began)))
        finally:h.close()
    def start(self):self.thread=threading.Thread(target=self.run);self.thread.start()
    def close(self):self.stop.set();self.thread.join(timeout=8)

def one(key,rec,budget,wave_start,out,runtime):
    start=time.monotonic();utc=common.utc();rawhash=hashlib.sha256();bytes_seen=0;lines=[]
    body={'input_ids':rec['input_ids'],'stream':True,'sampling_params':{'temperature':0,'max_new_tokens':budget,'ignore_eos':True}}
    with client._http_post_json('/generate',key,body,120) as response:
        for raw in response:
            rawhash.update(raw);bytes_seen+=len(raw)
            line=raw.rstrip(b'\r\n')
            if line:lines.append((time.monotonic()-wave_start,line))
    parsed=parser.parse_sse(lines);del lines
    mi=parsed['final_meta_info'];assert mi['prompt_tokens']==len(rec['input_ids']) and mi['completion_tokens']==budget and len(parsed['final_output_ids'])==budget
    assert parsed['finish_reason'].get('type')=='length' and parsed['finish_reason'].get('length')==budget
    receipt={'provider':'sglang-native-generate','worker':'tower2','runtime':runtime['runtime'],'verifiedModels':runtime['verifiedModels'],'utcStart':utc,'utcEnd':common.utc(),'request':{'inputIdsSha256':rec['inputIdsSha256'],'inputTokens':len(rec['input_ids']),'maxNewTokens':budget,'ignoreEos':True},'response':{'output_ids':parsed['final_output_ids'],'text':parsed['final_text'],'meta_info':mi},'rawStreamSha256':rawhash.hexdigest(),'rawStreamBytes':bytes_seen}
    stem=out.name+'-r'+str(rec['index']);common.atomic(B/'evidence'/(stem+'.generate-receipt.json'),receipt)
    compact={'events':[{'t':e['t'],'cumulativeTokens':len(e['output_ids']) if 'output_ids' in e else None} for e in parsed['events']],'finalOutputIds':parsed['final_output_ids'],'finalMetaInfo':mi,'rawStreamSha256':rawhash.hexdigest(),'rawStreamBytes':bytes_seen,'requestIndex':rec['index'],'firstTokenSeconds':next(e['t'] for e in parsed['events'] if e.get('output_ids'))-(start-wave_start),'latencySeconds':time.monotonic()-start}
    common.atomic(out/(stem+'.delivery.json'),compact)
    return parsed,compact

def main():
    ap=argparse.ArgumentParser();ap.add_argument('phase');ap.add_argument('fixtures');ap.add_argument('seconds',type=int);ap.add_argument('concurrency',type=int);ap.add_argument('budget',type=int);ap.add_argument('--allow-recovery',action='store_true');a=ap.parse_args()
    assert re.fullmatch('[a-zA-Z0-9-]+',a.phase) and 0<=a.seconds<=7200 and 1<=a.concurrency<=8 and 64<=a.budget<=4096
    out=B/'evidence'/a.phase;out.mkdir(exist_ok=False);profile=Path('/etc/mmbt/gpu-profile.json').read_bytes();(out/'profile.json').write_bytes(profile)
    result={'phase':a.phase,'status':'starting','utcStart':common.utc(),'bootId':common.boot(),'seconds':a.seconds,'concurrency':a.concurrency,'budget':a.budget,'profileSha256':hashlib.sha256(profile).hexdigest(),'sources':{},'waves':[],'callsComplete':0,'outputTokens':0,'promptTokens':0,'ambientTemperatureC':None,'noiseMeasure':'uniform fan percentage proxy','allowRecoveryFaults':a.allow_recovery}
    sources=out/'sources';sources.mkdir()
    for p in [Path(__file__),B/'native_sse_parser.py',B/'coherent_fans.py',*Path('/opt/mmbt/gpu-control').glob('*.py')]:
        if p.name=='pynvml.py':continue
        shutil.copyfile(p,sources/p.name);result['sources'][p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
    monitor=None
    try:
        guards();key=client._read_api_key();client._verify_docker_image();runtime=client._verify_runtime(key);result.update(runtime=runtime)
        fx,fxhash=load_fixture(a.fixtures);result.update(fixtureSha256=fxhash,inputTokens=fx['inputTokens']);assert fx['inputTokens']+a.budget<409600
        start=time.monotonic();result['runStartMonotonic']=start;monitor=Monitor(out,profile,a.allow_recovery);monitor.start();cursor=0
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.concurrency) as pool:
            while cursor==0 or time.monotonic()-start<a.seconds:
                if monitor.error:raise RuntimeError(monitor.error)
                batch=fx['records'][cursor:cursor+a.concurrency];assert len(batch)==a.concurrency,'Fresh fixtures exhausted';cursor+=a.concurrency
                wave_start=time.monotonic();jobs=[pool.submit(one,key,r,a.budget,wave_start,out,runtime) for r in batch];records=[j.result() for j in jobs]
                analysis=parser.analyze([r[0] for r in records]);assert analysis['status']=='ok',analysis
                w={'startMonotonic':wave_start,'endMonotonic':time.monotonic(),'analysis':analysis,'requests':[{'index':c['requestIndex'],'latencySeconds':c['latencySeconds'],'firstTokenSeconds':c['firstTokenSeconds']} for p,c in records]}
                result['waves'].append(w);result['callsComplete']+=len(records);result['outputTokens']+=a.budget*len(records);result['promptTokens']+=fx['inputTokens']*len(records)
                common.atomic(out/'result.json',result)
                if len(result['waves'])%4==0 or a.seconds==0:print(json.dumps({'phase':a.phase,'elapsed':round(time.monotonic()-start,1),'waves':len(result['waves']),'decodeRate':analysis['aggregate_rate'],'maxCoreC':max(g['coreC'] for g in json.loads((common.STATE/'watchdog-status.json').read_text())['gpus'])}),flush=True)
        result['totalElapsed']=time.monotonic()-start
        if monitor.error:raise RuntimeError(monitor.error)
        result['status']='ok';result['e2eOutputTokensPerSecond']=result['outputTokens']/result['totalElapsed']
    except Exception as e:
        result.update(status='error',error=type(e).__name__+': '+str(e));pause_owned_for_trial('Native qualification error')
    finally:
        if monitor:monitor.close()
        if monitor and monitor.error:result.update(status='error',monitorError=monitor.error)
        result['utcEnd']=common.utc();common.atomic(out/'result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k in ('phase','status','error','monitorError','totalElapsed','callsComplete','e2eOutputTokensPerSecond')}),flush=True)
    return 0 if result['status']=='ok' else 1
if __name__=='__main__':raise SystemExit(main())
