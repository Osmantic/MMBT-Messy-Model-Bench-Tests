"""Expected bounded settling is permitted; stale/unhealthy guards are not."""
import importlib.util, json, os, unittest
from pathlib import Path
from unittest.mock import patch
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926')
spec=importlib.util.spec_from_file_location('trial',os.environ.get('MMBT_TRIAL_SOURCE',str(B/'v2-native-trial.py')))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class GuardsTests(unittest.TestCase):
    def call(self,s,w):
        s={'source':'uniform-controller-v2',**s};w={'source':'independent-observer-v2',**w}
        def read(path,*args,**kwargs):return json.dumps(w if path.name=='watchdog-status.json' else s)
        with patch.object(Path,'read_text',read),patch.object(Path,'exists',return_value=False),patch.object(m.common,'fresh'),patch.object(m.common,'validate_sample'),patch.object(m.common,'boot',return_value='boot'),patch.object(m.time,'monotonic',return_value=100):return m.guards()
    def test_startup_can_withdraw_settled_readiness(self):
        self.call({'ready':False},{'mode':'starting','requestRecovery':False,'suspend':False,'degradedSince':90})
    def test_expired_or_failed_startup_rejected(self):
        for update in ({'degradedSince':80},{'degradedSince':101},{'requestRecovery':True},{'suspend':True},{'mode':'automatic'}):
            w={'mode':'starting','requestRecovery':False,'suspend':False,'degradedSince':90};w.update(update)
            with self.assertRaises((AssertionError,ValueError)):self.call({'ready':False},w)
    def test_manual_requires_both_ready_flags(self):
        for s,w in (({'ready':False},{'mode':'manual','healthy':True}),({'ready':True},{'mode':'manual','healthy':False})):
            with self.assertRaises(AssertionError):self.call(s,w)
if __name__=='__main__':unittest.main(verbosity=2)
