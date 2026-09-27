"""Bounded benchmark readback of a sequential eight-fan write.

Retain every rejected raw observation; never change controller decisions.
An unresolved mismatch or any observed90C condition still fails the trial.
"""
import math,time

def read(hardware,primary_reader,retain_transition,clock=time.monotonic,sleep=time.sleep,budget=.25):
    assert 0<budget<=.25
    began=clock();attempts=0;retry_since=None
    while True:
        before=primary_reader();sample=hardware.read();after=primary_reader();now=clock();attempts+=1
        if max(g['coreC'] for g in sample['gpus'])>=90:
            retain_transition({'reason':'critical-temperature','sample':sample})
            raise RuntimeError('Critical thermal cutoff during coherent observation')
        fans=[f for g in sample['gpus'] for f in g['fans']];target=after.get('targetPercent')
        def valid(p):
            tick=p.get('monotonic')
            return p.get('source')=='uniform-controller-v2' and p.get('bootId')==sample['bootId'] and type(tick) in (int,float) and math.isfinite(tick) and 0<=now-tick<=5
        coherent=valid(before) and valid(after) and before.get('pid')==after.get('pid') and type(after.get('pid')) is int and type(target) is int and 30<=target<=100 and before.get('targetPercent')==target and len(fans)==8 and all(f['policy']==1 and f['target']==target for f in fans)
        if coherent and (retry_since is None or now-retry_since<=budget):
            sample['fanObservation']={'method':'bounded coherent manual readback','attempts':attempts,'elapsedSeconds':now-began,'retryElapsedSeconds':0 if retry_since is None else now-retry_since,'budgetSeconds':budget,'budgetAppliesTo':'after first incoherent observation; baseline NVML read retains its5s sensor deadline','rawRejectedObservations':attempts-1}
            return sample
        if retry_since is None:retry_since=now
        retain_transition({'reason':'serial-target-or-status-transition','sample':sample,'beforePrimary':{k:before.get(k) for k in ('source','bootId','pid','monotonic','targetPercent')},'afterPrimary':{k:after.get(k) for k in ('source','bootId','pid','monotonic','targetPercent')},'elapsedSeconds':now-began})
        if now-retry_since>=budget:raise RuntimeError('Uniform manual readback not coherent within250ms after first mismatch')
        sleep(min(.02,budget-(now-retry_since)))
