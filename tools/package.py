import hashlib
import json
from pathlib import Path
import zipfile


def main():
    project = Path(__file__).resolve().parent.parent
    data_manifest = project / 'rime/znabc_data/manifest.json'
    if not data_manifest.is_file():
        raise SystemExit('先运行 python3 tools/build_data.py')
    version = json.loads(data_manifest.read_text())['project_version']
    distribution = project / 'dist'
    distribution.mkdir(exist_ok=True)
    destination = distribution / f'rime-znabc-{version}.zip'
    prefix = f'rime-znabc-{version}'
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((project / 'rime').rglob('*')):
            if path.is_file():
                archive.write(path, f'{prefix}/{path.relative_to(project).as_posix()}')
        archive.write(project / 'tools/install.py', f'{prefix}/install.py')
        archive.write(project / 'README.md', f'{prefix}/README.md')
        archive.write(project / 'backlog.md', f'{prefix}/backlog.md')
        archive.write(project / 'VERIFICATION.txt', f'{prefix}/VERIFICATION.txt')
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix('.zip.sha256').write_text(f'{digest}  {destination.name}\n')
    print(destination)
    print(f'{destination.stat().st_size:,} bytes; SHA-256 {digest}')


if __name__ == '__main__':
    main()

