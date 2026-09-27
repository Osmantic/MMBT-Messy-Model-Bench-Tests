"""Boundary and fault-contract tests. No GPU or Docker access."""
import copy,json,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import common,hardware,observer,policy,recovery,workload,controller
from common import UUIDS
IDS=sorted(UUIDS);BOOT='11111111-1111-1111-1111-111111111111'
def rows(core=78,util=90):return [{'uuid':u,'coreC':core,'utilizationGpu':util} for u in IDS]
class PurePolicy(unittest.TestCase):
    def make(self):return policy.Policy(IDS,{'power_limit_w':275,'mode':'curve'})
    def test_hottest_card_and_emergency(self):
        for u in IDS:
            p=self.make();r=rows(40,0);r[IDS.index(u)]['coreC']=82
            self.assertEqual(p.update(r,1),86)
            r[IDS.index(u)]['coreC']=85;self.assertEqual(p.update(r,2),95)
            r[IDS.index(u)]['coreC']=90;self.assertEqual(p.update(r,3),100)
    def test_invalid_inputs_do_not_change_state(self):
        bad=[]
        for k,v in [('coreC',True),('coreC',float('nan')),('coreC',-1),('utilizationGpu',101),('uuid',IDS[0])]:
            r=rows();r[1][k]=v;bad.append(r)
        bad.extend([rows()[:3],rows()+[rows()[0]]])
        for r in bad:
            p=self.make();before=copy.deepcopy(p.__dict__)
            with self.assertRaises(ValueError):p.update(r,1)
            self.assertEqual(before,p.__dict__)
    def test_invalid_clocks(self):
        for t in (0,-1,6,float('nan'),True):
            p=self.make();p.update(rows(),0);before=copy.deepcopy(p.__dict__)
            with self.assertRaises(ValueError):p.update(rows(),t)
            self.assertEqual(before,p.__dict__)
    def test_curve_and_configuration_validation(self):
        for curve in ([[40,30],[88,True]],[[40,50],[88,40]],[[40,30],[82,86]],[[40,30],[40,40],[88,100]]):
            with self.assertRaises(ValueError):policy.validate_curve(curve)
        for cap in (True,274,600):
            with self.assertRaises(ValueError):policy.settings({'mode':'curve','power_limit_w':cap})
        with self.assertRaises(ValueError):policy.settings({'mode':'fixed','power_limit_w':275,'fixed_percent':80,'curve':[]})
    def test_idle_quiet_and_load_start_floor(self):
        p=self.make()
        for t in range(100):p.update(rows(40,0),t)
        self.assertEqual(p.target,30)
        self.assertEqual(p.update(rows(40,80),100),80)
        for t in range(101,130):self.assertEqual(p.update(rows(40,80),t),80)
        for t in range(130,155):p.update(rows(40,80),t)
        self.assertLess(p.target,80)
    def test_short_wave_gaps_do_not_rearm_startup(self):
        p=self.make()
        for t in range(100):p.update(rows(70,90 if t%31 else 0),t)
        self.assertEqual(p.startup_until,31)
        self.assertLess(p.target,80)
    def test_cooling_dwell_and_immediate_hot_response(self):
        p=self.make()
        for t in range(20):self.assertEqual(p.update(rows(75,0),t),80)
        self.assertEqual(p.update(rows(75,0),20),79)
        self.assertEqual(p.update(rows(81,90),21),83)
    def test_fixed_baseline_remains_uniform_but_protected(self):
        p=policy.Policy(IDS,{'mode':'fixed','power_limit_w':275,'fixed_percent':80})
        self.assertEqual(p.update(rows(40,0),1),80)
        self.assertEqual(p.update(rows(84,90),2),92)
    def test_hot_restart_never_reduces_existing_emergency_demand_to80(self):
        for mode,core,expected in [('curve',70,80),('curve',82,86),('curve',88,100),('fixed',90,100)]:
            cfg={'mode':mode,'power_limit_w':275}
            if mode=='fixed':cfg['fixed_percent']=85
            p=policy.Policy(IDS,cfg)
            self.assertEqual(controller.startup_target(p,{'gpus':rows(core)}),expected)
    def test_lower_startup_floor_preserves_active_floor_and_hot_response(self):
        p=policy.Policy(IDS,{'mode':'curve','power_limit_w':275,'startup_floor':65,'startup_seconds':15})
        for t in range(100):p.update(rows(40,0),t)
        self.assertEqual(p.target,30)
        for t in range(100,120):self.assertEqual(p.update(rows(40,90),t),65)
        self.assertEqual(p.update(rows(81,90),120),83)
