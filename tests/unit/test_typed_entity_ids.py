"""The typed entity-id registry tool (tools/xml1build/typed_entity_ids.py over tools/lcsave/typed_registry.py):
invented script trees only (made-up function names and variable names), never game scripts."""
import hashlib
import os
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
if str(TOOLS / 'xml1build') not in sys.path:
    sys.path.insert(0, str(TOOLS / 'xml1build'))

from lcsave import typed_registry as T  # noqa: E402
import typed_entity_ids  # noqa: E402

API = {'getID': {'ret': 'i'}, 'getIDString': {'ret': 's'}, 'getZoneVar': {'ret': 'i'}, 'fadd': {'ret': 'f'}, 'fmul': {'ret': 'f'},
       'getName': {'ret': 's'}}


def _tree(folder, files):
    for rel, text in files.items():
        p = Path(folder) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode('cp1252'))
    return folder


GOOD = {
    'zone_a/trap.py': 'def onHit(me):\n   victim = getID( me )\n   setZoneVar("victim_a", victim )   # a token\n',
    'zone_a/reset.py': 'setZoneVar("victim_a", 0 )\nsetZoneVar("counter_a", 5 )\n',
    'zone_b/door.py': '  who = getIDString( me )\n  setGameVar("door_b", who)\n  label = getName( me )\n  setZoneVar("label_b", label)\n',
    'zone_b/untyped.py': 'x = getZoneVar("counter_a")\nsetZoneVar("counter_a", x)\n',
}


def _expected_fingerprint(folder):
    rows = []
    for dirpath, _, names in os.walk(folder):
        for n in names:
            p = Path(dirpath) / n
            rows.append((p.relative_to(folder).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest()))
    rows.sort(key=lambda r: r[0].lower().split('/'))
    return hashlib.sha256(''.join(f'{a}\0{b}\n' for a, b in rows).encode()).hexdigest()


def test_scan_finds_typed_keys_and_fingerprint():
    with tempfile.TemporaryDirectory() as d:
        _tree(d, GOOD)
        scan = T.scan_scripts(d, API)
        assert [(t['scope'], t['key']) for t in scan['typed_fields']] == [('Game', 'door_b'), ('Zone', 'victim_a')]
        assert scan['problems'] == [] and scan['getID_calls'] == 1
        assert scan['getID_assignments'] == [{'file': 'zone_a/trap.py', 'line': 2, 'local': 'victim', 'return_type': 'i'}]
        assert scan['fingerprint'] == _expected_fingerprint(d)
        # the fingerprint is the round6 line format over the sorted file list; a byte change or a rename changes it
        kinds = {w['value_kind'] for w in scan['writers']['Zone/victim_a']}
        assert kinds == {'world_token', 'zero'}
        text = T.registry_text(scan)
        assert text.startswith('lcsave-typed-entity-ids 1\nfingerprint ') and text.endswith('key\tGame\tdoor_b\nkey\tZone\tvictim_a\n')
        reg = T.load_registry(text.encode())
        assert reg['keys'] == {('Game', 'door_b'), ('Zone', 'victim_a')} and reg['files'] == 4
        assert T.verify_registry(text.encode(), d) == (True, '')
        assert T.verify_registry(reg, d) == (True, '')


def test_path_order_is_lowercased_components():
    # "a-b/x.py" sorts after "a/y.py" by components ('a' < 'a-b') although '-' < '/' as a string; "B/z.py" sorts
    # last by its lower-cased component although 'B' < 'a' as a string (WindowsPath order, the round6 scan's)
    with tempfile.TemporaryDirectory() as d:
        _tree(d, {'a-b/x.py': '# one\n', 'a/x.py': '# two\n', 'a/y.py': '# three\n', 'B/z.py': '# four\n', 'a/n.PY': '# five\n', 'a/no.txt': ''})
        files = [rel for rel, _ in T.script_files(d)]
        assert files == ['a/n.PY', 'a/x.py', 'a/y.py', 'a-b/x.py', 'B/z.py'], files


