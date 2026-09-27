"""Exclusive default-policy restoration, bounded model-preserving recovery."""
import argparse,json,subprocess,time
from common import STATE,Lease,atomic,boot,docker_state,event,fresh,latch,suspend,utc,recovery_since,validate_sample
from hardware import Hardware
def handoff(hardware,lease,reason):
    # A positively observed critical temperature gets strong cooling and a pause.
    try:current=hardware.read();critical=max(g['coreC'] for g in current['gpus'])>=90
    except Exception:current=None;critical=False
    if critical:
        try:
            latch('Critical temperature during handoff',current)
            suspend('Critical temperature during handoff')
        finally:hardware.command(100,lease)
        current.update(reason=reason,source='critical-emergency-handoff',verifiedAutomatic=False)
        atomic(STATE/'fallback.json',current)
        return current
    receipt=hardware.automatic(lease)
    receipt.update(reason=reason,source='automatic-handoff',pid=__import__('os').getpid())
    atomic(STATE/'fallback.json',receipt)
    since=recovery_since(reason)
    if time.monotonic()-since>30:suspend('Restoration recovery episode exceeded30s')
    event('automatic-handoff',reason=reason,verifiedAutomatic=True)
    return receipt
def restore_once(reason):
    success=False;h=None
    try:
        lease=Lease()
        for attempt in range(41):
            try:lease.__enter__();break
            except BlockingIOError:
                if attempt==40:raise
                time.sleep(.1)
        try:
            import pynvml
            h=Hardware(pynvml);h.open();handoff(h,lease,reason);success=True
        finally:lease.__exit__()
    except BlockingIOError:
        # A freshly healthy primary can legitimately have restarted before us.
        try:
            status=fresh(json.loads((STATE/'status.json').read_text()),time.monotonic(),boot())
            import pynvml
            h=Hardware(pynvml);h.open();sample=h.read();validate_sample(sample,time.monotonic(),boot())
            target=status.get('targetPercent')
            success=(status.get('ready') is True and status.get('source')=='uniform-controller-v2' and type(target) is int and
                all(f['policy']==1 and f['target']==target and f['rpm']>0 for g in sample['gpus'] for f in g['fans']))
        except Exception:pass
    except Exception as exc:
        try:event('handoff-failure',reason=reason,error=type(exc).__name__+': '+str(exc))
        except Exception:pass
    finally:
        if h is not None:
            try:h.close()
            except Exception:pass
    if not success:suspend('Automatic handoff could not be confirmed')
    return 0 if success else 1

def supervised_restore(reason):
    """The parent makes no NVML calls; blocked native calls die with the child."""
    import sys
    child=subprocess.Popen([sys.executable,'-u',__file__,'--restore-child','--reason',reason],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        stdout,stderr=child.communicate(timeout=12)
        if child.returncode==0:return 0
    except subprocess.TimeoutExpired:
        child.kill()
        try:child.communicate(timeout=2)
        except subprocess.TimeoutExpired:pass
    suspend('Restoration helper exceeded deadline or failed')
    return 1

def main():
    p=argparse.ArgumentParser();p.add_argument('--observer-exit',action='store_true');p.add_argument('--restore-child',action='store_true');p.add_argument('--reason',default='Controller service exit');args=p.parse_args()
    if args.restore_child:return restore_once(args.reason)
    reason='Observer service exit' if args.observer_exit else 'Controller service exit'
    if args.observer_exit:
        # A hung primary cannot defer restoration until its graceful-stop timeout.
        subprocess.run(['systemctl','kill','--signal=SIGKILL','mmbt-gpu-control.service'],capture_output=True,timeout=3)
        try:subprocess.run(['systemctl','stop','mmbt-gpu-control.service'],capture_output=True,timeout=20)
        except subprocess.TimeoutExpired:pass
    result=supervised_restore(reason)
    if args.observer_exit:subprocess.run(['systemctl','--no-block','start','mmbt-gpu-control.service'],capture_output=True,timeout=3)
    return result
if __name__=='__main__':raise SystemExit(main())
