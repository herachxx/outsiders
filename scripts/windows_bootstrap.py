"""Windows one-click bootstrap; stdlib only until dependencies are available.

The batch file is intentionally ASCII/CRLF and delegates all branches to Python.
No CLI configuration, external AI installation, or undocumented environment flags.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import venv
import tomllib

ROOT = Path(__file__).resolve().parent.parent


def _venv_python(root: Path) -> Path:
    return root / '.venv' / 'Scripts' / 'python.exe'


def bootstrap(root: Path = ROOT, *, run: bool = True) -> int:
    """Prepare dependencies, then launch; return subprocess exit code."""
    if sys.version_info < (3, 12):
        print('Python 3.12+ is required. https://www.python.org/downloads/windows/', flush=True)
        return 2
    py = _venv_python(root) if os.name == 'nt' else root / '.venv' / 'bin' / 'python'
    if not py.is_file():
        print('[1/2] Creating local Python environment (first run)...', flush=True)
        try:
            venv.EnvBuilder(with_pip=True).create(root / '.venv')
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f'Cannot create Python environment: {exc}', flush=True)
            return 1
    if not py.is_file():
        print(f'Python environment was not created: {py}', flush=True)
        return 1
    from scripts.bootstrap_check import needs_ml
    # Probe the newly-created virtual environment, never the system interpreter.
    # This fixes the first-run failure when system Python already had dependencies.
    probe = subprocess.call([str(py), '-m', 'scripts.bootstrap_check'], cwd=root,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if probe:
        print('[1/2] Installing required packages (internet needed once)...', flush=True)
        metadata = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
        dependencies = list(metadata['project']['dependencies'])
        if needs_ml(root):
            dependencies.extend(metadata['project']['optional-dependencies']['ml'])
        # Install runtime dependencies directly; don't require an editable build,
        # isolated setuptools download or wheel build of the app itself.
        cmd = [str(py), '-m', 'pip', 'install', '--disable-pip-version-check',
               '--retries', '2', '--timeout', '12', *dependencies]
        try:
            code = subprocess.call(cmd, cwd=root)
        except OSError as exc:
            print(f'Cannot run pip: {exc}', flush=True)
            return 1
        if code:
            print('Installation failed. Please check internet access and retry START_WINDOWS.bat.', flush=True)
            return code
        # The runtime's own import probe is the authoritative check.
        probe = subprocess.call([str(py), '-m', 'scripts.bootstrap_check'], cwd=root)
        if probe:
            print('Some dependencies are missing or incompatible. See the lines above.', flush=True)
            return probe
    if not run:
        return 0
    print('[2/2] Starting Grand Mobile Support...', flush=True)
    os.environ['GRAND_OPEN_BROWSER'] = '1'
    try:
        return subprocess.call([str(py), '-m', 'scripts.launch'], cwd=root)
    except (OSError, KeyboardInterrupt) as exc:
        if isinstance(exc, KeyboardInterrupt):
            return 0
        print(f'Cannot start: {exc}', flush=True)
        return 1


def main() -> int:
    try:
        return bootstrap()
    except Exception as exc:
        print(f'Startup failed: {type(exc).__name__}: {exc}', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