class Fake:
    NVML_TEMPERATURE_GPU=0
    def __init__(self):self.caps=dict.fromkeys(IDS,275000);self.enforcements=dict.fromkeys(IDS,275000);self.writes=[];self.policies={(u,f):1 for u in IDS for f in (0,1)};self.targets=dict.fromkeys(self.policies,80);self.fail=None
    @property
    def cap(self):return self.caps[IDS[0]]
    @cap.setter
    def cap(self,value):self.caps=dict.fromkeys(IDS,value)
    @property
    def enforced(self):return self.enforcements[IDS[0]]
    @enforced.setter
    def enforced(self,value):self.enforcements=dict.fromkeys(IDS,value)
    def nvmlInit(self):pass
    def nvmlShutdown(self):pass
    def nvmlDeviceGetCount(self):return 4
    def nvmlDeviceGetHandleByIndex(self,i):return IDS[i]
    def nvmlDeviceGetUUID(self,h):return h
    def nvmlDeviceGetNumFans(self,h):return 2
    def nvmlDeviceGetPowerManagementLimit(self,h):return self.caps[h]
    def nvmlDeviceGetEnforcedPowerLimit(self,h):return self.enforcements[h]
    def nvmlDeviceSetPowerManagementLimit(self,h,p):self.caps[h]=p;self.enforcements[h]=p;self.writes.append(('cap',h,p))
    def nvmlDeviceGetFanControlPolicy_v2(self,h,f):return self.policies[h,f]
    def nvmlDeviceGetTargetFanSpeed(self,h,f):return self.targets[h,f]
    def nvmlDeviceGetFanSpeed_v2(self,h,f):return self.targets[h,f]
    def nvmlDeviceGetTemperature(self,h,x):return 70
    def nvmlDeviceGetUtilizationRates(self,h):return SimpleNamespace(gpu=90)
    def nvmlDeviceSetDefaultFanSpeed_v2(self,h,f):
        self.writes.append(('default',h,f))
        if (h,f)==self.fail:raise RuntimeError('Injected fan failure')
        self.policies[h,f]=0
    def nvmlDeviceSetFanSpeed_v2(self,h,f,p):self.writes.append(('manual',h,f,p));self.policies[h,f]=1;self.targets[h,f]=p
