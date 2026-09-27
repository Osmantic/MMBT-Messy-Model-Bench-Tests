"""Real CPU child hang/kill test. No GPU commands or real Docker suspension."""
import datetime,json,subprocess,sys,time
from pathlib import Path
from unittest.mock import patch
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');sys.path.insert(0,str(B/'fan-control-v2'));import recovery
real_popen=subprocess.Popen;children=[];actions=[]
def spawn(*args,**kwargs):
    child=real_popen([sys.executable,'-c','import time;time.sleep(120)'],**kwargs);children.append(child);return child
began=time.monotonic()
with patch.object(recovery.subprocess,'Popen',side_effect=spawn),patch.object(recovery,'suspend',side_effect=lambda reason:actions.append({'monotonic':time.monotonic(),'reason':reason})):
    assert recovery.supervised_restore('Injected blocked native call')==1
elapsed=time.monotonic()-began
assert len(children)==1 and children[0].returncode==-9 and actions and 12<=elapsed<=15
receipt={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'actualChildPid':children[0].pid,'actualChildExitCode':children[0].returncode,'elapsedSeconds':elapsed,'suspensionDecisionAfterKill':True,'hardwareActuated':False,'ownedRuntimeStateChanged':False}
(B/'evidence/v2-helper-timeout-kernel-proof.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
