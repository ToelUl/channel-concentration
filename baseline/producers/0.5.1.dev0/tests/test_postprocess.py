from pathlib import Path
import json
import os
import subprocess
import sys
import pytest
import cc_repro
from cc_repro.resources import prepare_workspace
from cc_repro.postprocess import historical_evidence


def call(workspace, analysis, source='historical', input_run=None, run_id=None):
    env=os.environ.copy()
    env.update(PYTHONPATH=str(Path(cc_repro.__file__).parent.parent),PYTHONDONTWRITEBYTECODE='1')
    cmd=[sys.executable,'-B','-m','cc_repro','postprocess','--workspace',str(workspace),
         '--run-id',run_id or analysis,'--analysis',analysis,'--source',source]
    if input_run:cmd+=['--input-run',input_run]
    return subprocess.run(cmd,env=env,cwd=workspace.parent,text=True,capture_output=True,timeout=120)


@pytest.mark.parametrize('analysis',['potts-fss','potts-7over5','potts-ranked','nnn-ranked','projector-enclosures'])
def test_original_historical_routes(tmp_path,analysis):
    workspace=tmp_path/'work'
    result=call(workspace,analysis)
    assert result.returncode==0,result.stdout+result.stderr
    receipt=json.loads((workspace/'project/build/runs'/analysis/'postprocess.json').read_text())
    assert receipt['status']=='PASS' and receipt['source']=='historical'
    assert not receipt['model_eigensolves_performed']
    assert all(Path(r['path']).is_file() for r in receipt['outputs'])
    if analysis=='projector-enclosures':
        d=json.loads(Path(receipt['outputs'][0]['path']).read_text())
        assert d['classification']=='CONDITIONAL_NUMERICAL_ENCLOSURE'
        assert not d['spectral_completeness_independently_proved']


def test_evidence_tampering_refused(tmp_path):
    project,vault=prepare_workspace(tmp_path/'work')
    root,_=historical_evidence(project.parent,vault)
    path=root/'repro/evidence/potts_tail_calibration/06_L12_receipt.json'
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError,match='hash mismatch'):
        historical_evidence(project.parent,vault)


def test_current_requires_complete_grid_and_appropriate_contract(tmp_path):
    workspace=tmp_path/'work';project,_=prepare_workspace(workspace)
    partial=project/'build/runs/partial';partial.mkdir(parents=True)
    (partial/'campaign.json').write_text(json.dumps({'status':'PASS','plan':{'model':'potts','sizes':[6,7]}}))
    result=call(workspace,'potts-fss','current','partial')
    assert result.returncode!=0 and 'complete compatible L6-L14' in result.stderr
    assert not (project/'build/runs/potts-fss').exists()
    result=call(workspace,'potts-7over5','current','partial')
    assert result.returncode!=0 and 'historical inputs' in result.stderr
    assert not (project/'build/runs/potts-7over5').exists()
    result=call(workspace,'nnn-ranked','historical','partial')
    assert result.returncode!=0 and 'cannot accept' in result.stderr
