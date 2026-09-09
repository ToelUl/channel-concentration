from pathlib import Path
import importlib.util, shutil, subprocess, json, os, sys

import argparse
parser=argparse.ArgumentParser(description='Compile the frozen manuscript, supplement and preprint; no numerical calculations.')
parser.add_argument('--run-id',required=True)
args=parser.parse_args()
if not args.run_id or any(ch not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for ch in args.run_id):
    parser.error('run-id must contain only letters, digits, hyphens or underscores')
S=Path(__file__).resolve().parents[1]
B=S/'build/runs'/args.run_id
B.mkdir(parents=True,exist_ok=False)
for name in ['paper','supplement_numerical','figures']:
    shutil.copytree(S/name,B/name)
for name in ['revtex4-2.cls','revsymb4-2.sty','aps4-2.rtx','aps10pt4-2.rtx']:
    shutil.copy2(B/'paper'/name,B/'supplement_numerical'/name)
spec=importlib.util.spec_from_file_location('compositor',S/'scripts/packaging/build_arxiv_bundle.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
mod.build_source_tree(B/'combined',figures_input=S/'figures')
env=os.environ.copy();env.update(SOURCE_DATE_EPOCH='1785542400',TZ='UTC',PYTHONDONTWRITEBYTECODE='1')
pdf=['pdflatex','-synctex=1','-interaction=nonstopmode','-halt-on-error','main.tex']
sequence=[('paper',[pdf,['bibtex','main'],pdf,pdf]),('supplement_numerical',[pdf,pdf]),('paper',[pdf,pdf]),('supplement_numerical',[pdf,pdf]),('combined',[pdf,['bibtex','main'],pdf,pdf,pdf])]
steps=[]
for kind,cmds in sequence:
    for cmd in cmds:
        p=subprocess.run(cmd,cwd=B/kind,env=env,capture_output=True,text=True)
        log=B/f'command-{len(steps):02d}.log';log.write_text(p.stdout+p.stderr)
        steps.append(dict(document=kind,command=cmd,returncode=p.returncode,log=str(log)))
        (B/'commands.json').write_text(json.dumps(steps,indent=2))
        print(kind,cmd[0],p.returncode,flush=True)
        if p.returncode: print(p.stdout[-2500:]);sys.exit(p.returncode)
# Verify actual PDF structure and final reference resolution, beyond exit codes.
import re
for kind in ['paper','supplement_numerical','combined']:
    report=subprocess.run(['pdfinfo','main.pdf'],cwd=B/kind,capture_output=True,text=True,check=True)
    match=re.search(r'Pages:\s+(\d+)',report.stdout)
    if not match or int(match.group(1))<1:
        raise RuntimeError(f'{kind}: invalid or empty PDF')
    log=(B/kind/'main.log').read_text(errors='replace')
    if re.search(r'undefined references|Citation .* undefined|Reference .* undefined',log):
        raise RuntimeError(f'{kind}: unresolved references')
print(B)
