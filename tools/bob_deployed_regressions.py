"""Read-only check of delivered ranking code; no live account, orders or secrets.

Execute reviewed local fixtures only after public script bytes match exactly.
This tests functions, not browser layout or the current user's private inputs.
"""
import hashlib
from pathlib import Path
import subprocess
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent.parent
ASSETS=('degiro_assistant.js','product_evidence_contract.js')
TESTS=('test_early_product_ranking.js','test_unapproved_comparison_ranking.js','test_primary_calculated_product.js')


def read_asset(name):
    if name not in ASSETS:
        raise ValueError('Unlisted public asset')
    request=Request('https://bob-private-scanner.onrender.com/'+name,
                    headers={'Cache-Control':'no-cache','User-Agent':'bob-deployed-regressions'})
    with urlopen(request,timeout=20) as response:
        raw=response.read(4*1024*1024+1)
    if len(raw)>4*1024*1024:
        raise ValueError('Oversized asset')
    return raw


def verify_assets(fetch=read_asset, root=ROOT):
    return all(hashlib.sha256(fetch(name)).digest()==hashlib.sha256((root/name).read_bytes()).digest()
               for name in ASSETS)


def run():
    if not verify_assets():
        raise RuntimeError('Published ranking scripts differ from reviewed checkout')
    for test in TESTS:
        subprocess.run(['node',test],cwd=ROOT,check=True,timeout=45)
    print('Published ranking scripts: LONG/SHORT, early panel and source priority regressions passed. Browser layout and private live inputs not verified.')


if __name__=='__main__':
    run()