class HardwareTests(unittest.TestCase):
    def make(self):
        n=Fake();h=hardware.Hardware(n);h.rpm=lambda *args:2000;h.open();return n,h
    def test_auto_restores_every_fan_and_reads_back(self):
        n,h=self.make();r=h.automatic(SimpleNamespace(fd=1))
        self.assertTrue(r['verifiedAutomatic']);self.assertEqual(len([w for w in n.writes if w[0]=='default']),8)
    def test_partial_failure_still_attempts_all8_and_never_claims_success(self):
        n,h=self.make();n.fail=(IDS[0],0)
        with self.assertRaises(RuntimeError):h.automatic(SimpleNamespace(fd=1))
        self.assertEqual(len(n.writes),8)
    def test_no_write_without_ownership(self):
        n,h=self.make()
        for operation in (lambda:h.command(80,SimpleNamespace(fd=None)),lambda:h.automatic(SimpleNamespace(fd=None))):
            with self.assertRaises(RuntimeError):operation()
        self.assertFalse(n.writes)
    def test_caps_precede_any_fan_writes(self):
        n,h=self.make();n.cap=600000;n.enforced=600000
        with self.assertRaises(ValueError):h.command(80,SimpleNamespace(fd=1))
        self.assertFalse(n.writes)
        h.automatic(SimpleNamespace(fd=1));self.assertTrue(all(w[0]=='cap' for w in n.writes[:4]))
    def test_no_temperatures_needed_for_auto_proof(self):
        n,h=self.make();n.nvmlDeviceGetTemperature=lambda *args:(_ for _ in ()).throw(ValueError('No temps'))
        self.assertTrue(h.automatic(SimpleNamespace(fd=1))['verifiedAutomatic'])
    def test_lower_enforced_cap_recorded_truthfully(self):
        n,h=self.make();n.enforced=270000
        self.assertTrue(all(g['enforcedPowerW']==270 for g in h.read()['gpus']))
    def test_settling_deadline_is_not_reset_by_target_changes(self):
        n,h=self.make();s=h.read();transitions={}
        for g in s['gpus']:
            for f in g['fans']:f['target']=50;f['current']=80
        self.assertFalse(hardware.manual_proof(s,50,transitions,1))
        for g in s['gpus']:
            for f in g['fans']:f['target']=45
        with self.assertRaises(ValueError):hardware.manual_proof(s,45,transitions,17)
class ObserverTests(unittest.TestCase):
    def sample(self,automatic=False,core=70):
        return {'bootId':BOOT,'monotonic':100,'gpus':[{'uuid':u,'coreC':core,'utilizationGpu':90,'requestedPowerW':275,'enforcedPowerW':275,'fans':[{'fan':f,'policy':0 if automatic else 1,'target':80,'current':80,'rpm':2000} for f in (0,1)]} for u in IDS]}
    def primary(self,ready=True):return {'bootId':BOOT,'monotonic':100,'source':'uniform-controller-v2','targetPercent':80,'ready':ready}
    def test_manual_continuity(self):
        d=observer.assess(self.sample(),self.primary(),101,BOOT,None);self.assertTrue(d['healthy']);self.assertFalse(d['suspend'])
    def test_independent_observer_rejects_stall_despite_ready_flag(self):
        s=self.sample();s['gpus'][0]['fans'][0]['rpm']=0
        d=observer.assess(s,self.primary(),101,BOOT,None,{})
        self.assertFalse(d['healthy']);self.assertTrue(d['requestRecovery'])
    def test_independent_settling_deadline_cannot_be_renewed_by_targets(self):
        transitions={}
        for now,target in ((100,80),(110,60),(116,80)):
            s=self.sample();p=self.primary();s['monotonic']=p['monotonic']=now;p['targetPercent']=target
            for g in s['gpus']:
                for f in g['fans']:f['target']=target;f['current']=100
            d=observer.assess(s,p,now,BOOT,None,transitions)
        self.assertFalse(d['healthy']);self.assertTrue(d['requestRecovery'])
    def test_auto_bridge_expires(self):
        s=self.sample(True);s['monotonic']=130
        self.assertFalse(observer.assess(s,None,130,BOOT,100)['suspend'])
        self.assertTrue(observer.assess(s,None,131,BOOT,100)['suspend'])
    def test_corrupt_recovery_timer_cannot_allow_indefinite_auto(self):
        for value in (float('nan'),float('inf'),True,-1,102):
            with self.assertRaises(ValueError):observer.assess(self.sample(True),None,101,BOOT,value)
    def test_startup_does_not_kill_new_writer(self):
        d=observer.assess(self.sample(),self.primary(False),101,BOOT,None)
        self.assertEqual(d['mode'],'starting');self.assertFalse(d['requestRecovery'])
    def test_critical_in_auto_is_not_continuity(self):
        d=observer.assess(self.sample(True,90),None,101,BOOT,None);self.assertTrue(d['critical']);self.assertTrue(d['suspend'])
    def test_stale_or_foreign_boot_is_not_ready(self):
        p=self.primary();p['monotonic']=1
        self.assertFalse(observer.assess(self.sample(),p,101,BOOT,None)['healthy'])
        p=self.primary();p['bootId']='22222222-2222-2222-2222-222222222222'
        self.assertFalse(observer.assess(self.sample(),p,101,BOOT,None)['healthy'])
    def test_invalid_independent_sample_cannot_preserve_continuity(self):
        changes=[lambda s:s['gpus'].pop(),lambda s:s['gpus'][0].update(uuid=IDS[1]),lambda s:s['gpus'][0].update(enforcedPowerW=600),lambda s:s['gpus'][0]['fans'].pop(),lambda s:s['gpus'][0].update(coreC=float('nan'))]
        for change in changes:
            s=self.sample();change(s)
            with self.assertRaises(ValueError):observer.assess(s,self.primary(),101,BOOT,None)
