import copy,importlib.util,math,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('plateau',Path(__file__).with_name('v3-temperature-plateau.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Plateau(unittest.TestCase):
    def data(self,trend=0):
        ids=['gpu'+str(i) for i in range(4)];start=1000
        result={'status':'ok','seconds':1800,'concurrency':8,'runStartMonotonic':start,'waves':[{'startMonotonic':start+30*i,'endMonotonic':start+30*(i+1)} for i in range(60)]}
        rows=[{'monotonic':start+t,'gpus':[{'uuid':u,'coreC':50+i+(2 if t%30<15 else -2)+trend*t/60,'requestedPowerW':275,'enforcedPowerW':275} for i,u in enumerate(ids)]} for t in range(1801)]
        analysis={'quietThermalQualification':'not-qualified','reasons':['gpu0: not thermally steady'],'noiseProxy':{'nonuniformSnapshots':0,'peakRequestedPercent':78},'gpu':{u:{'thermalViolationDeltaNanoseconds':0,'steadySlopeCPerMinute':-.315} for u in ids}}
        return result,analysis,rows
    def test_periodic_cycle_means_are_stable(self):
        x=m.evaluate(*self.data());self.assertEqual(x['status'],'pass');self.assertEqual(x['cycleSpanSeconds'],180)
        self.assertTrue(all(abs(g['completeCycleSlopeCPerMinute'])<1e-9 for g in x['gpu'].values()))
        self.assertEqual(x['rawQualificationUnchanged'],'not-qualified')
    def test_real_heating_and_cooling_are_rejected(self):
        for drift in (.4,-.4):self.assertEqual(m.evaluate(*self.data(drift))['status'],'not-qualified')
    def test_raw_overtemperature_cannot_be_averaged_away(self):
        r,a,t=self.data();t[5]['gpus'][0]['coreC']=83
        with self.assertRaises(AssertionError):m.evaluate(r,a,t)
    def test_rejected_transition_peak_is_retained(self):
        r,a,t=self.data();raw=copy.deepcopy(t[-1]);raw['gpus'][0]['coreC']=83
        with self.assertRaises(AssertionError):m.evaluate(r,a,t,[raw])
    def test_cap_change_and_thermal_counter_fail(self):
        r,a,t=self.data();t[-5]['gpus'][0]['enforcedPowerW']=250
        with self.assertRaises(AssertionError):m.evaluate(r,a,t)
        r,a,t=self.data();a['gpu']['gpu0']['thermalViolationDeltaNanoseconds']=1
        with self.assertRaises(AssertionError):m.evaluate(r,a,t)
    def test_sample_gap_fails(self):
        r,a,t=self.data();del t[-100:-90]
        with self.assertRaises(AssertionError):m.evaluate(r,a,t)
    def test_incomplete_cycles_or_overlap_fail(self):
        r,a,t=self.data();r['waves']=r['waves'][-5:]
        with self.assertRaises(AssertionError):m.evaluate(r,a,t)
        r,a,t=self.data();r['waves'][-1]['startMonotonic']-=10
        with self.assertRaises(AssertionError):m.evaluate(r,a,t)
    def test_other_original_failures_cannot_be_relabelled(self):
        r,a,t=self.data();a['reasons'].append('Emergency cooling needed')
        with self.assertRaises(AssertionError):m.evaluate(r,a,t)
if __name__=='__main__':unittest.main(verbosity=2)
