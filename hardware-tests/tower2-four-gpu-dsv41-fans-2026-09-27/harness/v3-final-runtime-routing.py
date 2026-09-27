"""Short functional acceptance: cold native startup, actual authenticated routing."""
import datetime,hashlib,json,os,subprocess,time,urllib.error,urllib.request
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence';C=Path('/opt/mmbt/gpu-control')
runtime=json.loads((E/'native-runtime-start.json').read_text());start=time.monotonic()
def request(url,body=None,native=False):
    headers={'Content-Type':'application/json'}
    if native:headers['Authorization']='Bearer '+(B/'model-state/api-key').read_text().strip()
    req=urllib.request.Request(url,data=None if body is None else json.dumps(body).encode(),headers=headers)
    with urllib.request.urlopen(req,timeout=45 if body is not None else 3) as response:return json.load(response),dict(response.headers)
while time.monotonic()-start<300:
    try:
        models,_=request('http://127.0.0.1:8010/v1/models',native=True)
        assert any(m['id']=='deepseek-v4.1-flash' for m in models['data']);break
    except (urllib.error.URLError,TimeoutError,ConnectionError):time.sleep(3)
else:raise RuntimeError('Cold native model did not become ready in300s')
protection=json.loads(subprocess.check_output([os.sys.executable,str(C/'status.py')],text=True,timeout=30))
assert protection['status']=='ready' and not protection['criticalLatchPresent']
assert all(g['requestedPowerW']==g['enforcedPowerW']==275 for g in protection['independentGpuSample']['gpus'])
inspect=json.loads(subprocess.check_output(['docker','inspect','mmbt-dsv41'],text=True))[0]
assert inspect['Id']==runtime['containerId'] and inspect['Image']==runtime['imageId'] and inspect['State']['Running'] and not inspect['State']['Paused']
assert inspect['HostConfig']['LogConfig']=={'Type':'json-file','Config':{'max-size':'20m','max-file':'3'}}
assert subprocess.check_output(['systemctl','is-active','mmbt-dsv41.service'],text=True).strip()=='active'
body={'model':'deepseek-v4.1-flash','messages':[{'role':'user','content':'Return only this JSON after calculating41*19: {"product":NUMBER,"ok":true}'}],'max_tokens':128,'temperature':0,'chat_template_kwargs':{'thinking':False}}
responses=[]
for role,url,native in (('native','http://127.0.0.1:8010/v1/chat/completions',True),('routed','http://127.0.0.1:18080/v1/chat/completions',False)):
    if role=='routed':
        for _ in range(10):
            h,_=request('http://127.0.0.1:18080/health')
            if next(e for e in h['endpoints'] if e['name']=='tower2')['healthy']:break
            time.sleep(1)
        else:raise RuntimeError('Authenticated Tower2 router health did not settle')
        body['model']='dream-fleet-agent'
    t0=datetime.datetime.now(datetime.timezone.utc).isoformat();response,headers=request(url,body,native);t1=datetime.datetime.now(datetime.timezone.utc).isoformat()
    text=response['choices'][0]['message']['content'];parsed=json.loads(text.strip());assert parsed=={'product':779,'ok':True},text
    if role=='routed':assert headers.get('X-Dream-Fleet-Endpoint')=='tower2',headers
    item={'role':role,'utcStart':t0,'utcEnd':t1,'model':response['model'],'selectedEndpoint':headers.get('X-Dream-Fleet-Endpoint'),'response':response,'calculationPassed':True}
    responses.append(item)
    (E/('v2-final-'+role+'-chat-receipt.json')).write_text(json.dumps(item,indent=2)+'\n')
receipt={'status':'pass','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'bootId':protection['bootId'],'readinessWaitSeconds':time.monotonic()-start,'nativeStartedAt':inspect['State']['StartedAt'],'containerId':runtime['containerId'],'imageId':runtime['imageId'],'profileSha256':hashlib.sha256(Path('/etc/mmbt/gpu-profile.json').read_bytes()).hexdigest(),'protection':protection,'nativeLogConfig':inspect['HostConfig']['LogConfig'],'modelUnitActive':True,'responses':responses,'actualHostRebootPerformed':False,'twoHourSoakPerformed':False,'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'priorProofHarnessAttempt':'Two arithmetic calls succeeded but a missing status-schema field prevented receipt persistence; those calls are not included as known ledger usage.'}
path=E/'v2-final-runtime-routing.json';assert not path.exists();path.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'status':'pass','nativeModel':responses[0]['model'],'routedEndpoint':responses[1]['selectedEndpoint'],'containerId':runtime['containerId'],'bootProtectionReady':True,'caps275':True,'readinessWaitSeconds':receipt['readinessWaitSeconds']}))