def test_mixed_writers_and_float_taint_refuse():
    with tempfile.TemporaryDirectory() as d:
        mixed = dict(GOOD, **{'zone_c/other.py': 'setZoneVar("victim_a", 7 )\n'})
        _tree(d, mixed)
        scan = T.scan_scripts(d, API)
        assert any('mixed writers' in p and 'victim_a' in p for p in scan['problems'])
        try:
            T.registry_text(scan); assert False
        except T.RegistryError as e:
            assert 'no registry' in str(e)
    with tempfile.TemporaryDirectory() as d:
        tainted = dict(GOOD, **{'zone_c/math.py': 'v = getID( me )\nw = fadd( v, 1.5 )\nsetZoneVar("w_c", w)\n'})
        _tree(d, tainted)
        scan = T.scan_scripts(d, API)
        assert scan['float_tainted'] == [{'file': 'zone_c/math.py', 'line': 2}]
        assert any('float operator' in p for p in scan['problems'])
    with tempfile.TemporaryDirectory() as d:
        # a comment never counts; a key the engine's name field cannot hold is refused
        _tree(d, dict(GOOD, **{'zone_c/long.py': 'v = getID( me )\n# setZoneVar("victim_a", 9)\nsetZoneVar("averyveryverylongkey", v)\n'}))
        scan = T.scan_scripts(d, API)
        assert any('name field' in p for p in scan['problems'])
        assert all(w['value_kind'] != 'other' for w in scan['writers']['Zone/victim_a'])


def test_verify_detects_changed_tree_and_malformed_files():
    with tempfile.TemporaryDirectory() as d:
        root = _tree(os.path.join(d, 'scripts'), GOOD)
        reg = os.path.join(d, 'reg.txt')
        code, scan, messages = typed_entity_ids.generate(root, reg, api_path=_api_file(d), expect_keys=2)
        assert code == 0 and os.path.isfile(reg), messages
        assert T.verify_registry(reg, root) == (True, '')
        (Path(root) / 'zone_a' / 'trap.py').write_bytes(b'# changed\n')
        ok, reason = T.verify_registry(reg, root)
        assert not ok and 'does not match the scripts tree' in reason
        (Path(root) / 'zone_a' / 'extra.py').write_bytes(b'')
        ok, reason = T.verify_registry(reg, root)
        assert not ok
        ok, reason = T.verify_registry(os.path.join(d, 'missing.txt'), root)
        assert not ok and 'cannot be verified' in reason
        for bad in (b'', b'lcsave-typed-entity-ids 2\n', b'lcsave-typed-entity-ids 1\nfingerprint zz\n',
                    b'lcsave-typed-entity-ids 1\nfingerprint ' + b'0' * 64 + b'\nfiles 1\nkey\tWorld\tx\n',
                    b'lcsave-typed-entity-ids 1\nfingerprint ' + b'0' * 64 + b'\nfiles 1\nkey\tZone\tx\nkey\tZone\tx\n',
                    b'lcsave-typed-entity-ids 1\nfingerprint ' + b'0' * 64 + b'\nkey\tZone\tx\n',
                    b'lcsave-typed-entity-ids 1\r\nfingerprint ' + b'0' * 64 + b'\r\nfiles 1\r\n', b'\xff\xfe'):
            try:
                T.load_registry(bad); assert False, bad
            except T.RegistryError:
                pass
        # the tool's --check and the expectation switches
        assert typed_entity_ids.main(['--check', reg, root]) == 1
        code, _, messages = typed_entity_ids.generate(root, reg, api_path=_api_file(d), expect_fingerprint='0' * 64)
        assert code == 1 and any('is not the expected' in m for m in messages)
        code, _, messages = typed_entity_ids.generate(root, os.path.join(d, 'reg2.txt'), api_path=_api_file(d), expect_keys=3)
        assert code == 1 and not os.path.exists(os.path.join(d, 'reg2.txt'))