class RecoveryTests(unittest.TestCase):
    def test_logging_failure_follows_verified_automatic_restoration(self):
        actions=[]
        sample={'gpus':[{'coreC':70}],'bootId':BOOT,'monotonic':100}
        h=SimpleNamespace(read=lambda:sample,automatic=lambda lease:(actions.append('automatic') or {'verifiedAutomatic':True,'monotonic':100,'bootId':BOOT}))
        with tempfile.TemporaryDirectory() as d,patch.object(recovery,'STATE',Path(d)),patch.object(recovery,'recovery_since',return_value=time.monotonic()),patch.object(recovery,'event',side_effect=OSError('Read-only log')):
            with self.assertRaises(OSError):recovery.handoff(h,SimpleNamespace(fd=1),'log fault')
            self.assertTrue(json.loads((Path(d)/'fallback.json').read_text())['verifiedAutomatic'])
        self.assertEqual(actions,['automatic'])
    def test_expired_repeated_restoration_cannot_preserve_inference(self):
        actions=[];h=SimpleNamespace(read=lambda:{'gpus':[{'coreC':70}]},automatic=lambda lease:{'verifiedAutomatic':True})
        with tempfile.TemporaryDirectory() as d,patch.object(recovery,'STATE',Path(d)),patch.object(recovery,'recovery_since',return_value=time.monotonic()-31),patch.object(recovery,'event'),patch.object(recovery,'suspend',side_effect=lambda reason:actions.append('suspend')):
            r=recovery.handoff(h,SimpleNamespace(fd=1),'repeat')
        self.assertTrue(r['verifiedAutomatic']);self.assertEqual(actions,['suspend'])
    def test_partial_automatic_failure_suspends_after_all8_attempts(self):
        n=Fake();h=hardware.Hardware(n);h.rpm=lambda *args:2000;n.fail=(IDS[0],0);actions=[]
        fake_suspend=lambda reason:actions.append(('suspend',len(n.writes)))
        with tempfile.TemporaryDirectory() as d,patch.object(recovery,'STATE',Path(d)),patch.object(recovery,'Lease',side_effect=lambda:common.Lease(Path(d)/'lease')),patch.object(recovery,'Hardware',return_value=h),patch.object(recovery,'suspend',side_effect=fake_suspend),patch.object(recovery,'event'),patch.dict('sys.modules',{'pynvml':n}),patch('sys.argv',['recovery.py']):
            self.assertEqual(recovery.restore_once('Injected partial failure'),1)
        self.assertEqual(actions,[('suspend',8)])
    def test_blocked_native_helper_is_killed_then_workload_suspended(self):
        actions=[]
        class Child:
            returncode=None
            def communicate(self,timeout):raise recovery.subprocess.TimeoutExpired('native child',timeout)
            def kill(self):actions.append('kill-helper')
        with patch.object(recovery.subprocess,'Popen',return_value=Child()),patch.object(recovery,'suspend',side_effect=lambda reason:actions.append('suspend')):
            self.assertEqual(recovery.supervised_restore('NVML blocked'),1)
        self.assertEqual(actions,['kill-helper','suspend'])
    def test_repeated_handoffs_do_not_renew_deadline(self):
        with tempfile.TemporaryDirectory() as d,patch.object(common,'STATE',Path(d)),patch.object(common,'boot',return_value=BOOT):
            self.assertEqual(common.recovery_since('first',100),100)
            self.assertEqual(common.recovery_since('second',120),100)
    def test_critical_is_suspended_before_any_emergency_fan_write(self):
        events=[];h=SimpleNamespace(read=lambda:{'gpus':[{'coreC':90}]},command=lambda *args:events.append('cool'))
        with tempfile.TemporaryDirectory() as d,patch.object(recovery,'STATE',Path(d)),patch.object(recovery,'suspend',side_effect=lambda *args:events.append('suspend')),patch.object(recovery,'latch',side_effect=lambda *args:events.append('latch')):
            r=recovery.handoff(h,SimpleNamespace(fd=1),'test')
        self.assertEqual(events,['latch','suspend','cool']);self.assertFalse(r['verifiedAutomatic'])
    def test_critical_retains_emergency_cooling_when_docker_fails(self):
        actions=[];h=SimpleNamespace(read=lambda:{'gpus':[{'coreC':90}]},command=lambda *args:actions.append('cool'))
        with patch.object(recovery,'suspend',side_effect=RuntimeError('Docker unavailable')),patch.object(recovery,'latch') as critical_latch:
            with self.assertRaises(RuntimeError):recovery.handoff(h,SimpleNamespace(fd=1),'critical')
        critical_latch.assert_called_once()
        self.assertEqual(actions,['cool'])
    def test_failed_inspection_still_attempts_suspension(self):
        with tempfile.TemporaryDirectory() as d,patch.object(common,'STATE',Path(d)),patch.object(common,'boot',return_value=BOOT),patch.object(workload,'inspect',side_effect=RuntimeError('inspect unavailable')),patch.object(workload,'kernel_freeze',return_value={'running':True,'paused':True,'method':'owned-cgroup-freezer'}) as freeze:
            self.assertTrue(common.suspend('fault')['paused'])
        freeze.assert_called_once_with()
    def test_docker_error_does_not_invalidate_gpu_sample(self):
        with patch.object(workload,'inspect',side_effect=RuntimeError('Docker unavailable')):
            state,error=observer.workload_state()
        self.assertIsNone(state);self.assertIn('Docker unavailable',error)
        self.assertTrue(observer.assess(ObserverTests().sample(),ObserverTests().primary(),101,BOOT,None)['healthy'])
    def test_failed_suspend_still_latches_and_returns_control_error(self):
        with patch.object(observer,'suspend',side_effect=RuntimeError('pause failure')),patch.object(observer,'latch') as critical_latch:
            errors=observer.attempt_suspend('critical',{},True)
        critical_latch.assert_called_once();self.assertEqual(errors,['suspension: pause failure'])
    def test_failed_cache_write_does_not_hide_running_runtime(self):
        row={'state':{'Running':True,'Paused':False}}
        with patch.object(workload,'inspect',return_value=row),patch.object(workload,'remember',side_effect=OSError('cache read-only')):
            state,error=observer.workload_state()
        self.assertTrue(state['Running']);self.assertIn('cache read-only',error)
