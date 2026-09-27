import datetime, json, subprocess, sys
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926')
MODEL=Path('/mnt/bulk/models/deepseek-ai-DeepSeek-V4.1-Flash-fb2764a5')
IMAGE='sha256:a30e3c69e6a4de1b82e4893dfa971ab94cba126476e3a26f4d1da5d868fae04f'
size=int(sys.argv[1]);count=int(sys.argv[2]);name=sys.argv[3]
assert name.replace('-','').isalnum()
out=B/'evidence'/('fixtures-'+name+'.json');assert not out.exists()
args=['docker','run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--memory','2g','--pids-limit','64',
      '--tmpfs','/tmp:rw,size=128m','-v',str(MODEL/'tokenizer.json')+':/models/DeepSeek-V4.1-Flash/tokenizer.json:ro',
      '-v',str(MODEL/'encoding')+':/models/DeepSeek-V4.1-Flash/encoding:ro',
      '-v',str(B/'encode-native-fixtures.py')+':/encode.py:ro','--entrypoint','python3',IMAGE,'/encode.py']
r=subprocess.run(args,input=json.dumps({'inputTokens':size,'count':count}),capture_output=True,text=True,timeout=120)
if r.returncode:raise RuntimeError(r.stderr[-2000:])
data=json.loads(r.stdout);assert data['count']==count and all(len(row['input_ids'])==size for row in data['records'])
out.write_text(r.stdout)
print(json.dumps({'path':str(out),'inputTokens':size,'count':count,'bytes':out.stat().st_size,
                  'cpuOnly':True,'noNetwork':True,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}))
