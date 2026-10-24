"""Create a complete GitHub-uploadable archive while excluding private/local files."""
from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import sys

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache',
            '.mypy_cache', '.ruff_cache', 'dist', 'build', 'htmlcov'}


def main() -> None:
    """Package source and small outputs; fail rather than omit oversized outputs."""
    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT.parent / 'cancer-clock-stage-1.zip'
    if target.is_relative_to(ROOT):
        raise ValueError('Save the archive outside the repository')
    files = []
    for path in sorted(ROOT.rglob('*')):
        relative = path.relative_to(ROOT)
        if not path.is_file() or EXCLUDED.intersection(relative.parts):
            continue
        if relative.parts[:2] == ('data', 'raw') or path.suffix in {'.pyc', '.pyo', '.log', '.pem', '.key'}:
            continue
        if path.name in {'.DS_Store', 'Thumbs.db', '.coverage'}:
            continue
        if path.name.startswith('.env') and path.name != '.env.example':
            continue
        if path.stat().st_size >= 25_000_000:
            raise ValueError(f'File too large for web upload: {relative}')
        files.append(path)
    if len(files) > 100:
        raise ValueError(f'Too many files for a single web upload: {len(files)}')
    with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, Path('cancer-clock') / path.relative_to(ROOT))
    with ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Archive integrity check failed')
    print(f'Packaged {len(files)} files; {target.stat().st_size:,} bytes: {target}')


if __name__ == '__main__':
    main()
