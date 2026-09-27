import copy,unittest
from coherent_fans import read
class Clock:
    def __init__(self):self.now=100
    def __call__(self):return self.now
    def sleep(self,seconds):self.now+=seconds
def sample(target=79):return {'bootId':'b','monotonic':100,'gpus':[{'coreC':78,'fans':[{'policy':1,'target':target} for f in (0,1)]} for g in range(4)]}
def primary(target=79):return {'source':'uniform-controller-v2','bootId':'b','pid':42,'monotonic':100,'targetPercent':target}
class Hardware:
    def __init__(self,rows):self.rows=rows;self.calls=0
    def read(self):self.calls+=1;return copy.deepcopy(self.rows[min(self.calls-1,len(self.rows)-1)])
class Coherence(unittest.TestCase):
    def run_read(self,h,p=primary):
        c=Clock();raw=[];r=read(h,p,raw.append,c,c.sleep);return r,raw
    def test_unchanged_uniform_read(self):
        r,raw=self.run_read(Hardware([sample()]));self.assertEqual(r['fanObservation']['attempts'],1);self.assertEqual(raw,[])
    def test_valid_slow_first_read_is_not_a_transition_timeout(self):
        c=Clock();h=Hardware([sample()]);original=h.read
        def slow():c.sleep(.31);return original()
        h.read=slow;raw=[];r=read(h,primary,raw.append,c,c.sleep)
        self.assertEqual(raw,[]);self.assertEqual(r['fanObservation']['attempts'],1);self.assertAlmostEqual(r['fanObservation']['elapsedSeconds'],.31);self.assertEqual(r['fanObservation']['retryElapsedSeconds'],0)
    def test_serial_transition_retained_then_coherent(self):
        s=sample();s['gpus'][0]['fans'][0]['target']=78
        r,raw=self.run_read(Hardware([s,sample()]));self.assertEqual(len(raw),1);self.assertEqual(r['fanObservation']['attempts'],2);self.assertEqual(raw[0]['sample']['gpus'][0]['fans'][0]['target'],78)
    def test_continuing_mismatch_expires_without_renewal(self):
        c=Clock();raw=[]
        with self.assertRaises(RuntimeError):read(Hardware([sample(78)]),primary,raw.append,c,c.sleep)
        self.assertGreaterEqual(c.now,100.25);self.assertLess(c.now,100.28);self.assertGreater(len(raw),1)
    def test_critical_transient_is_not_hidden(self):
        s=sample();s['gpus'][0]['coreC']=90;h=Hardware([s,sample()]);raw=[];c=Clock()
        with self.assertRaisesRegex(RuntimeError,'Critical'):read(h,primary,raw.append,c,c.sleep)
        self.assertEqual(h.calls,1);self.assertEqual(raw[0]['reason'],'critical-temperature')
    def test_stale_foreign_and_nonfinite_primary_rejected(self):
        for edit in ({'monotonic':90},{'monotonic':101},{'monotonic':float('nan')},{'monotonic':True},{'bootId':'other'},{'targetPercent':True},{'source':'other'}):
            c=Clock();p=primary();p.update(edit)
            with self.assertRaises(RuntimeError):read(Hardware([sample()]),lambda:p,lambda r:None,c,c.sleep)
if __name__=='__main__':unittest.main(verbosity=2)
