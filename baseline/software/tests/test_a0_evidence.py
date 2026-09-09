import copy
import json
from pathlib import Path
import pytest
from cc_repro import evidence, ladder
from cc_repro.resources import prepare_workspace
from cc_repro.postprocess import historical_evidence


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    project,vault=prepare_workspace(tmp_path_factory.mktemp("a0")/"workspace")
    history,_=historical_evidence(project.parent,vault)
    identity=evidence.context(project,ladder.config())
    payloads=[]
    for L,name in [(12,"06_L12_receipt.json"),(13,"08_L13_receipt.json"),(14,"10_L14_receipt.json")]:
        p=evidence.read(history/"repro/evidence/potts_tail_calibration"/name)
        # Explicit reference fixture: the validator has a role argument for tests,
        # while production accepted() always requires current.
        p.update(source_role="fixture",identity=identity,predecessor=None,status="PASS",outcome=p["outcome"]["final_adjudication"])
        payloads.append(p)
    return project,identity,payloads


def test_reference_fixture_original_ladder_math(setup):
    project,identity,payloads=setup
    for p in payloads:
        ladder.validate_payload(project,p,identity,None,role="fixture")


@pytest.mark.parametrize("fault",["role","ground","rung","raw_hash","guard","nested","predecessor","context","width"])
def test_ladder_rejects_bad_evidence(setup,fault):
    project,identity,payloads=setup;p=copy.deepcopy(payloads[0])
    if fault=="role":p["source_role"]="reference"
    elif fault=="ground":p["ground_and_P2"].pop("y_error_bound")
    elif fault=="rung":p["rungs"].pop("192")
    elif fault=="raw_hash":p["rungs"]["128"]["elapsed_seconds"]+=1
    elif fault=="guard":p["rungs"]["128"]["guard_eigenpairs"]=0
    elif fault=="nested":p["rungs"]["128"]["nested_with_previous"]=False
    elif fault=="predecessor":p["predecessor"]={"forged":True}
    elif fault=="context":p["identity"]={}
    elif fault=="width":p["outcome"]["width_pass"]=False
    with pytest.raises((ValueError,KeyError)):
        ladder.validate_payload(project,p,identity,None,role="fixture")


def test_fixture_cannot_enter_current_pipeline(setup,tmp_path):
    project,identity,payloads=setup
    root=tmp_path/"ladder";root.mkdir()
    binding=evidence.commit(root,"L12",payloads[0])
    evidence.write(root/"ladder.json",{"schema":"cc-repro-ladder/1","source_role":"current","identity":identity,"status":"PAUSED","sizes":{"12":binding}})
    with pytest.raises(ValueError,match="requires current"):
        ladder.accepted(project,root,complete=False)


def test_durable_seal_and_tamper_refusal(tmp_path):
    binding=evidence.commit(tmp_path,"test",{"source_role":"fixture","value":1})
    assert evidence.load_commit(tmp_path,binding)["value"]==1
    with pytest.raises(FileExistsError):evidence.commit(tmp_path,"test",{})
    (tmp_path/"test.json").write_text('{"source_role":"fixture","value":2}')
    with pytest.raises(ValueError,match="identity mismatch"):evidence.load_commit(tmp_path,binding)


@pytest.mark.parametrize("text",['{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}'])
def test_strict_json(tmp_path,text):
    p=tmp_path/"bad.json";p.write_text(text)
    with pytest.raises(ValueError):evidence.read(p)


def test_count_only_cannot_replace_task_identity():
    with pytest.raises(ValueError):evidence.verify_keys(["a","a"],["a","b"])


def test_unsafe_artifact_path_rejected(tmp_path):
    with pytest.raises(ValueError,match="unsafe"):
        evidence.verify_file(tmp_path,{"path":"../outside","sha256":"0"*64,"bytes":0})


def test_interrupted_ladder_size_is_not_retried(setup,tmp_path):
    project,identity,_=setup;root=tmp_path/"interrupted";root.mkdir()
    evidence.write(root/"ladder.json",{"schema":"cc-repro-ladder/1","source_role":"current","identity":identity,"status":"RUNNING","sizes":{},"active_size":12})
    with pytest.raises(ValueError,match="uncommitted/interrupted"):
        ladder.run(project,root,resume=True)
