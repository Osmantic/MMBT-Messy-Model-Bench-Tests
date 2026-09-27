"""Explicit fresh installed-protection gate. Never resumes a latched workload."""
import json,time,subprocess
from common import STATE,BASE,boot,fresh,validate_sample,CONTAINER
IMAGE='sha256:a30e3c69e6a4de1b82e4893dfa971ab94cba126476e3a26f4d1da5d868fae04f'
def main():
    if (STATE/'critical-latch.json').exists():raise RuntimeError('Critical latch requires reviewed acknowledgment')
    now=time.monotonic();current=boot()
    primary=json.loads((STATE/'status.json').read_text());observer=json.loads((STATE/'watchdog-status.json').read_text())
    # Sample the clock after reads, avoiding the prior pre-inspect clock race.
    now=time.monotonic();fresh(primary,now,current);fresh(observer,now,current)
    validate_sample(primary,now,current);validate_sample(observer,now,current)
    if primary.get('source')!='uniform-controller-v2' or primary.get('ready') is not True or primary.get('allFansSettled') is not True:raise RuntimeError('Primary not ready')
    if observer.get('source')!='independent-observer-v2' or observer.get('mode')!='manual' or observer.get('healthy') is not True:raise RuntimeError('Observer not ready')
    target=primary.get('targetPercent')
    if type(target) is not int or not 30<=target<=100:raise RuntimeError('Uniform target differs')
    for sample in (primary,observer):
        if any(f['policy']!=1 or f['target']!=target or f['rpm']<=0 for g in sample['gpus'] for f in g['fans']):raise RuntimeError('All-eight manual proof differs')
    if any(g['coreC']>82 for g in observer['gpus']):raise RuntimeError('Startup thermal margin not ready')
    receipt=json.loads((BASE/'model-state/verification.json').read_text())
    if receipt.get('status')!='verified' or receipt.get('revision')!='fb2764a5cf321eaa5070ca8f9e892818f477c16d' or len(receipt.get('files',[]))!=88:raise RuntimeError('Checkpoint differs')
    image=subprocess.check_output(['docker','inspect','--format','{{.Image}}',CONTAINER],text=True,timeout=3).strip()
    if image!=IMAGE:raise RuntimeError('Native runtime image differs')
    print('Fresh uniform controller and independent observer ready')
if __name__=='__main__':main()
