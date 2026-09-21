"""Exercise refusal paths in the public wrapper without changing the baseline."""
import copy,importlib.util,json,shutil,tempfile,unittest,hashlib
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
        figure_map=json.loads((SOURCE/'FIGURE_MAP.json').read_text())
        code_paths={route['path'] for figure in figure_map['figures'] for route in figure['code_routes']}
        artifact_paths={artifact for figure in figure_map['figures'] for route in figure['code_routes']
                        for artifact in route.get('artifacts',[])}
        for path in code_paths|artifact_paths:
            source=SOURCE.parent/path
            target=self.repo/path
            if target.exists():continue
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target)
        run.HERE,run.REPO=self.here,self.repo

    def test_pristine_copy(self):
        self.assertEqual(run.verify()['baseline_inputs'],42)

    def test_describe_aliases_bind_to_same_figure(self):
        for identifier in ('1','tfim_critical_concentration','fig:twothirds'):
            locator=run.describe(identifier)
            self.assertEqual(locator['selector'],'1')
            self.assertEqual(locator['computation_class'],'analytic-closed-form')
            self.assertIn('soft-ladder',locator['caption_role'])
            self.assertEqual(locator['figure_guide'],'docs/FIGURE_GUIDE.md#figure-1')
            self.assertEqual(locator['code_routes'][-1]['symbol'],'plot_fig1_tfim_critical_concentration')

    def test_every_figure_has_complete_code_route_layers(self):
        figure_map=json.loads((self.here/'FIGURE_MAP.json').read_text())
        for figure in figure_map['figures']:
            stages={route['stage'] for route in figure['code_routes']}
            self.assertIn('scientific-computation',stages)
            self.assertIn('publication-renderer',stages)
            self.assertTrue(stages.intersection({'data-transformation','archived-input','evidence-projection'}))

    def test_final_source_mapping_identities(self):
        figure_map=json.loads((self.here/'FIGURE_MAP.json').read_text())
        self.assertEqual(figure_map['source_validation'],'FINAL_LOCAL_20260921_HASH_AND_LABEL_MAPPING')
        self.assertEqual(
            {row['path']:row['sha256'] for row in figure_map['source_documents']},
            {
                'paper/main.tex':'5a14758e61e267d4f406fe5c40c8a5caca90adc6f8506dd756abc947a13f9d05',
                'supplement_numerical/main.tex':'1f9d9c32a8b1576e68def871814f9b38288af9e8c096e8854cda596bcc2bd745',
                'supplement_numerical/weak_quench_module.tex':'0826ad66245c92b3f2b168ac2a42496ca21a7e895527ecaacad5d20b7f1788b9',
            },
        )
        self.assertTrue(all(figure['caption_role'].strip() for figure in figure_map['figures']))

    def test_missing_code_route_path_is_refused(self):
        path=self.here/'FIGURE_MAP.json';obj=json.loads(path.read_text())
        obj['figures'][0]['code_routes'][0]['path']='companion/missing.py'
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,'code route path'):
            run.verify()

    def test_missing_code_route_symbol_is_refused(self):
        path=self.here/'FIGURE_MAP.json';obj=json.loads(path.read_text())
        obj['figures'][0]['code_routes'][0]['symbol']='not_a_real_symbol'
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,'code route symbol'):
            run.verify()

    def test_interacting_input_without_route_is_refused(self):
        path=self.here/'FIGURE_MAP.json';obj=json.loads(path.read_text())
        for route in obj['figures'][3]['code_routes']:
            route['artifacts']=[artifact for artifact in route.get('artifacts',[])
                                if not artifact.endswith('interacting_benchmarks.csv')]
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,'lacks a producer or postprocessor route'):
            run.verify()

    def test_invalid_figure_is_refused(self):
        with self.assertRaisesRegex(ValueError,'Unknown or ambiguous figure'):
            run.resolve_figure('7')

    def test_changed_computation_class_is_refused(self):
        path=self.here/'FIGURE_MAP.json'
        obj=json.loads(path.read_text())
        obj['figures'][0]['computation_class']='archived-interacting-hybrid'
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,'computation class'):
            run.verify()

    def test_other_figure_metadata_is_hash_bound_for_describe(self):
        path=self.here/'FIGURE_MAP.json'
        obj=json.loads(path.read_text())
        obj['figures'][0]['title']='misleading title'
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,'Figure map identity'):
            run.describe('1')

    def test_legacy_filename_number_is_refused(self):
        p=self.here/'FIGURE_MAP.json'; value=json.loads(p.read_text())
        value['figures'][3]['output_stem']='fig6_interacting_benchmarks'
        p.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'number and output filename disagree'):
            run.verify()

    def test_renderer_filename_mismatch_is_refused(self):
        p=self.here/'FIGURE_MAP.json'; value=json.loads(p.read_text())
        value['figures'][4]['renderer']='plot_figS1_distribution_comparisons'
        p.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'renderer and output filename disagree'):
            run.verify()

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

    def test_changed_artwork_identity_record_is_refused(self):
        p=self.here/'ARTWORK.json'
        p.write_bytes(p.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'artwork identity record'):
            run.verify()

    def test_unapproved_pdf_is_refused(self):
        out=self.repo/'generated';out.mkdir()
        expected=json.loads((self.here/'ARTWORK.json').read_text())['figures']
        for row in expected:(out/row['pdf']).write_bytes(b'not the approved PDF')
        with self.assertRaisesRegex(ValueError,'differs from approved'):
            run.verify_artwork(out)

    def test_missing_or_extra_pdf_is_refused(self):
        out=self.repo/'generated';out.mkdir()
        with self.assertRaisesRegex(ValueError,'inventory differs'):
            run.verify_artwork(out)
        expected=json.loads((self.here/'ARTWORK.json').read_text())['figures']
        for row in expected:(out/row['pdf']).write_bytes(b'placeholder')
        (out/'unexpected.pdf').write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError,'inventory differs'):
            run.verify_artwork(out)