class WorkloadTests(unittest.TestCase):
    CID='a'*64
    def identity(self):return {'bootId':BOOT,'id':self.CID,'image':workload.IMAGE,'pid':42,'startTicks':999,'cgroup':'/system.slice/docker-'+self.CID+'.scope'}
    def test_identity_boundaries_reject_boot_image_pid_reuse_and_cgroup(self):
        good=self.identity()
        with tempfile.TemporaryDirectory() as d,patch.object(workload,'CGROUP',Path(d)),patch.object(workload,'boot',return_value=BOOT):
            path=Path(d)/good['cgroup'].lstrip('/');path.mkdir(parents=True);(path/'cgroup.procs').write_text('42\n')
            with patch.object(workload,'process_identity',return_value=(999,good['cgroup'])):
                self.assertEqual(workload.validate(good),path)
                for key,value in [('bootId','other'),('image','other'),('id','../foreign'),('pid',True),('startTicks',True),('startTicks',1000),('cgroup','/system.slice/foreign.scope')]:
                    bad=good.copy();bad[key]=value
                    with self.subTest(key=key,value=value):
                        # mocked process_identity must still enforce genuine PID type.
                        if key=='pid':
                            with patch.object(workload,'process_identity',side_effect=ValueError('Invalid PID')):
                                with self.assertRaises(ValueError):workload.validate(bad)
                        else:
                            with self.assertRaises(ValueError):workload.validate(bad)
                (path/'cgroup.procs').write_text('43\n')
                with self.assertRaises(ValueError):workload.validate(good)
    def test_process_start_clock_handles_comm_spaces_and_parentheses(self):
        with tempfile.TemporaryDirectory() as d,patch.object(workload,'PROC',Path(d)):
            p=Path(d)/'42';p.mkdir();(p/'stat').write_text('42 (owned (complex) process) '+' '.join(['S']+['0']*18+['999']+['0']*4))
            (p/'cgroup').write_text('0::/system.slice/docker-'+self.CID+'.scope\n')
            self.assertEqual(workload.process_identity(42),(999,'/system.slice/docker-'+self.CID+'.scope'))
            for pid in (True,1,-1,'42'):
                with self.assertRaises(ValueError):workload.process_identity(pid)
    def test_dead_docker_uses_no_docker_mutation(self):
        with patch.object(workload,'inspect',side_effect=TimeoutError()),patch.object(workload,'kernel_freeze',return_value={'paused':True}) as freeze,patch.object(workload.subprocess,'run') as command:
            self.assertTrue(workload.pause()['paused'])
        freeze.assert_called_once();command.assert_not_called()
    def test_cache_failure_still_verifies_successful_docker_pause(self):
        row={'state':{'Running':True,'Paused':False}};paused={'state':{'Running':True,'Paused':True}}
        with patch.object(workload,'inspect',side_effect=[row,paused]),patch.object(workload,'remember',side_effect=OSError()),patch.object(workload,'kernel_freeze',side_effect=ValueError()),patch.object(workload.subprocess,'run') as command:
            self.assertEqual(workload.pause()['method'],'docker-state')
        self.assertEqual(command.call_args.kwargs['timeout'],2)
        self.assertEqual(command.call_args.args[0],['docker','pause','mmbt-dsv41'])
    def test_failed_docker_pause_uses_kernel_identity(self):
        with patch.object(workload,'inspect',return_value={'state':{'Running':True,'Paused':False}}),patch.object(workload,'remember'),patch.object(workload.subprocess,'run',side_effect=TimeoutError()),patch.object(workload,'kernel_freeze',return_value={'paused':True}) as freeze:
            self.assertTrue(workload.pause()['paused'])
        freeze.assert_called_once()
    def test_unconfirmed_pause_never_returns_success(self):
        row={'state':{'Running':True,'Paused':False}}
        with patch.object(workload,'inspect',return_value=row),patch.object(workload,'remember'),patch.object(workload,'kernel_freeze',side_effect=ValueError()),patch.object(workload.subprocess,'run'):
            with self.assertRaises(RuntimeError):workload.pause()
    def test_foreign_cache_blocks_kernel_write(self):
        with patch.object(workload,'cached',side_effect=ValueError('Foreign')),patch.object(workload.os,'write') as write:
            with self.assertRaises(ValueError):workload.kernel_freeze()
        write.assert_not_called()
    def test_paused_docker_needs_no_mutation(self):
        with patch.object(workload,'inspect',return_value={'state':{'Running':True,'Paused':True}}),patch.object(workload.subprocess,'run') as run:
            self.assertTrue(workload.pause()['paused'])
        run.assert_not_called()
class LeaseTests(unittest.TestCase):
    def test_stable_inode_and_exclusive_ownership(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'lease'
            with common.Lease(p):
                inode=p.stat().st_ino
                with self.assertRaises(BlockingIOError):
                    with common.Lease(p):pass
            with common.Lease(p):self.assertEqual(p.stat().st_ino,inode)
if __name__=='__main__':unittest.main(verbosity=2)
