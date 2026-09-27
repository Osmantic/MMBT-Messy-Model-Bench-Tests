"""Independent sensor and workload observer, never a fan writer."""
import json,os,signal,subprocess,threading,time
from pathlib import Path
from common import STATE,atomic,boot,docker_state,event,fresh,latch,notify,suspend,utc,validate_sample,recovery_since,real
from hardware import Hardware,manual_proof
import workload

def workload_state():
    """Docker failure is workload visibility loss, not GPU visibility loss."""
    try:
        row=workload.inspect()
        try:workload.remember(row)
        except Exception as exc:cache_error=type(exc).__name__+': '+str(exc)
        else:cache_error=None
        return row['state'],cache_error
    except Exception as exc:return None,type(exc).__name__+': '+str(exc)

def attempt_suspend(reason,sample,critical=False):
    errors=[]
    if critical:
        try:latch(reason,sample)
        except Exception as exc:errors.append('latch: '+str(exc))
    try:suspend(reason)
    except Exception as exc:errors.append('suspension: '+str(exc))
    return errors
def assess(sample,primary,now,current_boot,degraded_since,fan_transitions=None):
    validate_sample(sample,now,current_boot)
    critical=max(g['coreC'] for g in sample['gpus'])>=90
    fans=[f for g in sample['gpus'] for f in g['fans']]
    automatic=len(fans)==8 and all(f['policy']==0 for f in fans)
    transitions={} if fan_transitions is None else fan_transitions
    if automatic:transitions.clear()
    primary_ok=False;starting=False
    try:
        fresh(primary,now,current_boot)
        target=primary.get('targetPercent')
        if primary.get('source')!='uniform-controller-v2' or type(target) is not int or not 30<=target<=100:raise ValueError('Primary source/target differs')
        if not automatic:
            try:
                # Independently measure settling; never trust a ready flag alone.
                manual_proof(sample,target,transitions,now)
                transitions.pop('__mismatch__',None)
                primary_ok=primary.get('ready') is True
                starting=not primary_ok
            except ValueError:
                since=transitions.setdefault('__mismatch__',now)
                timed_out=any(now-start>15 for start in transitions.values())
                stalled=primary.get('ready') is True and any(f['rpm']<=0 for f in fans)
                starting=all(f['policy']==1 for f in fans) and not timed_out and not stalled
    except Exception:pass
    if primary_ok:return {'mode':'manual','healthy':True,'requestRecovery':False,'suspend':critical,'degradedSince':None,'critical':critical}
    since=now if degraded_since is None else real(degraded_since,0,now)
    expired=now-since>30
    return {'mode':'automatic' if automatic else ('starting' if starting else 'recovery'),'healthy':automatic and not expired and not critical,'requestRecovery':not automatic and not starting,'suspend':critical or expired,'degradedSince':since,'critical':critical}
def main():
    stop=threading.Event()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *args:stop.set())
    import pynvml
    h=Hardware(pynvml);h.open();degraded=None;recovery_requested=False;notified=False;critical_started=None;fan_transitions={}
    try:
        while not stop.is_set():
            began=time.monotonic();sample=None
            try:
                sample=h.read()
                try:primary=json.loads((STATE/'status.json').read_text())
                except (FileNotFoundError,ValueError):primary=None
                episode=STATE/'recovery-episode.json'
                if degraded is None and episode.exists():
                    previous=json.loads(episode.read_text())
                    if previous.get('bootId')==boot():degraded=previous['monotonic']
                decision=assess(sample,primary,time.monotonic(),boot(),degraded,fan_transitions);degraded=decision['degradedSince']
                state,workload_error=workload_state()
                active=None if state is None else state['Running'] and not state['Paused']
                control_errors=[]
                memory=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024
                if decision['critical']:
                    if critical_started is None:critical_started=time.monotonic()
                    control_errors+=attempt_suspend('Independent observer saw90C',sample,True)
                    # CPU pause does not cancel already submitted GPU work.
                    if time.monotonic()-critical_started>10 and any(g['coreC']>=90 and g['utilizationGpu']>=10 for g in sample['gpus']):
                        try:workload.stop_critical()
                        except Exception as exc:control_errors.append('critical-stop: '+str(exc))
                else:critical_started=None
                if active is not False and memory<10*2**30:control_errors+=attempt_suspend('Available RAM below10GiB',sample,True)
                if decision['suspend'] and not decision['critical']:control_errors+=attempt_suspend('Custom cooling recovery exceeded30s',sample)
                if (STATE/'critical-latch.json').exists() and active is not False and not decision['critical']:
                    control_errors+=attempt_suspend('Critical latch remains active',sample)
                if decision['requestRecovery'] and not recovery_requested:
                    subprocess.run(['systemctl','kill','--signal=SIGKILL','mmbt-gpu-control.service'],capture_output=True,timeout=3)
                    recovery_requested=True;event('primary-recovery-requested')
                if decision['mode']=='manual':
                    recovery_requested=False
                    episode.unlink(missing_ok=True)
                sample.update(source='independent-observer-v2',pid=os.getpid(),**decision,active=active,workloadStateKnown=state is not None,workloadError=workload_error,controlErrors=control_errors,availableBytes=memory,latchPresent=(STATE/'critical-latch.json').exists())
                atomic(STATE/'watchdog-status.json',sample)
                if not notified:notify('READY=1');notified=True
                notify('WATCHDOG=1')
            except Exception as exc:
                # The sample can fail while fan policy/cap reads still work.
                if degraded is None:degraded=recovery_since('Observer visibility failure')
                confirmed=False;caps_confirmed=False
                try:proof=h.read(temperature=False);caps_confirmed=True;confirmed=all(f['policy']==0 for g in proof['gpus'] for f in g['fans'])
                except Exception:proof=None
                if not recovery_requested:
                    subprocess.run(['systemctl','kill','--signal=SIGKILL','mmbt-gpu-control.service'],capture_output=True,timeout=3);recovery_requested=True
                # Allow restoration up to15s, then require confirmed automatic.
                control_errors=[]
                if not caps_confirmed or (time.monotonic()-degraded>15 and not confirmed) or time.monotonic()-degraded>30:
                    control_errors=attempt_suspend('Observer visibility/automatic recovery unavailable',sample)
                atomic(STATE/'watchdog-status.json',{'source':'independent-observer-v2','bootId':boot(),'monotonic':time.monotonic(),'healthy':False,'mode':'visibility-recovery','error':type(exc).__name__+': '+str(exc),'automaticVerified':confirmed,'degradedSince':degraded,'controlErrors':control_errors,'latchPresent':(STATE/'critical-latch.json').exists()})
                notify('WATCHDOG=1')
            stop.wait(max(0,1-(time.monotonic()-began)))
    finally:
        try:(STATE/'watchdog-status.json').unlink(missing_ok=True)
        except Exception:pass
        h.close()
if __name__=='__main__':main()
