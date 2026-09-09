"""Exercise refusal paths in the public wrapper without changing the baseline."""
import importlib.util,json,shutil,tempfile,unittest,hashlib
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('companion_run',SOURCE/'run.py')
run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)

class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo=Path(self.tmp.name)/'repository'
        self.here=self.repo/'companion'
        shutil.copytree(SOURCE,self.here,ignore=shutil.ignore_patterns('__pycache__'))
        paths={r['public_path'] for r in json.loads((SOURCE/'INPUTS.json').read_text())['files']}
        paths.add('baseline/MANIFEST.json')
        for path in paths:
            p=self.repo/path;p.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(SOURCE.parent/path,p)
        run.HERE,run.REPO=self.here,self.repo

    def test_pristine_copy(self):
        self.assertEqual(run.verify()['baseline_inputs'],42)

    def test_changed_baseline_is_refused(self):
        p=self.repo/'baseline/data/figure-inputs/interacting_benchmarks.csv'
        p.write_bytes(p.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'Baseline input identity'):
            run.verify()

    def test_changed_renderer_is_refused(self):
        p=self.here/'scripts/plotting/generate_figures.py'
        p.write_bytes(p.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'Frozen source identity'):
            run.verify()

    def test_projection_semantics_checked_beyond_hash(self):
        p=self.here/'inputs/cft/cft_kf_results.json'
        obj=json.loads(p.read_text());obj['delta_1']['K']=float(obj['delta_1']['K'])
        p.write_text(json.dumps(obj))
        index=self.here/'INPUTS.json';obj=json.loads(index.read_text())
        obj['projection']['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
        index.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,'decimal strings'):
            run.verify()

    def test_input_tree_cannot_be_output(self):
        for p in [self.repo,self.here/'new',self.repo/'baseline/new']:
            with self.assertRaisesRegex(ValueError,'overlaps'):
                run.fresh_output(p)

    def test_existing_output_is_not_reused(self):
        p=self.repo/'build/new';p.mkdir(parents=True)
        with self.assertRaises(FileExistsError):run.fresh_output(p)

if __name__=='__main__':unittest.main()