def _api_file(d):
    import json
    p = os.path.join(d, 'api.json')
    with open(p, 'w') as f:
        json.dump(API, f)
    return p


def test_tool_refuses_mixed_tree_without_writing():
    with tempfile.TemporaryDirectory() as d:
        root = _tree(os.path.join(d, 'scripts'), dict(GOOD, **{'zone_c/other.py': 'setZoneVar("victim_a", 7 )\n'}))
        out = os.path.join(d, 'out', 'reg.txt')
        code, scan, messages = typed_entity_ids.generate(root, out, api_path=_api_file(d), report_path=os.path.join(d, 'report.json'))
        assert code == 1 and not os.path.exists(out) and any('mixed writers' in m for m in messages)
        assert os.path.isfile(os.path.join(d, 'report.json'))
        assert typed_entity_ids.main([root, out, '--api', _api_file(d)]) == 1 and not os.path.exists(out)
        root2 = _tree(os.path.join(d, 'good'), GOOD)
        assert typed_entity_ids.main([root2, out, '--api', _api_file(d), '--expect-keys', '2']) == 0 and os.path.isfile(out)
        assert typed_entity_ids.main(['--check', out, root2]) == 0


def test_savefiles_registry_for_shipped_tree():
    """SPEC 85 / V50: savefiles.typed_registry_for scans <out>/Scripts (the shipped tree) and refuses an unclassifiable one."""
    from xml1build import savefiles as SF
    with tempfile.TemporaryDirectory() as d:
        _tree(Path(d) / 'Scripts', GOOD)
        code, scan, messages = SF.typed_registry_for(d)
        assert code == 0 and scan is not None, messages
        assert [(t['scope'], t['key']) for t in scan['typed_fields']] == [('Game', 'door_b'), ('Zone', 'victim_a')]
        assert any('typed keys 2' in m for m in messages)
        text = T.registry_text(scan)
        assert T.verify_registry(T.load_registry(text.encode('ascii')), str(Path(d) / 'Scripts'))[0]
        # a tree with a mixed writer (a token key also written from an untyped value) is refused, no registry
        _tree(Path(d) / 'Scripts', {'zone_c/mixed.py': 'n = getZoneVar("counter_a")\nsetZoneVar("victim_a", n)\n'})
        code, scan, messages = SF.typed_registry_for(d)
        assert code == 1 and any('refused' in m for m in messages)
        assert SF.REGISTRY_REL == 'Data/lcsave/typed-entity-ids.txt'


def test_savefiles_registry_reads_api_through_ctx():
    """0.2.1: in a build the script API comes through ctx.research_path, never a path computed from the module's own
    location - the frozen builder bundles research/ under _internal/, and 0.2.0's path pointed beside the exe."""
    import shutil
    from xml1build import savefiles as SF
    from xml1build import typed_entity_ids as TE
    with tempfile.TemporaryDirectory() as d:
        bundle = Path(d) / 'bundle' / 'research'
        (bundle / 'scripts').mkdir(parents=True)
        shutil.copyfile(TE.DEFAULT_API, bundle / 'scripts' / 'xml2_api.json')

        class Ctx:
            def research_path(self, rel):
                return bundle / rel

        out = Path(d) / 'out'
        _tree(out / 'Scripts', GOOD)
        saved = TE.DEFAULT_API
        try:
            TE.DEFAULT_API = Path(d) / 'missing' / 'xml2_api.json'   # the repo path a frozen build does not have
            code, scan, messages = SF.typed_registry_for(str(out), Ctx())
            assert code == 0 and scan is not None, messages
            code, scan, messages = SF.typed_registry_for(str(out))
            assert code == 1 and any('No such file' in m or 'cannot find' in m.lower() for m in messages), messages
        finally:
            TE.DEFAULT_API = saved
