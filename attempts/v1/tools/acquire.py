"""Download only public sources. Never accepts a student worksheet."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://catalog.charlotte.edu/mime/media/view/10/5658/2026-2027-Undergraduate-Catalog.pdf'

def download(url, target):
    request=urllib.request.Request(url,headers={'User-Agent':'ClassWizard academic exploration'})
    with urllib.request.urlopen(request,timeout=120) as source:
        target.write_bytes(source.read())

def run(local=None):
    raw=ROOT/'data/raw';raw.mkdir(exist_ok=True)
    pdf=Path(local) if local else raw/'catalog-public.pdf'
    if not local: download(URL,pdf)
    subprocess.run(['pdftotext','-raw',str(pdf),str(raw/'catalog-raw.txt')],check=True)
    subprocess.run(['pdftotext','-layout',str(pdf),str(raw/'catalog-2026-2027.txt')],check=True)
    (raw/'catalog-acquisition.json').write_text(json.dumps({'url':URL,'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'bytes':pdf.stat().st_size},indent=2))
    for table, filename in [('occupation_data','occupation_data'),('transferable_skills','transferable_skills'),('essential_skills','essential_skills'),('knowledge','knowledge'),('software_skills','software_skills'),('education','education_training_experience')]:
        download(f'https://www.onetcenter.org/dl_files/database/db_31_0_csv/{table}.csv',raw/f'{filename}.csv')
    print('Public sources acquired. Run prepare.py and review profile.json before activation.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--catalog');args=parser.parse_args();run(args.catalog)
