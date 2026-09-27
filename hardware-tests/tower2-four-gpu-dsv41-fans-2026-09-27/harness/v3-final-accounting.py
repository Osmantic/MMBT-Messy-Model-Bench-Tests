"""Capture all authoritative final receipts without exporting private sessions."""
import datetime,hashlib,json,subprocess,urllib.request
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence';TASK='codex-01a0dfd8-b03d-7622-b24f-23e65ad1c861-fan-management-execution';LEDGER='/home/michael/.local/bin/pixel-local-work-ledger'
with urllib.request.urlopen('http://127.0.0.1:18080/health',timeout=3) as response:health=json.load(response)
t2=next(e for e in health['endpoints'] if e['name']=='tower2');assert t2['healthy'] and t2['model_id']=='deepseek-v4.1-flash' and t2['completed']>=3
assert all(e['completed']==0 for e in health['endpoints'] if e['name']!='tower2'),'Unexpected alternate route requires investigation'
raw=json.loads((E/'v2-final-dsv-navigation-output.json').read_text());assert raw['status']=='ok';meta=raw['result']['meta']['agentMeta'];assert meta['model']=='dream-fleet-agent'
begin=(E/'v2-final-dsv-navigation-start-utc.txt').read_text().strip();end=(E/'v2-final-dsv-navigation-end-utc.txt').read_text().strip()
cmd=[LEDGER,'import-openclaw','--task',TASK,'--phase','v2-final-dsv-navigation','--worker','tower2','--model','deepseek-v4.1-flash','--session',meta['sessionFile'],'--from',begin,'--to',end,'--outcome','reviewed-doc-navigation-and-native-routing-proof']
pixel_import=json.loads(subprocess.check_output(cmd,text=True))
mapping=[]
for role in ('native','routed'):
    path=E/('v2-final-'+role+'-chat-receipt.json');record=json.loads(path.read_text());response=record['response'];usage=response['usage'];details=usage.get('prompt_tokens_details') or {};cached=details.get('cached_tokens',usage.get('cached_tokens'))
    row={'receiptId':response['id'],'task':TASK,'phase':'v2-final-'+role+'-arithmetic-proof','worker':'tower2','model':'deepseek-v4.1-flash','promptTokens':usage['prompt_tokens'],'completionTokens':usage['completion_tokens'],'outcome':'functional-cold-native-and-router-proof','cacheSplitKnown':cached is not None,'evidence':str(path)+';sha256='+hashlib.sha256(path.read_bytes()).hexdigest()}
    if cached is not None:
        assert type(cached) is int and 0<=cached<=usage['prompt_tokens'];row.update(cached=cached,fresh=usage['prompt_tokens']-cached)
    mapping.append(row)
path=E/'v2-final-chat-transcript-mapping.json';path.write_text(json.dumps(mapping,indent=2)+'\n')
chat_import=json.loads(subprocess.check_output([LEDGER,'import-transcripts','--mapping',str(path)],text=True))
subprocess.run(['python3',str(B/'v2-import-receipts.py')],check=True,stdout=subprocess.DEVNULL)
receipt={'status':'pass','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'task':TASK,'pixelUtcStart':begin,'pixelUtcEnd':end,'actualPixelBackend':'tower2/deepseek-v4.1-flash','routerWitness':{'tower2Completed':t2['completed'],'alternateCompleted':0,'nativeModelId':t2['model_id']},'allPixelCallsImported':pixel_import,'functionalChatCallsImported':chat_import,'privateSessionExported':False,'unknownUnreceiptedCalls':2,'unknownCallReason':'Initial functional-proof attempt completed two calls but failed before saving receipts; they are not counted as known fresh usage.'}
(E/'v2-final-pixel-routing-accounting.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
