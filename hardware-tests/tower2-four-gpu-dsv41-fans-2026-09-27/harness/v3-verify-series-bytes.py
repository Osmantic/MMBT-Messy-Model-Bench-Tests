"""Independent completed-series byte proof; does not change original results."""
import argparse,datetime,hashlib,json
from pathlib import Path

def digest(path):
    assert path.is_file() and not path.is_symlink(),path.name
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify(root,comparison_file,live_controller=None,harness=None):
    assert Path(comparison_file).name==comparison_file and comparison_file.startswith('v2-matched-') and comparison_file.endswith('-comparison.json')
    comparison=json.loads((root/comparison_file).read_text());assert comparison['status']=='qualified'
    spec_file=comparison_file.replace('-comparison.json','-spec.json')
    spec=json.loads((root/spec_file).read_text());assert digest(root/spec_file)==comparison['specSha256']
    phases=[];candidate_pin=None;analysis_pin=None;source_pins=None
    for pair in spec['pairs']:
        for role in ('reference','candidate'):
            phase=pair[role];assert Path(phase).name==phase
            folder=root/phase;result=json.loads((folder/'result.json').read_text());analysis=json.loads((folder/'analysis.json').read_text())
            plateau=json.loads((folder/'plateau-analysis.json').read_text())
            assert result['status']=='ok' and plateau['status']=='pass'
            assert digest(folder/'profile.json')==result['profileSha256'],phase+': profile bytes differ'
            if role=='candidate':
                if candidate_pin is None:candidate_pin=result['profileSha256']
                assert candidate_pin==result['profileSha256']==comparison['candidateProfileSha256']
            assert digest(folder/'analysis.json')==plateau['originalAnalysisSha256']
            assert plateau['analysisSourceSha256']==spec['plateauSourceSha256']
            if analysis_pin is None:analysis_pin=analysis['analysisSourceSha256']
            assert analysis['analysisSourceSha256']==analysis_pin
            if source_pins is None:source_pins=result['sources']
            assert result['sources']==source_pins
            for name,pin in result['sources'].items():
                assert Path(name).name==name and name.endswith('.py')
                assert digest(folder/'sources'/name)==pin,phase+': source snapshot differs: '+name
                if live_controller is not None and (live_controller/name).is_file():
                    assert digest(live_controller/name)==pin,'Installed source differs: '+name
                elif harness is not None:
                    assert digest(harness/name)==pin,'Current harness differs: '+name
            if harness is not None:
                assert digest(harness/'v2-analyze-trial.py')==analysis_pin
                assert digest(harness/'v3-temperature-plateau.py')==spec['plateauSourceSha256']
                assert digest(harness/'v3-compare-pairs.py')==spec['comparisonSourceSha256']
            phases.append({'phase':phase,'profileSha256':result['profileSha256'],'sourceFiles':len(result['sources']),'resultSha256':digest(folder/'result.json'),'analysisSha256':digest(folder/'analysis.json'),'plateauSha256':digest(folder/'plateau-analysis.json')})
    assert len(phases)==6 and len({p['phase'] for p in phases})==6
    return {'status':'pass','comparisonSha256':digest(root/comparison_file),'specSha256':comparison['specSha256'],'candidateProfileSha256':candidate_pin,'phases':phases,'liveSourcesChecked':live_controller is not None,'hardwareActuation':False,'scope':'Exact saved profile and executable source bytes, analysis linkage and current installed/harness source identity; does not replace live hardware or statistical qualification.'}

def main():
    b=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');e=b/'evidence'
    p=argparse.ArgumentParser();p.add_argument('comparison');a=p.parse_args()
    proof=verify(e,a.comparison,Path('/opt/mmbt/gpu-control'),b)
    proof.update(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceSha256=digest(Path(__file__)))
    path=e/('v2-series-byte-proof-'+a.comparison.replace('-comparison.json','.json'))
    path.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'status':proof['status'],'path':str(path),'phases':len(proof['phases'])}))
if __name__=='__main__':main()