class HostedS1CoordinateTests(unittest.TestCase):
    def setUp(self):
        self.reference=json.loads((SOURCE/'reference/S1-approved-plot-data.json').read_text())
        self.observed=copy.deepcopy(self.reference)

    def test_exact_and_observed_scale_roundoff_pass(self):
        self.assertEqual(run.compare_s1_plot_data(self.reference,self.observed)['y_values'],450)
        self.observed[0]['lines'][0]['y'][0] *= 1+6e-12
        self.assertEqual(run.compare_s1_plot_data(self.reference,self.observed)['different_y_values'],1)

    def test_changed_x_is_refused_even_within_y_tolerance(self):
        self.observed[0]['lines'][0]['x'][0] += 1e-12
        with self.assertRaisesRegex(ValueError,'non-y value differs'):
            run.compare_s1_plot_data(self.reference,self.observed)

    def test_meaningful_y_change_is_refused(self):
        self.observed[0]['lines'][0]['y'][0] *= 1+1e-9
        with self.assertRaisesRegex(ValueError,'exceeds portability tolerance'):
            run.compare_s1_plot_data(self.reference,self.observed)

    def test_changed_label_or_point_count_is_refused(self):
        self.observed[0]['lines'][0]['label']='wrong curve'
        with self.assertRaisesRegex(ValueError,'plot-data value differs'):
            run.compare_s1_plot_data(self.reference,self.observed)
        self.observed=copy.deepcopy(self.reference)
        self.observed[0]['lines'][0]['y'].pop()
        with self.assertRaisesRegex(ValueError,'plot-data length differs'):
            run.compare_s1_plot_data(self.reference,self.observed)

    def test_nonfinite_y_is_refused(self):
        self.observed[0]['lines'][0]['y'][0]=float('nan')
        with self.assertRaisesRegex(ValueError,'numeric type or finiteness'):
            run.compare_s1_plot_data(self.reference,self.observed)

if __name__=='__main__':unittest.main()
