"""Reject fabricated/reordered timing evidence and verify simultaneous windows."""
import copy,importlib.util,json,sys,unittest
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');sys.path.insert(0,str(B))
spec=importlib.util.spec_from_file_location('analysis',str(B/'v2-analyze-trial.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class AnalysisTests(unittest.TestCase):
    def sample(self):return {'events':[{'t':1,'cumulativeTokens':1},{'t':2,'cumulativeTokens':2},{'t':3,'cumulativeTokens':3},{'t':4,'cumulativeTokens':3}],'finalOutputIds':[1,2,3],'finalMetaInfo':{'prompt_tokens':8,'completion_tokens':3,'cached_tokens':0,'finish_reason':{'type':'length','length':3}}}
    def test_final_metadata_only_does_not_add_tokens(self):
        s=m.checked_stream(self.sample());positive=[];prev=0
        for e in s['events']:
            n=e['cumulativeTokens']
            if n>prev:positive.append((e['t'],n-prev))
            prev=n
        self.assertEqual(positive,[(1,1),(2,1),(3,1)])
    def test_timing_and_count_corruption_rejected(self):
        changes=[lambda s:s['events'][2].update(t=.5),lambda s:s['events'][2].update(cumulativeTokens=1),lambda s:s['events'][2].update(cumulativeTokens=True),lambda s:s['finalMetaInfo'].update(completion_tokens=8),lambda s:s['finalOutputIds'].append(4)]
        for change in changes:
            s=self.sample();change(s)
            with self.assertRaises((AssertionError,ValueError)):m.checked_stream(s)
    def test_temperature_slope_has_correct_units(self):
        self.assertAlmostEqual(m.slope([(0,70),(60,71),(120,72)],None),1)
if __name__=='__main__':unittest.main(verbosity=2)
