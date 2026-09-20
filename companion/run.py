#!/usr/bin/env python3
"""Verify public inputs, render the frozen figure implementation, or build a gallery."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
COMPUTATION_CLASSES = {
    '1': 'analytic-closed-form',
    '2': 'analytic-free-fermion',
    '3': 'analytic-free-fermion',
    '4': 'archived-interacting-hybrid',
    '5': 'archived-interacting-distribution',
    '6': 'analytic-free-fermion',
    'S1': 'analytic-free-fermion-quench',
}
FIGURE_MAP_SHA256 = '271386896c9d0f0f6eb29dc45598e76b1dd98c02746a6cfb39484a94170b36a9'
S1_REFERENCE_SHA256 = '91582fff7e7a5ea88865752e03ed58555752a3066c15eda0e0281dbb93f83051'
S1_PNG_SHA256 = '4e69fd422ee534520e8e1ad4929c446a3ad37e73c85a2c2a19afd69690e5c508'
S1_Y_RTOL = 1e-11

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')

def checked_path(relative):
    candidate = HERE / relative
    resolved = candidate.resolve()
    if not resolved.is_relative_to(REPO) or not candidate.is_file():
        raise ValueError('Missing or unsafe input: '+relative)
    if any(p.is_symlink() for p in [candidate, *candidate.parents] if p != REPO.parent):
        raise ValueError('Symbolic links are not accepted: '+relative)
    return resolved

def verify():
    origin = read(HERE/'ORIGIN.json')
    for row in origin['scripts']:
        if sha(checked_path(row['path'])) != row['sha256']:
            raise ValueError('Frozen source identity mismatch: '+row['path'])
    inputs = read(HERE/'INPUTS.json')
    for row in inputs['files']:
        if sha(checked_path(row['path'])) != row['sha256']:
            raise ValueError('Baseline input identity mismatch: '+row['path'])
    if sha(REPO/'baseline/MANIFEST.json') != inputs['baseline_manifest_sha256']:
        raise ValueError('Baseline manifest identity mismatch')
    row = inputs['projection']
    target, source = checked_path(row['path']), checked_path(row['source'])
    if sha(target) != row['sha256'] or sha(source) != row['source_sha256']:
        raise ValueError('CFT projection/source identity mismatch')
    projected, raw = read(target), read(source)
    for delta, legacy in [('1','delta_1'), ('4/5','delta_4_over_5')]:
        r = raw['delta_results'][delta]
        for a,b in [('s1','S1'), ('s2','S2'), ('k','K')]:
            value = r['beta_integral_hypergeometric_closed_form'][a]
            if not isinstance(value,str) or value != projected[legacy][b]:
                raise ValueError('CFT decimal strings changed')
        if r['routes_agree_1e-20'] is not projected[legacy]['routes_agree_1e-20']:
            raise ValueError('CFT route-agreement flag changed')
    contract = read(HERE/'FIGURE_MAP.json')
    selectors = [row.get('selector') for row in contract['figures']]
    if selectors != list(COMPUTATION_CLASSES):
        raise ValueError('Figure map selector inventory differs from the approved seven figures')
    for row in contract['figures']:
        if row.get('computation_class') != COMPUTATION_CLASSES[row['selector']]:
            raise ValueError('Figure computation class differs from its contract: '+row['selector'])
        if not row['output_stem'].startswith('fig'+row['selector']+'_'):
            raise ValueError('Figure number and output filename disagree: '+row['selector'])
        if row['renderer'] != 'plot_'+row['output_stem']:
            raise ValueError('Figure renderer and output filename disagree: '+row['selector'])
    if sha(HERE/'FIGURE_MAP.json') != FIGURE_MAP_SHA256:
        raise ValueError('Figure map identity differs from the reviewed S3 metadata')
    if contract['renderer_sha256'] != sha(HERE/'scripts/plotting/generate_figures.py'):
        raise ValueError('Figure map is bound to a different renderer')
    artwork = read(HERE/'ARTWORK.json')
    if sha(HERE/'ARTWORK.json') != origin['artwork_identity_sha256']:
        raise ValueError('Approved artwork identity record changed')
    if artwork['renderer_sha256'] != contract['renderer_sha256']:
        raise ValueError('Approved artwork is bound to a different renderer')
    expected = [(r['selector'], r['output_stem']+'.pdf') for r in contract['figures']]
    if [(r['selector'], r['pdf']) for r in artwork['figures']] != expected:
        raise ValueError('Approved artwork inventory differs from figure map')
    return {'status':'PASS', 'baseline_inputs':len(inputs['files']), 'lossless_projections':1,
            'frozen_sources':len(origin['scripts']), 'numerical_baseline':inputs['tag'],
            'scope':'Input identity and decimal-string mapping; no numerical qualification.'}


def verify_artwork(figure_dir):
    verify()
    expected = read(HERE/'ARTWORK.json')['figures']
    names = {r['pdf'] for r in expected}
    observed = {p.name for p in figure_dir.glob('*.pdf')}
    if observed != names:
        raise ValueError('Figure PDF inventory differs from the approved S2 set')
    for row in expected:
        if sha(figure_dir/row['pdf']) != row['pdf_sha256']:
            raise ValueError('Figure PDF differs from approved S2 artwork: '+row['pdf'])
    return {'status':'PASS','figures':len(expected),'artwork_version':read(HERE/'ARTWORK.json')['version'],
            'scope':'Exact output identity with the author-approved S2 figure set; not a new human review or venue approval.'}


def compare_s1_plot_data(reference, observed):
    """Require identical structure and x values; bound only S1 y roundoff."""
    result = {'numeric_values': 0, 'y_values': 0, 'different_y_values': 0,
              'max_relative_y_difference': 0.0}

    def walk(expected, actual, path=(), y_coordinate=False):
        location = '/'.join(map(str, path)) or 'root'
        if isinstance(expected, dict):
            if not isinstance(actual, dict) or expected.keys() != actual.keys():
                raise ValueError('Figure S1 plot-data structure differs at '+location)
            for key in expected:
                walk(expected[key], actual[key], path+(key,), key == 'y' and len(path) >= 2
                     and path[-2] == 'lines')
        elif isinstance(expected, list):
            if not isinstance(actual, list) or len(expected) != len(actual):
                raise ValueError('Figure S1 plot-data length differs at '+location)
            for index, (left, right) in enumerate(zip(expected, actual)):
                walk(left, right, path+(index,), y_coordinate)
        elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
            if type(actual) is not type(expected) or not math.isfinite(expected) or not math.isfinite(actual):
                raise ValueError('Figure S1 plot-data numeric type or finiteness differs at '+location)
            result['numeric_values'] += 1
            if y_coordinate:
                result['y_values'] += 1
                if not math.isclose(expected, actual, rel_tol=S1_Y_RTOL, abs_tol=0.0):
                    raise ValueError('Figure S1 y coordinate exceeds portability tolerance at '+location)
                if expected != actual:
                    result['different_y_values'] += 1
                    result['max_relative_y_difference'] = max(
                        result['max_relative_y_difference'], abs(actual-expected)/max(abs(expected), abs(actual)))
            elif expected != actual:
                raise ValueError('Figure S1 non-y value differs at '+location)
        elif type(actual) is not type(expected) or actual != expected:
            raise ValueError('Figure S1 plot-data value differs at '+location)

    walk(reference, observed)
    if result['numeric_values'] != 900 or result['y_values'] != 450:
        raise ValueError('Figure S1 coordinate count differs from approved S2 reference')
    return result


def verify_hosted_artwork(figure_dir, plot_dir):
    """Check six exact PDFs and the portable S1 contract on a hosted runner."""
    verify()
    artwork = read(HERE/'ARTWORK.json')
    expected = artwork['figures']
    pdf_names = {row['pdf'] for row in expected}
    png_names = {Path(row['pdf']).with_suffix('.png').name for row in expected}
    if {path.name for path in figure_dir.glob('*.pdf')} != pdf_names:
        raise ValueError('Figure PDF inventory differs from the approved S2 set')
    if {path.name for path in figure_dir.glob('*.png')} != png_names:
        raise ValueError('Figure PNG inventory differs from the complete S2 render')
    receipt = read(plot_dir.parent/'render-receipt.json')
    selectors = [row['selector'] for row in expected]
    if (receipt.get('status') != 'PASS' or receipt.get('mode') != 'publication'
            or receipt.get('selected_figures') != selectors
            or [row.get('selector') for row in receipt.get('figures', [])] != selectors
            or receipt.get('input_check', {}).get('status') != 'PASS'
            or receipt.get('artist_check', {}).get('status') != 'PASS'
            or receipt.get('analytic_artist_check', {}).get('status') != 'PASS'):
        raise ValueError('Complete publication render and coordinate-check receipt required')
    for row in receipt['figures']:
        if (row.get('pdf') not in pdf_names or row.get('pdf_sha256') != sha(figure_dir/row['pdf'])
                or row.get('png_sha256') != sha(figure_dir/Path(row['pdf']).with_suffix('.png').name)):
            raise ValueError('Rendered figure differs from its render receipt: '+str(row.get('selector')))
    s1 = next(row for row in expected if row['selector'] == 'S1')
    for row in expected:
        if row['selector'] != 'S1' and sha(figure_dir/row['pdf']) != row['pdf_sha256']:
            raise ValueError('Figure PDF differs from approved S2 artwork: '+row['pdf'])
    s1_pdf = figure_dir/s1['pdf']
    pdf_bytes = s1_pdf.read_bytes()
    if len(pdf_bytes) < 1000 or not pdf_bytes.startswith(b'%PDF-') or b'%%EOF' not in pdf_bytes[-1024:]:
        raise ValueError('Figure S1 PDF is missing or malformed')
    s1_png = figure_dir/Path(s1['pdf']).with_suffix('.png').name
    if sha(s1_png) != S1_PNG_SHA256:
        raise ValueError('Figure S1 PNG differs from the approved-render raster reference')
    reference_path = HERE/'reference/S1-approved-plot-data.json'
    if sha(reference_path) != S1_REFERENCE_SHA256:
        raise ValueError('Figure S1 approved plot-data reference identity changed')
    comparison = compare_s1_plot_data(read(reference_path), read(plot_dir/'S1.json'))
    s1_pdf_hash = sha(s1_pdf)
    exact = s1_pdf_hash == s1['pdf_sha256']
    return {'status':'PASS', 'mode':'EXACT_7_OF_7' if exact else 'PORTABLE_S1_CHECK',
            'exact_pdf_count':7 if exact else 6, 'approved_s1_pdf_sha256':s1['pdf_sha256'],
            'rendered_s1_pdf_sha256':s1_pdf_hash, 's1_png_sha256':S1_PNG_SHA256,
            's1_plot_data':comparison, 'artwork_version':artwork['version'],
            'scope':('Seven freshly rendered PDFs match the author-approved S2 artwork.' if exact else
                     'Six PDFs match approved S2 artwork exactly; S1 coordinates and PNG pass the portable check. '
                     'The newly rendered S1 PDF is not an approved artwork identity.')}

def renderer():
    import numpy, scipy, matplotlib
    versions={'python':'.'.join(map(str,sys.version_info[:3])), 'numpy':numpy.__version__,
              'scipy':scipy.__version__, 'matplotlib':matplotlib.__version__}
    expected=read(HERE/'ENVIRONMENT.json')['versions']
    if versions != expected:
        raise ValueError('Use the pinned plotting environment: '+str(expected)+'; observed '+str(versions))
    spec=importlib.util.spec_from_file_location('companion_renderer',HERE/'scripts/plotting/generate_figures.py')
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    expected_map=read(HERE/'FIGURE_MAP.json')['figures']
    actual=[{'selector':s.selector,'key':s.key,'title':s.title,'renderer':s.renderer.__name__,
             'output_stem':s.output_stem,'tex_label':s.tex_label,'tex_source':s.tex_source,
             'documents':[list(x) for x in s.documents], 'data_inputs':list(s.data_inputs),
             'evidence_inputs':list(s.evidence_inputs)} for s in mod.FIGURE_SPECS]
    expected_identity=[{key:value for key,value in row.items() if key!='computation_class'}
                       for row in expected_map]
    if actual != expected_identity:
        raise ValueError('Frozen figure registry differs from the source-derived map')
    return mod, versions


def resolve_figure(identifier):
    figures=read(HERE/'FIGURE_MAP.json')['figures']
    matches=[row for row in figures if identifier.upper()==row['selector']
             or identifier in (row['key'],row['tex_label'])]
    if len(matches)!=1:
        raise ValueError('Unknown or ambiguous figure: '+identifier)
    return matches[0]


def describe(identifier):
    verify()
    row=resolve_figure(identifier)
    selector=row['selector']
    return {'selector':selector,'key':row['key'],'title':row['title'],
            'computation_class':row['computation_class'],'renderer':row['renderer'],
            'direct_data_inputs':row['data_inputs'],
            'direct_evidence_inputs':row['evidence_inputs'],
            'output_stem':row['output_stem'],
            'figure_guide':'docs/FIGURE_GUIDE.md#figure-'+selector.lower(),
            'reproduce':'python -B companion/run.py render --fig '+selector}

def semantic(fig):
    import numpy as np
    records=[]
    def visit(ax):
        records.append({'lines':[{'label':l.get_label(),'x':np.asarray(l.get_xdata(),dtype=float).tolist(),
            'y':np.asarray(l.get_ydata(),dtype=float).tolist()} for l in ax.lines],
            'bars':[{'height':p.get_height()} for p in ax.patches if hasattr(p,'get_height')]})
        for child in ax.child_axes: visit(child)
    for ax in fig.axes: visit(ax)
    return records

def fresh_output(path):
    path=path.resolve()
    # Generated material must never be written into immutable inputs or source directories.
    for source in [REPO/'baseline', HERE]:
        if path == source or path.is_relative_to(source) or source.is_relative_to(path):
            raise ValueError('Output overlaps an input/source tree')
    path.mkdir(parents=True,exist_ok=False)
    return path

def render(args):
    before=verify()
    selected={resolve_figure(identifier)['selector'] for identifier in (args.fig or [])}
    os.environ.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    mod, versions=renderer()
    selected_specs=[spec for spec in mod.FIGURE_SPECS
                    if not selected or spec.selector in selected]
    out=fresh_output(args.output)
    os.environ.update(MPLBACKEND='Agg', MPLCONFIGDIR=str(out/'matplotlib-cache'),
                      SOURCE_DATE_EPOCH='1785542400', OPENBLAS_NUM_THREADS='1',
                      OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    mod.configure_plotting()
    data=REPO/'baseline/data/figure-inputs'
    evidence=HERE/'inputs'
    mod.validate_selected_inputs(selected_specs,data,evidence)
    records=[]; diagnostics={}
    for s in selected_specs:
        result=s.renderer(mod.PlotContext(s,mod.get_params(args.mode),HERE,data,evidence))
        try:
            write(out/'plot-data'/f'{s.selector}.json',semantic(result.figure))
            mod.save_figure(result.figure,s,out/'figures')
            diagnostics.update(result.diagnostics)
            records.append({'selector':s.selector,'pdf':s.output_stem+'.pdf',
                            'pdf_sha256':sha(out/'figures'/f'{s.output_stem}.pdf'),
                            'png_sha256':sha(out/'figures'/f'{s.output_stem}.png')})
            print('Rendered Figure '+s.selector,flush=True)
        finally:
            mod.plt.close(result.figure)
    from verify_artists import verify_artists
    artist_check=verify_artists(out/'plot-data',data,
                                {spec.selector for spec in selected_specs})
    write(out/'artist-verification.json',artist_check)
    from verify_analytic_artists import verify_analytic_artists
    analytic_check=verify_analytic_artists(out/'plot-data',data,
                                           {spec.selector for spec in selected_specs})
    write(out/'analytic-artist-verification.json',analytic_check)
    after=verify()
    assert before == after
    write(out/'render-receipt.json',{'status':'PASS','mode':args.mode,'versions':versions,
          'figures':records,'selected_figures':[spec.selector for spec in selected_specs],
          'input_check':after,'artist_check':artist_check,
          'analytic_artist_check':analytic_check,'diagnostics':diagnostics,
          'interacting_eigensolves':0,'new_fits':0,'artwork_approval':'NOT_ASSERTED'})
    print('PASS: '+str(len(records))+' figures, '+str(len(artist_check['checks']))+
          ' interacting and '+str(len(analytic_check['checks']))+
          ' analytic coordinate checks')

def gallery(args):
    verify()
    figures=read(HERE/'FIGURE_MAP.json')['figures']
    # Refuse incomplete inputs before creating the document directory.
    for row in figures:
        if not (args.figure_dir/(row['output_stem']+'.pdf')).is_file():
            raise ValueError('Render all seven figures before building the gallery')
    out=fresh_output(args.output)
    lines=[r'\documentclass{article}',r'\usepackage[margin=18mm]{geometry}',r'\usepackage{graphicx}',
           r'\pagestyle{plain}',r'\begin{document}']
    for row in figures:
        name=row['output_stem']+'.pdf'
        shutil.copy2(args.figure_dir/name,out/name)
        lines += [r'\section*{Figure '+row['selector']+'}',
                  r'\noindent Channel Concentration: reproducible figure gallery.\\',
                  r'S2 presentation companion; see ARTWORK.json for approved PDF identities.\par',
                  r'\includegraphics[width=\textwidth,height=0.82\textheight,keepaspectratio]{'+name+'}',
                  r'\clearpage']
    lines += [r'\end{document}']
    (out/'gallery.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    cmd=['pdflatex','-no-shell-escape','-interaction=nonstopmode','-halt-on-error','gallery.tex']
    run=subprocess.run(cmd,cwd=out,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (out/'build.log').write_text(run.stdout+run.stderr,encoding='utf-8')
    if run.returncode or not (out/'gallery.pdf').is_file():
        raise RuntimeError('Gallery compilation failed; inspect build.log')
    write(out/'gallery-receipt.json',{'status':'PASS','figures':7,'pdf_sha256':sha(out/'gallery.pdf'),
          'scope':'Public figure inclusion and minimal LaTeX build only; not a manuscript or arXiv target build.'})
    print('PASS: gallery.pdf')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('verify',help='Verify shared baseline inputs and the CFT projection using the standard library')
    p=sub.add_parser('describe',help='Locate a figure by selector, stable key, or TeX label')
    p.add_argument('figure')
    p=sub.add_parser('verify-artwork',help='Compare rendered PDFs with the exact author-approved S2 figure set')
    p.add_argument('--figure-dir',type=Path,default=REPO/'build/companion/figures')
    p=sub.add_parser('verify-hosted-artwork',help='Check six exact PDFs and the portable S1 contract')
    p.add_argument('--figure-dir',type=Path,default=REPO/'build/companion/figures')
    p.add_argument('--plot-dir',type=Path,default=REPO/'build/companion/plot-data')
    p.add_argument('--receipt',type=Path,help='Write the hosted artwork verification receipt')
    p=sub.add_parser('render',help='Render all or selected figures without an interacting solve or refit')
    p.add_argument('--mode',choices=['fast','publication'],default='publication')
    p.add_argument('--output',type=Path,default=REPO/'build/companion')
    p.add_argument('--fig',nargs='+',metavar='SELECTOR',help='Only render the selected figures')
    p=sub.add_parser('gallery',help='Build a minimal seven-page LaTeX figure gallery')
    p.add_argument('--figure-dir',type=Path,default=REPO/'build/companion/figures')
    p.add_argument('--output',type=Path,default=REPO/'build/gallery')
    args=parser.parse_args()
    try:
        if args.command=='verify': print(json.dumps(verify(),indent=2))
        elif args.command=='describe': print(json.dumps(describe(args.figure),indent=2))
        elif args.command=='verify-artwork': print(json.dumps(verify_artwork(args.figure_dir),indent=2))
        elif args.command=='verify-hosted-artwork':
            result=verify_hosted_artwork(args.figure_dir,args.plot_dir)
            if args.receipt: write(args.receipt,result)
            print(json.dumps(result,indent=2))
        elif args.command=='render': render(args)
        else: gallery(args)
    except (ValueError,FileExistsError,RuntimeError) as error:
        parser.exit(1,str(error)+'\n')

if __name__=='__main__': main()
