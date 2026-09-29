"""Developer paths for the tools, without hard-coding anyone's folders.

Each value comes from an environment variable first, then from `local_paths.json` at the repo root (untracked -
.gitignore; copy `local_paths.example.json`), then a relative default:
    XML2_DIR     / "xml2_dir"      the X-Men Legends II install the developer tools and self-tests read
    XML2FIX_DLL  / "xml2fix_dll"   the xml2-fix dinput.dll the test harness installs
The builder (xml1-builder) never uses these: it is always given --xml2 explicitly.
"""
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_FILE = REPO_ROOT / 'local_paths.json'


def _local():
    try:
        with open(LOCAL_FILE, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def get(env, key, default):
    return os.environ.get(env) or _local().get(key) or default


def xml2_dir():
    return get('XML2_DIR', 'xml2_dir', 'X-Men Legends II')


def xml2fix_dll(default):
    return get('XML2FIX_DLL', 'xml2fix_dll', default)
