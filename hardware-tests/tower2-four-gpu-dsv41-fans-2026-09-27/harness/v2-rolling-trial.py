"""Continuous C8 soak; replenish HTTP requests before recorder processing.

Reuses the pinned native trial's sensor contract and strict SSE parser. This
workload is explicitly different from matched cohort comparisons.
"""
import argparse, concurrent.futures, hashlib, importlib.util, json, queue
import re, shutil, sys, time
from pathlib import Path

B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926')
sys.path.insert(0,str(B));sys.path.insert(0,'/opt/mmbt/gpu-control')
spec=importlib.util.spec_from_file_location('trial',B/'v2-native-trial.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)

def request(key,rec,budget,start,out,runtime,completed_http):
    began=time.monotonic();utc=t.common.utc();rawhash=hashlib.sha256();nbytes=0;lines=[]
    body={'input_ids':rec['input_ids'],'stream':True,'sampling_params':{'temperature':0,'max_new_tokens':budget,'ignore_eos':True}}
    with t.client._http_post_json('/generate',key,body,120) as response:
        for raw in response:
            rawhash.update(raw);nbytes+=len(raw)
            line=raw.rstrip(b'\r\n')
            if line:lines.append((time.monotonic()-start,line))
    http_end=time.monotonic()
    # Replenishment is independent of quadratic cumulative-stream recording.
    completed_http.put(rec['index'])
    parsed=t.parser.parse_sse(lines);del lines
    mi=parsed['final_meta_info']
    assert mi['prompt_tokens']==len(rec['input_ids']) and mi['completion_tokens']==budget and len(parsed['final_output_ids'])==budget
    assert parsed['finish_reason']=={'type':'length','length':budget}
    stem=out.name+'-r'+str(rec['index'])
    receipt={'provider':'sglang-native-generate','worker':'tower2','runtime':runtime['runtime'],'verifiedModels':runtime['verifiedModels'],'utcStart':utc,'utcEnd':t.common.utc(),'request':{'inputIdsSha256':rec['inputIdsSha256'],'inputTokens':len(rec['input_ids']),'maxNewTokens':budget,'ignoreEos':True},'response':{'output_ids':parsed['final_output_ids'],'text':parsed['final_text'],'meta_info':mi},'rawStreamSha256':rawhash.hexdigest(),'rawStreamBytes':nbytes}
    t.common.atomic(B/'evidence'/(stem+'.generate-receipt.json'),receipt)
    positive=[e['t'] for e in parsed['events'] if e.get('output_ids')]
    compact={'requestIndex':rec['index'],'requestStartMonotonic':began,'httpEndMonotonic':http_end,'events':[{'t':e['t'],'cumulativeTokens':len(e['output_ids']) if 'output_ids' in e else None} for e in parsed['events']],'finalOutputIds':parsed['final_output_ids'],'finalMetaInfo':mi,'rawStreamSha256':rawhash.hexdigest(),'rawStreamBytes':nbytes,'firstTokenSeconds':positive[0]-(began-start),'latencySeconds':http_end-began}
    t.common.atomic(out/(stem+'.delivery.json'),compact)
    return {'index':rec['index'],'httpEndMonotonic':http_end,'firstTokenSeconds':compact['firstTokenSeconds'],'latencySeconds':compact['latencySeconds']}

def run_pool(pool,records,key,budget,start,seconds,out,runtime,result,monitor):
    """Keep C HTTP streams in flight, cap unprocessed completions at 2C."""
    notifications=queue.Queue();pending={};in_http=set();cursor=0;last_progress=start
    def submit():
        nonlocal cursor
        if cursor>=len(records):raise RuntimeError('Fresh rolling fixtures exhausted')
        if len(pending)>=16:raise RuntimeError('Recorder cannot keep up with continuous load')
        rec=records[cursor];cursor+=1
        pending[rec['index']]=pool.submit(request,key,rec,budget,start,out,runtime,notifications)
        in_http.add(rec['index'])
        result['dispatches'].append({'index':rec['index'],'monotonic':time.monotonic(),'httpStreamsIncludingNew':len(in_http)})
    for _ in range(8):submit()
    while pending:
        if monitor.error:raise RuntimeError(monitor.error)
        for idx,f in list(pending.items()):
            if f.done():
                receipt=f.result();result['requests'].append(receipt);del pending[idx]
                result['callsComplete']+=1;result['outputTokens']+=budget
        while True:
            try:idx=notifications.get_nowait()
            except queue.Empty:break
            assert idx in in_http,'Duplicate HTTP completion'
            in_http.remove(idx)
            result['httpCompletions'].append({'index':idx,'observedMonotonic':time.monotonic(),'remainingHttpStreams':len(in_http)})
            if time.monotonic()-start<seconds:submit()
        if time.monotonic()-last_progress>=30:
            last_progress=time.monotonic();t.common.atomic(out/'result.json',result)
            print(json.dumps({'phase':out.name,'elapsed':round(last_progress-start,1),'callsComplete':result['callsComplete'],'inFlight':len(in_http),'pendingRecorders':len(pending)-len(in_http)}),flush=True)
        if pending:time.sleep(.02)
    assert not in_http,'HTTP tracking did not drain'

def main():
    p=argparse.ArgumentParser();p.add_argument('phase');p.add_argument('seconds',type=int);p.add_argument('fixtures',nargs='+');p.add_argument('--budget',type=int,default=2048);a=p.parse_args()
    assert re.fullmatch('v2-[a-zA-Z0-9-]+',a.phase) and 30<=a.seconds<=7200 and 64<=a.budget<=4096
    out=B/'evidence'/a.phase;out.mkdir(exist_ok=False);profile=Path('/etc/mmbt/gpu-profile.json').read_bytes();(out/'profile.json').write_bytes(profile)
    result={'phase':a.phase,'status':'starting','workload':'continuous-replenishment-C8','utcStart':t.common.utc(),'bootId':t.common.boot(),'seconds':a.seconds,'concurrency':8,'budget':a.budget,'callsComplete':0,'outputTokens':0,'requests':[],'dispatches':[],'httpCompletions':[],'sources':{},'fixtureSha256':[],'profileSha256':hashlib.sha256(profile).hexdigest(),'ambientTemperatureC':None,'noiseMeasure':'uniform fan percentage proxy'}
    sources=out/'sources';sources.mkdir()
    for path in [Path(__file__),B/'v2-native-trial.py',B/'native_sse_parser.py',B/'coherent_fans.py',*Path('/opt/mmbt/gpu-control').glob('*.py')]:
        if path.name=='pynvml.py':continue
        shutil.copyfile(path,sources/path.name);result['sources'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    monitor=None
    try:
        t.guards();key=t.client._read_api_key();t.client._verify_docker_image();runtime=t.client._verify_runtime(key);result['runtime']=runtime
        records=[];nonces=set();input_tokens=None
        for name in a.fixtures:
            f,sha=t.load_fixture(name);result['fixtureSha256'].append({'name':name,'sha256':sha})
            if input_tokens is None:input_tokens=f['inputTokens']
            assert f['inputTokens']==input_tokens and input_tokens+a.budget<409600
            for r in f['records']:
                assert r['nonce'] not in nonces;nonces.add(r['nonce'])
                r['index']=len(records);records.append(r)
        result['inputTokens']=input_tokens
        start=time.monotonic();result['runStartMonotonic']=start;t.common.atomic(out/'result.json',result)
        monitor=t.Monitor(out,profile,False);monitor.start()
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            try:run_pool(pool,records,key,a.budget,start,a.seconds,out,runtime,result,monitor)
            except Exception:
                t.pause_owned_for_trial('Rolling qualification error');raise
        result['totalElapsed']=time.monotonic()-start
        if monitor.error:raise RuntimeError(monitor.error)
        result['status']='ok';result['e2eOutputTokensPerSecond']=result['outputTokens']/result['totalElapsed']
    except Exception as e:
        result.update(status='error',error=type(e).__name__+': '+str(e));t.pause_owned_for_trial('Rolling qualification failed')
    finally:
        if monitor:monitor.close()
        if monitor and monitor.error:result.update(status='error',monitorError=monitor.error)
        result['utcEnd']=t.common.utc();t.common.atomic(out/'result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k in ('phase','status','error','monitorError','totalElapsed','callsComplete','e2eOutputTokensPerSecond')}),flush=True)
    return 0 if result['status']=='ok' else 1
if __name__=='__main__':raise SystemExit(main())
