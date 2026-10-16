from pathlib import Path
import sys, zipfile
root=Path(__file__).resolve().parent.parent
out=Path(sys.argv[1] if len(sys.argv)>1 else root.parent/'output')
out.mkdir(parents=True,exist_ok=True)
archive=out/'SilentHelp-HQ-Full-Source.zip'
excluded={'node_modules','.git','test-results','playwright-report','dist','__pycache__'}
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(root.rglob('*')):
        if not p.is_file() or any(part in excluded for part in p.relative_to(root).parts):continue
        if p.name.startswith('.env') and not p.name.endswith('.example'):continue
        if p.suffix in {'.log','.tsbuildinfo'}:continue
        z.write(p,Path('SilentHelp-HQ')/p.relative_to(root))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
print(archive)
print(f'{archive.stat().st_size:,} bytes')
