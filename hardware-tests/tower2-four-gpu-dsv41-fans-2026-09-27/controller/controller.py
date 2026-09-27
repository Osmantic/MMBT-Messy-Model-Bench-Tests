"""One uniform fan writer. No automatic workload resumption."""
import argparse,json,os,signal,threading,time
from pathlib import Path
from common import STATE,UUIDS,Lease,atomic,event,latch,notify,suspend
from hardware import Hardware,manual_proof
from policy import Policy,settings
from recovery import handoff

def startup_target(policy,sample):
    # A restart must never lower an already-hot stack to the ordinary80% start.
    return max(policy.target,policy.demand(max(g['coreC'] for g in sample['gpus'])))
def run(config):
    stop=threading.Event()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *args:stop.set())
    h=None;notified=False;failed=False;transitions={};expected=None
    with Lease() as lease:
        try:
            import pynvml
            h=Hardware(pynvml);h.open();h.caps(repair=True)
            cfg=settings(json.loads(config.read_text()));policy=Policy(UUIDS,cfg)
            policy.target=startup_target(policy,h.read())
            h.command(policy.target,lease);expected=policy.target;first_command=time.monotonic()
            while not stop.is_set():
                began=time.monotonic();sample=h.read()
                # Initial ramps may have zero RPM briefly; never arm inference then.
                zero=any(f['rpm']==0 for g in sample['gpus'] for f in g['fans'])
                if zero and not notified and began-first_command<15:
                    settled=False
                    for g in sample['gpus']:
                        for f in g['fans']:
                            if f['policy']!=1 or f['target']!=expected:raise ValueError('Startup manual target differs')
                            f['settlingSince']=first_command
                else:settled=manual_proof(sample,expected,transitions,time.monotonic())
                maximum=max(g['coreC'] for g in sample['gpus'])
                if maximum>=90:
                    try:
                        latch('GPU reached90C',sample)
                        try:suspend('GPU reached90C')
                        except Exception as exc:event('suspension-failed',error=str(exc))
                    finally:
                        if expected!=100:h.command(100,lease);expected=100
                updated=settings(json.loads(config.read_text()))
                if updated!=cfg:
                    cfg=updated;policy=Policy(UUIDS,cfg)
                    event('configuration-reloaded',settings=cfg)
                target=policy.update(sample['gpus'],time.monotonic())
                if target!=expected:
                    h.command(target,lease);expected=target
                    sample=h.read();settled=manual_proof(sample,expected,transitions,time.monotonic())
                    event('fan-command',targetPercent=target,maxCoreC=maximum)
                sample.update(source='uniform-controller-v2',pid=os.getpid(),ready=notified or settled,allFansSettled=settled,targetPercent=expected,mode=cfg['mode'])
                atomic(STATE/'status.json',sample)
                if settled and not notified:notify('READY=1');notified=True
                notify('WATCHDOG=1')
                stop.wait(max(0,1-(time.monotonic()-began)))
        except Exception as exc:
            failed=True
            try:atomic(STATE/'last-fault-v2.json',{'utc':__import__('common').utc(),'error':type(exc).__name__+': '+str(exc)})
            except Exception:pass
            print(type(exc).__name__+': '+str(exc),flush=True)
        finally:
            # Restore cooling before any workload suspension on visibility failure.
            try:
                if h is None or not h.initialized:raise RuntimeError('NVML unavailable')
                handoff(h,lease,'Controller loop exit')
            except Exception as exc:
                failed=True
                try:suspend('Controller exit: automatic handoff not confirmed')
                except Exception:pass
            try:(STATE/'status.json').unlink(missing_ok=True)
            except Exception:pass
            if h is not None:
                try:h.close()
                except Exception:failed=True
    return 1 if failed else 0
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,default=Path('/etc/mmbt/gpu-profile.json'));args=p.parse_args()
    raise SystemExit(run(args.config))
