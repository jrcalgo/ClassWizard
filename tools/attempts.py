"""Filesystem-only attempt preservation: no Git mutations."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
EXCLUDE={'node_modules','dist','__pycache__','.pytest_cache','test-results','playwright-report','.env'}

def manifest(name):
    folder=ROOT/'attempts'/name
    files={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob('*'))
           if p.is_file() and not any(part in EXCLUDE for part in p.relative_to(folder).parts) and p.name!='checksum-manifest.json'}
    (folder/'docs/checksum-manifest.json').write_text(json.dumps(files,indent=2))
    print(f'{name}: {len(files)} files checksummed')

def advance(prior,next_name):
    source=ROOT/'attempts'/prior;dest=ROOT/'attempts'/next_name
    if not (source/'docs/review.md').exists():
        raise SystemExit('Write the predecessor review before creating the next attempt.')
    if dest.exists():
        raise SystemExit('Destination exists; refusing to overwrite an attempt.')
    manifest(prior)
    shutil.copytree(source,dest,ignore=shutil.ignore_patterns(*EXCLUDE))
    compose=dest/'compose.yaml'
    text=compose.read_text().replace('classwizard-'+prior,'classwizard-'+next_name).replace('ATTEMPT: '+prior,'ATTEMPT: '+next_name).replace('808'+prior[-1]+':80','808'+next_name[-1]+':80')
    compose.write_text(text)
    (dest/'docs/predecessor-review.md').write_text((source/'docs/review.md').read_text())
    # Baseline reports remain preserved, but new reports must not masquerade as measurements.
    for p in (dest/'docs').glob('*.json'):
        if p.name not in {'profile-output.json'}:
            p.unlink()
    (dest/'docs/review.md').unlink()
    readme=dest/'README.md';readme.write_text(readme.read_text().replace('V'+prior[-1],'V'+next_name[-1]).replace('attempts/'+prior,'attempts/'+next_name).replace('localhost:808'+prior[-1],'localhost:808'+next_name[-1]))
    playwright=dest/'frontend/playwright.config.ts';playwright.write_text(playwright.read_text().replace('808'+prior[-1],'808'+next_name[-1]))
    print(f'{next_name} created from reviewed {prior}; predecessor remains intact')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['manifest','advance']);parser.add_argument('prior');parser.add_argument('next',nargs='?');args=parser.parse_args()
    manifest(args.prior) if args.action=='manifest' else advance(args.prior,args.next)
