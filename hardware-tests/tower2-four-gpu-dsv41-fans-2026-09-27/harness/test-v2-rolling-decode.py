import unittest
from rolling_decode import measure
def stream(points):return {'events':[{'t':t,'cumulativeTokens':n} for t,n in points]}
class Decode(unittest.TestCase):
    def test_full_common_interval(self):
        s=[stream([(1,1),(2,2),(3,3)]),stream([(1,1),(2,2),(3,3)])]
        r=measure(s,0,0,4,2);self.assertEqual(r['seconds'],2);self.assertEqual(r['tokens'],4);self.assertEqual(r['aggregateTokensPerSecond'],2)
    def test_prefill_overlap_is_excluded_and_window_clipped(self):
        s=[stream([(1,1),(2,2),(3,3),(4,4)]),stream([(3,1),(4,2),(5,3)])]
        r=measure(s,0,2,6,2);self.assertEqual(r['seconds'],1);self.assertEqual(r['tokens'],2)
    def test_disjoint_decode_coverage_is_none(self):
        r=measure([stream([(1,1),(2,2)]),stream([(3,1),(4,2)])],0,0,5,2)
        self.assertEqual(r['seconds'],0);self.assertIsNone(r['aggregateTokensPerSecond'])
    def test_equal_replacement_boundary_never_creates_extra_stream(self):
        s=[stream([(1,1),(2,2)]),stream([(2,1),(3,2)])]
        r=measure(s,0,0,4,1);self.assertEqual(r['seconds'],2);self.assertEqual(r['tokens'],3)
    def test_invalid_counts_and_overconcurrency_rejected(self):
        with self.assertRaises(AssertionError):measure([stream([(1,2),(2,1)])],0,0,4,1)
        with self.assertRaises(AssertionError):measure([stream([(1,1),(2,2)])]*2,0,0,4,1)
if __name__=='__main__':unittest.main(verbosity=2)
