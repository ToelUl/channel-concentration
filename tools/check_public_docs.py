"""Check active public Markdown links and English-only documentation paths."""
from pathlib import Path
import re
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parents[1]
files=[*ROOT.glob('*.md'),*ROOT.glob('*.cff')]
for name in ['docs','companion','r3_support','.github']:
    files.extend(p for p in (ROOT/name).rglob('*') if p.suffix in {'.md','.cff','.yml','.yaml'})
errors=[]
for path in files:
    text=path.read_text(encoding='utf-8')
    if re.search(r'[\u3400-\u9fff]',text):errors.append(f'{path.relative_to(ROOT)}: non-English text')
    for target in re.findall(r'\]\(([^)]+)\)',text):
        target=unquote(target.split('#',1)[0])
        if target.startswith('https://github.com/ToelUl/channel-concentration/blob/'):
            target=target.split('/blob/',1)[1].split('/',1)[1]
            resolved=ROOT/target
        elif not target or re.match(r'\w+://',target) or target.startswith('mailto:'):
            continue
        else:resolved=path.parent/target
        if not resolved.exists():errors.append(f'{path.relative_to(ROOT)}: missing link {target}')
    if re.search(r'(?:[CD]:[\\/]Users[\\/]|/home/\w+/|/mnt/[a-z]/phd_research)',text):
        errors.append(f'{path.relative_to(ROOT)}: private machine path')
if errors:raise SystemExit('\n'.join(errors))
print(f'PASS: {len(files)} active public documentation files; frozen historical baseline excluded')
