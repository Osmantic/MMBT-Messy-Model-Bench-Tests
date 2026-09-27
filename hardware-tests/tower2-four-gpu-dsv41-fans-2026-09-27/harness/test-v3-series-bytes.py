import hashlib,importlib.util,json,unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent))
from importlib.machinery import SourceFileLoader
contract=SourceFileLoader('contract',str(Path(__file__).with_name('test-v3-pair-contract.py'))).load_module()
bytecheck=SourceFileLoader('bytecheck',str(Path(__file__).with_name('v3-verify-series-bytes.py'))).load_module()

class ByteProofTests(contract.ContractTests):
    # Only byte-proof cases below; do not rerun the unrelated contract methods.
    def setUp(self):
        super().setUp()
        for pair in self.protocol['pairs']:
            for phase in pair.values():
                folder=self.root/phase;(folder/'sources').mkdir();source=folder/'sources/controller.py';source.write_bytes(b'pass\n')
                result=json.loads((folder/'result.json').read_text());result['sources']={'controller.py':hashlib.sha256(source.read_bytes()).hexdigest()};result['profileSha256']=hashlib.sha256((folder/'profile.json').read_bytes()).hexdigest();self.write(phase,'result.json',result)
                analysis=json.loads((folder/'analysis.json').read_text());analysis['analysisSourceSha256']='analysis-pin';self.write(phase,'analysis.json',analysis);self.repin_plateau(phase)
        candidate=json.loads((self.root/'p0-candidate/result.json').read_text())['profileSha256']
        spec_file=self.root/'v2-matched-fixture-spec.json';spec_file.write_text(json.dumps(self.protocol))
        self.comparison_file='v2-matched-fixture-comparison.json';(self.root/self.comparison_file).write_text(json.dumps({'status':'qualified','specSha256':hashlib.sha256(spec_file.read_bytes()).hexdigest(),'candidateProfileSha256':candidate}))
    def test_bytes_valid(self):self.assertEqual(bytecheck.verify(self.root,self.comparison_file)['status'],'pass')
    def test_profile_bytes_tampered(self):
        (self.root/'p1-candidate/profile.json').write_bytes(b'{}')
        with self.assertRaises(AssertionError):bytecheck.verify(self.root,self.comparison_file)
    def test_source_bytes_tampered(self):
        (self.root/'p1-candidate/sources/controller.py').write_bytes(b'raise RuntimeError()\n')
        with self.assertRaises(AssertionError):bytecheck.verify(self.root,self.comparison_file)
    def test_snapshot_symlink_rejected(self):
        source=self.root/'p1-candidate/sources/controller.py';original=source.read_bytes();source.unlink();target=self.root/'alternate.py';target.write_bytes(original)
        try:source.symlink_to(target)
        except OSError:self.skipTest('Symlink creation not permitted on this platform')
        with self.assertRaises(AssertionError):bytecheck.verify(self.root,self.comparison_file)
    def test_analysis_hash_tampered(self):
        self.change('p1-candidate','analysis.json',lambda d:d.update(extra='changed'))
        with self.assertRaises(AssertionError):bytecheck.verify(self.root,self.comparison_file)
    def test_parent_path_rejected(self):
        self.change('p1-candidate','result.json',lambda d:d.update(sources={'../controller.py':'x'}))
        with self.assertRaises(AssertionError):bytecheck.verify(self.root,self.comparison_file)

if __name__=='__main__':
    suite=unittest.TestSuite(ByteProofTests(name) for name in ('test_bytes_valid','test_profile_bytes_tampered','test_source_bytes_tampered','test_snapshot_symlink_rejected','test_analysis_hash_tampered','test_parent_path_rejected'))
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
