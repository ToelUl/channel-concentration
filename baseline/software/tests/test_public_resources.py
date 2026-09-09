"""Public distribution must work without manuscript/artwork or full archives."""
import json
from pathlib import Path
import shutil
import zipfile
import pytest
import cc_repro
import cc_repro.resources as resources
from test_campaign import invoke


def test_public_resource_inventory_excludes_held_content(tmp_path):
    root = Path(cc_repro.__file__).parent
    blocked = {'.tex', '.bbl', '.bib', '.pdf', '.png', '.jpg', '.zip', '.gz'}
    paths = [p for p in (root / '_resources').rglob('*') if p.is_file()]
    assert paths and all(p.suffix.lower() not in blocked for p in paths)
    assert not any('manuscript_baseline' in p.parts for p in paths)
    assert not list((root / '_data').glob('*.zip'))
    project, vault = resources.prepare_workspace(tmp_path / 'work')
    assert not (project / 'paper').exists()
    assert not (project / 'supplement_numerical').exists()
    assert not (project / 'figures').exists()
    with zipfile.ZipFile(vault) as z:
        assert set(z.namelist()) == {r['path'] for r in resources.manifest()['historical']}
        assert all(Path(n).suffix.lower() not in blocked for n in z.namelist())


def test_registry_check_without_manuscript(tmp_path):
    workspace = tmp_path / 'work'
    invoke(workspace, 'figures', '--run-id', 'map')
    result = json.loads((workspace / 'project/build/runs/map/result.json').read_text())
    assert result['status'] == 'PASS'
    assert len(result['figures']) == 7
    assert not result['manuscript_mapping_checked'] and not result['figures_rendered']
    assert result['figures'][3]['output_stem'] == 'fig6_interacting_benchmarks'


@pytest.mark.parametrize('fault', ['extra_archive', 'missing_input', 'modified_input'])
def test_packaged_resource_faults_refused(tmp_path, monkeypatch, fault):
    installed = Path(cc_repro.__file__).parent
    local = tmp_path / 'package'
    for name in ['_resources', '_data']:
        shutil.copytree(installed / name, local / name)
    dependency = local / '_resources/original/repro/config/nnn_tfim_expensive_reproduction.json'
    if fault == 'extra_archive':
        (local / '_resources/original/private.zip').write_bytes(b'not a public dependency')
    elif fault == 'missing_input':
        dependency.unlink()
    else:
        dependency.write_bytes(dependency.read_bytes() + b' ')
    monkeypatch.setattr(resources, 'files', lambda package: local)
    with pytest.raises(ValueError, match='resource (inventory|hash) mismatch'):
        resources.prepare_workspace(tmp_path / 'work')
    assert not (tmp_path / 'work').exists()


def test_old_profile_not_silently_rebound(tmp_path):
    workspace = tmp_path / 'work'
    resources.prepare_workspace(workspace)
    p = workspace / 'binding.json'
    data = json.loads(p.read_text()); data['schema'] = 'cc-original-resources/1.0'
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='binding does not match'):
        resources.prepare_workspace(workspace)
