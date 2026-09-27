"""CPU-only continuous-dispatch boundary tests; never initialize GPUs."""
import concurrent.futures, importlib.util, json, tempfile, threading, time, unittest
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926')
spec=importlib.util.spec_from_file_location('rolling',B/'v2-rolling-trial.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Monitor:error=None
class RollingTests(unittest.TestCase):
    def result(self):return {'dispatches':[],'httpCompletions':[],'requests':[],'callsComplete':0,'outputTokens':0}
    def run_case(self,fn,seconds=.06,count=100):
        old=m.request;m.request=fn
        try:
            with tempfile.TemporaryDirectory() as tmp,concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
                r=self.result();m.run_pool(pool,[{'index':i} for i in range(count)],None,64,time.monotonic(),seconds,Path(tmp),{},r,Monitor());return r
        finally:m.request=old
    def test_replenishes_before_processing_finishes_and_drains(self):
        replenished=threading.Event()
        def fake(key,rec,budget,start,out,runtime,q):
            time.sleep(.01);q.put(rec['index'])
            if rec['index']==0:self.assertTrue(replenished.wait(1),'Replacement waited for recorder')
            if rec['index']>=8:replenished.set()
            time.sleep(.005)
            return {'index':rec['index']}
        r=self.run_case(fake)
        self.assertGreater(r['callsComplete'],8)
        self.assertEqual(r['callsComplete'],len(r['dispatches']))
        self.assertEqual(r['callsComplete'],len(r['httpCompletions']))
        self.assertEqual(len({x['index'] for x in r['requests']}),r['callsComplete'])
        self.assertTrue(all(1<=x['httpStreamsIncludingNew']<=8 for x in r['dispatches']))
        self.assertEqual(r['outputTokens'],64*r['callsComplete'])
    def test_fixture_exhaustion_is_explicit(self):
        def fake(key,rec,budget,start,out,runtime,q):q.put(rec['index']);return {'index':rec['index']}
        with self.assertRaisesRegex(RuntimeError,'fixtures exhausted'):self.run_case(fake,count=8)
    def test_failed_request_is_not_counted(self):
        def fake(*args):raise ValueError('invalid completed SSE')
        with self.assertRaisesRegex(ValueError,'invalid completed SSE'):self.run_case(fake)
if __name__=='__main__':unittest.main(verbosity=2)
