"""Independent CPU fixtures check the prospective comparison's evidence gates."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('pairs', Path(__file__).with_name('v3-compare-pairs.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.protocol = {'referenceProfile': 'fixed85', 'plateauSourceSha256': 'plateau-pin', 'pairs': []}
        for index in range(3):
            pair = {'reference': f'p{index}-ref', 'candidate': f'p{index}-candidate'}
            self.protocol['pairs'].append(pair)
            order = ('candidate', 'reference') if index == 1 else ('reference', 'candidate')
            for rank, role in enumerate(order):
                name = pair[role]
                folder = self.root / name
                folder.mkdir()
                fixed = role == 'reference'
                profile = {'power_limit_w': 275, 'mode': 'fixed', 'fixed_percent': 85} if fixed else {'power_limit_w': 275, 'mode': 'curve', 'testFixture': True}
                result = {
                    'status': 'ok', 'seconds': 1800, 'inputTokens': 8192,
                    'budget': 2048, 'concurrency': 8, 'allowRecoveryFaults': False,
                    'fixtureSha256': name, 'sources': {'controller': 'exact-source'},
                    'runtime': {'verifiedModels': {'data': [{'id': 'deepseek-v4.1-flash', 'created': index * 2 + rank}]}, 'image': 'exact-image'},
                    'bootId': 'one-boot', 'profileSha256': 'ref-pin' if fixed else 'candidate-pin',
                    'utcStart': f'2026-09-27T{index * 2 + rank:02d}:00:00+00:00',
                    'utcEnd': f'2026-09-27T{index * 2 + rank:02d}:31:00+00:00',
                }
                analysis = {
                    'gpu': {f'gpu-{gpu}': {'requestedCapRangeW': [275, 275], 'enforcedCapRangeW': [275, 275]} for gpu in range(4)},
                    'warmDecode600': {'windowDurationSeconds': 600, 'seconds': 390, 'aggregateTokensPerSecond': 800 if fixed else 792},
                    'e2eOutputTokensPerSecond': 550 if fixed else 544.5,
                    'noiseProxy': {'steady600CoverageSeconds': 600, 'steady600RequestedPercent': 85 if fixed else 78},
                    'paging': {}, 'steadyDecode': {},
                }
                self.write(name, 'result.json', result)
                self.write(name, 'profile.json', profile)
                self.write(name, 'analysis.json', analysis)
                self.repin_plateau(name)

    def write(self, phase, file, data):
        (self.root / phase / file).write_text(json.dumps(data), encoding='utf-8')

    def change(self, phase, file, mutate, repin=False):
        data = json.loads((self.root / phase / file).read_text())
        mutate(data)
        self.write(phase, file, data)
        if repin:
            self.repin_plateau(phase)

    def repin_plateau(self, phase):
        digest = hashlib.sha256((self.root / phase / 'analysis.json').read_bytes()).hexdigest()
        self.write(phase, 'plateau-analysis.json', {'status': 'pass', 'reasons': [], 'originalAnalysisSha256': digest, 'analysisSourceSha256': 'plateau-pin'})

    def rejected(self, phase, file, mutation, repin=False):
        self.change(phase, file, mutation, repin)
        with self.assertRaises(AssertionError):
            m.compare(self.root, self.protocol)

    def test_valid_six_runs_qualify(self):
        self.assertEqual(m.compare(self.root, self.protocol)['status'], 'qualified')

    def test_original_analysis_tamper_fails_hash(self):
        self.rejected('p0-candidate', 'analysis.json', lambda a: a.update(e2eOutputTokensPerSecond=1000))

    def test_cycle_failure_rejects_comparison(self):
        self.rejected('p0-candidate', 'plateau-analysis.json', lambda a: a.update(status='not-qualified', reasons=['genuine heating']))

    def test_wrong_plateau_source_rejected(self):
        self.rejected('p0-candidate', 'plateau-analysis.json', lambda a: a.update(analysisSourceSha256='different'))

    def test_mixed_boot_rejected(self):
        self.rejected('p2-candidate', 'result.json', lambda a: a.update(bootId='second-boot'))

    def test_changed_candidate_bytes_rejected(self):
        self.rejected('p2-candidate', 'result.json', lambda a: a.update(profileSha256='different'))

    def test_changed_executable_source_rejected(self):
        self.rejected('p1-candidate', 'result.json', lambda a: a.update(sources={'controller': 'different'}))

    def test_native_model_identity_rejected(self):
        self.rejected('p1-candidate', 'result.json', lambda a: a['runtime']['verifiedModels']['data'][0].update(id='fallback-qwen'))

    def test_reused_fixture_rejected(self):
        self.rejected('p1-candidate', 'result.json', lambda a: a.update(fixtureSha256='p0-candidate'))

    def test_short_run_rejected(self):
        self.rejected('p1-candidate', 'result.json', lambda a: a.update(seconds=1200))

    def test_overlap_rejected(self):
        self.rejected('p0-candidate', 'result.json', lambda a: a.update(utcStart='2026-09-27T00:30:00+00:00'))

    def test_wrong_counterbalance_rejected(self):
        ref = json.loads((self.root / 'p1-ref' / 'result.json').read_text())
        can = json.loads((self.root / 'p1-candidate' / 'result.json').read_text())
        ref['utcStart'], can['utcStart'] = can['utcStart'], ref['utcStart']
        ref['utcEnd'], can['utcEnd'] = can['utcEnd'], ref['utcEnd']
        self.write('p1-ref', 'result.json', ref)
        self.write('p1-candidate', 'result.json', can)
        with self.assertRaises(AssertionError):
            m.compare(self.root, self.protocol)

    def test_changed_cap_rejected(self):
        self.rejected('p0-candidate', 'analysis.json', lambda a: a['gpu']['gpu-0'].update(enforcedCapRangeW=[274, 275]), repin=True)

    def test_insufficient_decode_coverage_rejected(self):
        self.rejected('p0-candidate', 'analysis.json', lambda a: a['warmDecode600'].update(seconds=299), repin=True)

    def test_e2e_loss_rejects_even_when_decode_passes(self):
        for pair in self.protocol['pairs']:
            self.change(pair['candidate'], 'analysis.json', lambda a: a.update(e2eOutputTokensPerSecond=522.5), repin=True)
        comparison = m.compare(self.root, self.protocol)
        self.assertTrue(comparison['metrics']['warmSimultaneousDecode600']['noninferiorityQualified'])
        self.assertFalse(comparison['metrics']['endToEnd']['noninferiorityQualified'])
        self.assertEqual(comparison['status'], 'not-qualified')

    def test_not_quieter_rejects_even_when_both_rates_pass(self):
        for pair in self.protocol['pairs']:
            self.change(pair['candidate'], 'analysis.json', lambda a: a['noiseProxy'].update(steady600RequestedPercent=85), repin=True)
        self.assertEqual(m.compare(self.root, self.protocol)['status'], 'not-qualified')


if __name__ == '__main__':
    unittest.main(verbosity=2)
