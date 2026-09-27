"""One prospectively declared replacement of a thermally ineligible pair.

No controller, sampler, plateau, performance threshold, or accepted data edits.
Preparation is separate from execution. The original failed run stays intact.
"""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path

B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');E=B/'evidence'
PARENT='v2-matched-cycle30-base80';SERIES=PARENT+'-r2'
PARENT_SHA='3208d9e69fa6b39752ae9a626969bc46ea03b96c52662afc71b795c225175b31'
CANDIDATE_SHA='2881a6d108a4c9a145b7c97a1f2cefd72f94a5be403cda356147fdbea518f7f6'
OWNED_ID='7b25db6a9d1a6bd3f6b3e35077b5ccae0aa8e7ee9829b966e8098d0f6b016971'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())

def prepare():
    old=E/(PARENT+'-spec.json');assert digest(old)==PARENT_SHA
    spec=read(old);terminal=E/(PARENT+'-runner/result.json')
    assert read(terminal)['status']=='error'
    failed=E/spec['pairs'][2]['reference'];result=read(failed/'result.json')
    analysis=read(failed/'analysis.json');plateau=read(failed/'plateau-analysis.json')
    assert result['status']=='ok' and plateau['status']=='not-qualified'
    assert plateau['reasons'] and all(r.endswith(': complete-cycle trend exceeds0.3C/min') for r in plateau['reasons'])
    assert plateau['originalAnalysisSha256']==digest(failed/'analysis.json')
    assert all(g['peakCoreC']<=82 and g['requestedCapRangeW']==[275,275] and g['enforcedCapRangeW']==[275,275] and g['thermalViolationDeltaNanoseconds']==0 for g in analysis['gpu'].values())
    assert not (E/spec['pairs'][2]['candidate']).exists()
    for pair in spec['pairs'][:2]:
        for phase in pair.values():
            assert read(E/phase/'result.json')['status']=='ok'
            assert read(E/phase/'plateau-analysis.json')['status']=='pass'
        assert read(E/pair['candidate']/'result.json')['profileSha256']==CANDIDATE_SHA
    assert digest(B/'v3-temperature-plateau.py')==spec['plateauSourceSha256']
    assert digest(B/'v3-compare-pairs.py')==spec['comparisonSourceSha256']
    assert digest(Path('/etc/mmbt/gpu-profile.json'))==CANDIDATE_SHA
    spec['pairs'][2]={'reference':SERIES+'-p3-ref85','candidate':SERIES+'-p3-candidate'}
    spec['amendment']={'originalSpecSha256':PARENT_SHA,'retainedPairs':[1,2],'excludedReference':failed.name,'excludedAnalysisSha256':digest(failed/'analysis.json'),'excludedPlateauSha256':digest(failed/'plateau-analysis.json'),'terminalReceiptSha256':digest(terminal),'reason':plateau['reasons'],'decision':'One entire third-pair replacement declared before either new measurement. Preserve original unsteady reference. Retain the two already eligible pairs from this same study/boot/configuration, all sources, windows and thresholds. No new campaign or retrospective relabeling.','repetitionLimit':1,'candidateProfileSha256':CANDIDATE_SHA}
    path=E/(SERIES+'-spec.json');folder=E/(SERIES+'-runner')
    assert not path.exists() and not folder.exists()
    assert all(not (E/phase).exists() for phase in spec['pairs'][2].values())
    path.write_text(json.dumps(spec,indent=2)+'\n');folder.mkdir()
    receipt={'status':'prepared','specSha256':digest(path),'driverSha256':digest(Path(__file__)),'completed':[]}
    (folder/'result.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'prospectiveSpec':path.name,'sha256':digest(path),'excludedReference':failed.name,'repetitionLimit':1}),flush=True)

def execute():
    path=E/(SERIES+'-spec.json');folder=E/(SERIES+'-runner');record=read(folder/'result.json');spec=read(path)
    assert record['status']=='prepared' and digest(path)==record['specSha256']
    assert digest(Path(__file__))==record['driverSha256']
    assert spec['amendment']['originalSpecSha256']==PARENT_SHA
    assert digest(E/(PARENT+'-spec.json'))==PARENT_SHA
    assert spec['amendment']['repetitionLimit']==1
    assert digest(Path('/etc/mmbt/gpu-profile.json'))==CANDIDATE_SHA
    assert subprocess.check_output(['docker','inspect','--format','{{.Id}}','mmbt-dsv41'],text=True).strip()==OWNED_ID
    state=json.loads(subprocess.check_output(['docker','inspect','--format','{{json .State}}','mmbt-dsv41'],text=True))
    assert state['Running']
    if state['Paused']:subprocess.run([sys.executable,str(B/'v2-resume-owned.py')],check=True)
    record['status']='starting';(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    try:
        for role in ('reference','candidate'):
            assert digest(B/'v3-temperature-plateau.py')==spec['plateauSourceSha256']
            assert digest(B/'v3-compare-pairs.py')==spec['comparisonSourceSha256']
            phase=spec['pairs'][2][role]
            command=[sys.executable,str(B/'v2-run-screen.py'),'fixed85' if role=='reference' else 'curve',phase,'--seconds','1800']
            if role=='candidate':command+=['--startup-floor','80','--startup-seconds','30']
            subprocess.run(command,check=True)
            subprocess.run([sys.executable,str(B/'v3-temperature-plateau.py'),str(E),phase],check=True)
            p=read(E/phase/'plateau-analysis.json');assert p['status']=='pass',p['reasons']
            record['completed'].append(phase);(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
        comparison=E/(SERIES+'-comparison.json')
        subprocess.run([sys.executable,str(B/'v3-compare-pairs.py'),str(E),str(path),str(comparison)],check=True)
        record.update(status='complete',comparisonStatus=read(comparison)['status'])
    except BaseException as error:
        record.update(status='error',error=type(error).__name__+': '+str(error))
        (folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
        raise
    (folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','execute']);a=p.parse_args()
    prepare() if a.action=='prepare' else execute()
