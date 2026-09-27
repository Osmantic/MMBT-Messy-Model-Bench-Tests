import importlib.util, unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('pairs',Path(__file__).with_name('v2-compare-pairs.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class PairTests(unittest.TestCase):
    def test_identical_rates_have_unit_ratio(self):
        r=m.interval([800,900,700],[800,900,700]);self.assertEqual(r['geometricMeanRatio'],1);self.assertTrue(r['noninferiorityQualified'])
    def test_low_variance_quiet_candidate_can_qualify(self):
        r=m.interval([985,986,984],[1000]*3);self.assertTrue(r['noninferiorityQualified'])
    def test_good_mean_with_unresolved_variance_does_not_qualify(self):
        r=m.interval([970,990,1010],[1000]*3);self.assertGreater(r['geometricMeanRatio'],.97);self.assertFalse(r['noninferiorityQualified'])
    def test_losses_beyond_three_percent_fail(self):
        self.assertFalse(m.interval([960]*3,[1000]*3)['noninferiorityQualified'])
    def test_invalid_rates_rejected(self):
        for bad in (True,0,float('nan'),float('inf'),-1):
            with self.assertRaises(AssertionError):m.interval([bad,900,900],[1000]*3)
    def test_only_model_listing_timestamp_is_volatile(self):
        a={'runtime':{'imageId':'pinned'},'verifiedModels':{'data':[{'id':'actual-dsv','created':1}]}}
        b={'runtime':{'imageId':'pinned'},'verifiedModels':{'data':[{'id':'actual-dsv','created':2}]}}
        self.assertEqual(m.runtime_identity(a),m.runtime_identity(b))
        b['verifiedModels']['data'][0]['id']='wrong-model'
        self.assertNotEqual(m.runtime_identity(a),m.runtime_identity(b))
if __name__=='__main__':unittest.main(verbosity=2)
