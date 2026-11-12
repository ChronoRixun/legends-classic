"""SPEC 27.5.2: a save loaded in the Sentinel flashback's first street (nyc/fb/nyc_fb1) must not strand the party.

The zone script plays the intro that spawns the first Sentinel only while s_fb_intro is 0, and the save keeps the var
and the objectives but not the zone's entities (nosave world): after a load there was no Sentinel, the exit stayed
off and "You must finish your objectives" blocked the way (tester report 11-11, reproduced on 0.6.0-beta.6).
Synthetic scripts only: the fix is anchored by the sha1 of the XML1 source, faked here."""
import contextlib
import hashlib
import inspect
import tempfile
from pathlib import Path

from xml1build import reload_fixes as R
from xml1build.prepare import scripts as P3

GATE = ['# header', 'flag = getMissionVar("intro" )', 'if flag == 0', '     startConversation("a/b/c" )',
        '     setMissionVar("intro", 1 )', 'endif']


@contextlib.contextmanager
def fake(lines=GATE):
    """the real fix, anchored to a synthetic source"""
    saved = R.FIXES['nyc/fb/nyc_fb1']
    R.FIXES['nyc/fb/nyc_fb1'] = (hashlib.sha1('\n'.join(lines).encode('latin-1')).hexdigest(), saved[1])
    try:
        yield ('\r\n'.join(lines) + '\r\n\r\n').encode('latin-1')
    finally:
        R.FIXES['nyc/fb/nyc_fb1'] = saved


def test_the_reload_case_redoes_the_first_sentinel_or_replays_the_intro():
    with fake() as src:
        out = R.apply('nyc/fb/nyc_fb1', src).decode('latin-1').split('\r\n')
    assert out[:5] == GATE[:5] and out[5] == 'else'          # the first visit is unchanged
    body = '\n'.join(out)
    assert 'getObjective("sentinel1", "COMPLETE" )' in body
    assert 'setEnable("zone_link01", "TRUE" )' in body and 'setEnable("trigger_touch02", "FALSE" )' in body
    assert body.count('startConversation("nyc/fb/1_4_5" )') == 1  # the replayed intro (it spawns the Sentinel)
    assert out[-2:] == ['endif', '']


def test_the_fix_is_idempotent_and_fails_closed():
    with fake() as src:
        once = R.apply('scripts/NYC/fb/nyc_fb1.py', src)
        assert R.apply('nyc/fb/nyc_fb1', once) == once
        try:
            R.apply('nyc/fb/nyc_fb1', src.replace(b'"a/b/c"', b'"a/b/d"'))
        except ValueError:
            pass
        else:
            raise AssertionError('a different source must fail closed')
    assert R.apply('nyc/fb/nyc_fb2', b'anything\r\n') == b'anything\r\n'


def test_the_rewriter_reads_every_script_through_the_reload_fixes():
    p = Path(tempfile.mkdtemp(prefix='reload-fix-')) / 'nyc_fb1.py'
    with fake() as src:
        p.write_bytes(src)
        assert any(ln.raw.strip() == 'else' for ln in P3.parse_script('nyc/fb/nyc_fb1', str(p)).lines)
    body = inspect.getsource(P3.Rewriter)
    assert 'parse_file(' not in body                         # all four passes and the scriptstart inline use it


def test_the_cached_prepare_output_is_rebuilt():
    assert P3.VERSION >= 11
