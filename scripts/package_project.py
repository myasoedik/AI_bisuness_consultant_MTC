"""Package reviewed source using an allowlist. Exclude case dumps and all secrets."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import hashlib
import json
import re

root=Path(__file__).resolve().parent.parent
files=[root/name for name in ['README.md','Dockerfile','compose.yaml','compose.demo.yaml',
                             '.dockerignore','.gitignore','.env.example','requirements.txt','solution.py']]
for directory,suffixes in [('energytool',{'.py'}),('web',{'.js','.css','.html'}),
                           ('scripts',{'.py'}),('tests',{'.py','.md'}),('docs',{'.md'}),('demo-knowledge-base',{'.md'})]:
    files.extend(p for p in (root/directory).rglob('*') if p.is_file() and p.suffix in suffixes and '__pycache__' not in p.parts)
pdf=root/'output'/'pdf'/'energytool-presentation.pdf'
if not pdf.exists():
    raise SystemExit('Missing presentation PDF. Build it before final packaging.')
files.append(pdf)
target=root/'output'/'energytool-mvp.zip'
manifest=[]
with ZipFile(target,'w',ZIP_DEFLATED) as archive:
    for p in sorted(set(files)):
        data=p.read_bytes()
        if p.suffix!='.pdf' and re.search(rb'(sk-or-v1-[a-fA-F0-9]{32,}|Bearer sk-[A-Za-z0-9_-]{20,})',data):
            raise SystemExit('Potential secret found; packaging aborted.')
        name='docs/presentation.pdf' if p==pdf else p.relative_to(root).as_posix()
        archive.writestr(name,data)
        manifest.append({'path':name,'sha256':hashlib.sha256(data).hexdigest()})
    archive.writestr('MANIFEST.json',json.dumps(manifest,indent=2))
print(f'Packaged {len(files)} files: {target.name}')
