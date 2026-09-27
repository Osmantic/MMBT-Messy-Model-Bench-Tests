"""Explicit reviewed runtime resume. Guards never autonomously resume inference."""
import json,subprocess,time
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926')
state=json.loads(subprocess.check_output(['docker','inspect','--format','{{json .State}}','mmbt-dsv41'],text=True))
assert state['Running'] and state['Paused']
for attempt in range(20):
    r=subprocess.run(['/usr/bin/python3','/opt/mmbt/gpu-control/model-gate.py'],capture_output=True,text=True)
    if r.returncode==0:break
    time.sleep(1)
else:raise RuntimeError(r.stderr)
subprocess.run(['docker','unpause','mmbt-dsv41'],check=True)
receipt={'utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'gate':r.stdout.strip(),'explicitOwnerAuthorizedResume':True}
(B/'evidence'/('v2-explicit-resume-'+str(time.time_ns())+'.json')).write_text(json.dumps(receipt));print(json.dumps(receipt))
