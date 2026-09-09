"""Check rendered interacting-model coordinates against the archived tables."""
import csv,json

def verify_artists(plot_dir,data):
    import numpy as np
    def read(p): return json.loads(p.read_text(encoding='utf-8'))
    def rows(p):
        with p.open(newline='',encoding='utf-8') as f: return list(csv.DictReader(f))
    checks=[]
    def check(name,a,b):
        aa,bb=np.asarray(a,dtype=float),np.asarray(b,dtype=float)
        checks.append({'check':name,'count':int(aa.size),'passed':aa.shape==bb.shape and bool(np.array_equal(aa,bb))})
    f4=read(plot_dir/'4.json')
    fss=sorted([r for r in rows(data/'potts_outcome_aware_fss.csv') if r['primary_fit']=='True'],key=lambda r:int(r['L']))
    exponent=float(read(data/'potts_theory_guided_7over5_receipt.json')['theory_contract']['relative_analytic_background_correction'])
    check('Fig4 Potts all9 coordinates',list(zip(f4[0]['lines'][0]['x'],f4[0]['lines'][0]['y'])),[(int(r['L'])**(-exponent),float(r['midpoint'])) for r in fss])
    bench=rows(data/'interacting_benchmarks.csv')
    for j in [.05,.1,.2]:
        line=next(l for l in f4[1]['lines'] if l['label']==f'$J_2={j:g}$')
        rr=sorted([r for r in bench if r['model']=='NNN-TFIM' and float(r['lambda_or_g'])==j],key=lambda r:int(r['L']))
        check(f'Fig4 NNN J2={j} all8 coordinates',list(zip(line['x'],line['y'])),[(1/int(r['L']),float(r['KF'])) for r in rr])
    f5=read(plot_dir/'5.json')
    potts=sorted([r for r in rows(data/'potts_L14_certified_ranked_weights.csv') if r['displayed_in_fig7']=='True'],key=lambda r:int(r['channel_rank']))
    check('Fig5 Potts all15 bars',[r['height'] for r in f5[0]['bars'][:15]],[float(r['weight_central']) for r in potts])
    check('Fig5 Potts inset all14 bars',[r['height'] for r in f5[1]['bars'][:14]],[float(r['weight_central']) for r in potts[1:]])
    ranks=rows(data/'nnn_ranked_distribution_convergence.csv')
    for i,L in enumerate([6,10,14,20]):
        rr={int(r['rank']):float(r['pi']) for r in ranks if r['model']=='NNN-TFIM' and float(r['J2'])==.2 and int(r['L'])==L}
        expected=[rr.get(n,0) for n in range(1,11)]
        check(f'Fig5 NNN L{L} all10 bars',[r['height'] for r in f5[2]['bars'][i*10:(i+1)*10]],expected)
        check(f'Fig5 NNN L{L} inset all9 bars',[r['height'] for r in f5[3]['bars'][i*9:(i+1)*9]],expected[1:])
    exact=sorted([r for r in ranks if r['model']=='exact-TFIM' and int(r['L'])==20],key=lambda r:int(r['rank']))
    check('Fig5 exact TFIM all10 line points',f5[2]['lines'][0]['y'],[float(r['pi']) for r in exact])
    check('Fig5 exact TFIM inset all9 line points',f5[3]['lines'][0]['y'],[float(r['pi']) for r in exact[1:]])
    if not all(c['passed'] for c in checks):
        raise ValueError('Rendered coordinates differ from archived inputs: '+json.dumps(checks))
    return {'status':'PASS','checks':checks,'scope':'Archived data-coordinate binding, not spectral completeness or artwork approval.'}
