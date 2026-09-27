import importlib.util, unittest
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926')
spec=importlib.util.spec_from_file_location('rolling_analysis',B/'v2-analyze-rolling.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class OccupancyTests(unittest.TestCase):
    def streams(self,start,end,n=8):return [{'requestStartMonotonic':start,'httpEndMonotonic':end} for _ in range(n)]
    def test_full_eight_and_clipping(self):
        r=m.occupancy(self.streams(0,12),2,10);self.assertEqual(r['meanHttpConcurrency'],8);self.assertEqual(r['fractionWithEightHttpStreams'],1)
    def test_gaps_are_not_counted_as_continuous_load(self):
        r=m.occupancy(self.streams(0,4)+self.streams(6,10),0,10);self.assertAlmostEqual(r['meanHttpConcurrency'],6.4);self.assertAlmostEqual(r['fractionWithEightHttpStreams'],.8)
    def test_simultaneous_end_start_has_no_spurious_ninth_stream(self):
        r=m.occupancy(self.streams(0,5)+self.streams(5,10),0,10);self.assertEqual(r['peakHttpConcurrency'],8)
    def test_invalid_intervals_are_rejected(self):
        for start,end in ((3,2),(0,float('nan')),(0,126),(True,10)):
            with self.assertRaises(AssertionError):m.occupancy(self.streams(start,end),0,10)
if __name__=='__main__':unittest.main(verbosity=2)
