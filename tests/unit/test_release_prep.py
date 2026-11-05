"""Release identity rejects output until its measured fingerprint matches history."""
import tempfile
from pathlib import Path
from unittest.mock import patch

from lcsave import lcfiles
from xml1build import release_identity as RI


def test_unbound_or_different_release_fingerprint_cannot_produce_a_manifest():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        catalogue = out / 'Data/lcsave/catalogue.lcc'
        catalogue.parent.mkdir(parents=True)
        catalogue.write_bytes(b'synthetic catalogue: decoder replaced below')
        synthetic_fingerprint = 'f' * 64
        assert RI.HISTORY[-1].bind_manifest != synthetic_fingerprint
        with patch.object(lcfiles, 'read_catalogue_lcc', return_value={'content_version': RI.HISTORY[-1].content_version, 'revision': RI.HISTORY[-1].catalogue_revision}), \
             patch.object(lcfiles, 'content_fingerprint', return_value=synthetic_fingerprint):
            try:
                RI.manifest(out)
            except ValueError as exc:
                assert 'immutable history' in str(exc)
            else:
                raise AssertionError('unbound or different content fingerprint produced a release manifest')


def test_one_release_switch_reaches_guard_defaults_and_preserves_explicit_off():
    """Simulate the one-line release flip in a fresh interpreter, without editing the checkout."""
    import subprocess
    import sys
    code = r"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
import xml1builder
xml1builder.DEFAULT_GUARD_DECIDE = 'xml1'
import build_xml1
from xml1builder.cli import make_parser
from xml1builder.commands import Job
from xml1builder.pipeline import RealPipeline
from xml1build import fix_ini as FI
assert make_parser().parse_args(['build']).guard_decide == 'xml1'
assert build_xml1.parse_args(['--out', 'x']).guard_decide == 'xml1'
job = Job(out=Path('out'), xml2=Path('xml2'), cache=Path('cache'), iso=None,
          movies=True, jobs=1, prepare_jobs=1)
assert job.guard_decide == 'xml1'
assert RealPipeline().build_args(job).guard_decide == 'xml1'
fields = vars(job).copy()
fields.pop('guard_decide')
assert RealPipeline().build_args(SimpleNamespace(**fields)).guard_decide == 'xml1'
assert make_parser().parse_args(['build', '--guard-decide', 'off']).guard_decide == 'off'
assert build_xml1.parse_args(['--out', 'x', '--guard-decide', 'off']).guard_decide == 'off'
job.guard_decide = 'off'
assert RealPipeline().build_args(job).guard_decide == 'off'
assert FI.GUARD_DECIDE == {'GuardDecideRule': 'xml1'}
"""
    result = subprocess.run([sys.executable, '-B', '-c', code, str(Path(__file__).resolve().parents[2] / 'tools')],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
