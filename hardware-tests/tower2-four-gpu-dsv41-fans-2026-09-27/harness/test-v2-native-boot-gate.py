"""Check actual container startup gate without importing SGLang or GPUs."""
import copy,importlib.util,json,os,tempfile,time,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('serve',Path(os.environ.get('MMBT_BOOT_SOURCE',str(Path(__file__).with_name('serve-verified-offline-next.py')))));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Gate(unittest.TestCase):
    def records(self):
        p={'bootId':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'monotonic':time.monotonic(),'source':'uniform-controller-v2','ready':True,'allFansSettled':True,'targetPercent':80,'gpus':[{'uuid':u,'coreC':70,'requestedPowerW':275,'enforcedPowerW':275,'fans':[{'fan':f,'policy':1,'target':80,'rpm':2400} for f in (0,1)]} for u in m.UUIDS]}
        w=copy.deepcopy(p);w.update(source='independent-observer-v2',mode='manual',healthy=True);return p,w
    def run_gate(self,p,w,latch=False):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);(folder/'status.json').write_text(json.dumps(p));(folder/'watchdog-status.json').write_text(json.dumps(w))
            if latch:(folder/'critical-latch.json').write_text('{}')
            return m.verify_guards(folder)
    def test_fresh_two_guards(self):self.assertTrue(self.run_gate(*self.records()))
    def test_stale_foreign_future_nonfinite_or_boolean_clocks(self):
        for key,value in [('bootId','foreign'),('monotonic',time.monotonic()-6),('monotonic',time.monotonic()+100),('monotonic',float('nan')),('monotonic',True)]:
            for role in (0,1):
                rows=self.records();rows[role][key]=value
                with self.subTest(key=key,role=role),self.assertRaises(ValueError):self.run_gate(*rows)
    def test_caps_fan_identity_and_thermal_boundaries(self):
        for mutate in (lambda p:p['gpus'].pop(),lambda p:p['gpus'][0].update(requestedPowerW=600),lambda p:p['gpus'][0].update(coreC=83),lambda p:p['gpus'][0].update(coreC=True),lambda p:p['gpus'][0]['fans'][0].update(rpm=0),lambda p:p['gpus'][0]['fans'][0].update(target=79),lambda p:p['gpus'][0]['fans'][0].update(policy=0),lambda p:p['gpus'][0]['fans'].pop()):
            p,w=self.records();mutate(w)
            with self.assertRaises(ValueError):self.run_gate(p,w)
    def test_unsettled_unhealthy_and_critical_latch(self):
        p,w=self.records();p['allFansSettled']=False
        with self.assertRaises(ValueError):self.run_gate(p,w)
        p,w=self.records();w['healthy']=False
        with self.assertRaises(ValueError):self.run_gate(p,w)
        with self.assertRaises(RuntimeError):self.run_gate(*self.records(),latch=True)
if __name__=='__main__':unittest.main(verbosity=2)
