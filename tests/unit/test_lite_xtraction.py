"""Synthetic regressions for the first game's lite Xtraction points (issue #63): XML1's extractionPointLite always
offers Save, XMen2.exe's is team change only, so the prepare stage writes the full extractionPoint instead and V32
rejects any extractionPointLite left in XML1 output."""
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from xml1build.prepare import scripts as P3
from xml1build.validate import Check, Scan, Validator

LITE_DATA = "extractionPointLite('_OWNER_','false','true','true','true','false')"


def _tree(root: Path):
    loose, assets = root / 'loose', root / 'assets'
    files = {
        loose / '_fb_manifest.json': json.dumps({'packages/generated/maps/inv/outpost1.fb': [
            ['scripts/inv/outpost1.py', 'py'], ['maps/inv/outpost1.eng', 'zonexml']]}),
        loose / 'maps/inv/outpost1.eng': '<world>\r\n'
                                         '<entity name="world" zonescript="inv/outpost1" />\r\n'
                                         f'<entity name="invented_beacon" actscript="{LITE_DATA}" />\r\n'
                                         '</world>',
        loose / 'scripts/inv/outpost1.py': 'extractionPointLite("invented_beacon", "true", "false", "false", '
                                           '"false", "true")\r\n'
                                           'extractionPoint("invented_beacon")\r\n',
        assets / 'data/strings.eng': '<strings>\r\n<string id="1" text="Invented" />\r\n</strings>',
    }
    for p, t in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(t.encode('latin-1'))
    plan = {'missions': {'m1': {'act': 1, 'attrs': {}, 'objectives': [{'name': 'o1'}], 'required': []}}}
    return loose, assets, plan


def test_prepare_writes_the_full_point_for_every_lite_call():
    api1, api2 = P3.load_api()
    with tempfile.TemporaryDirectory() as td:
        loose, assets, plan = _tree(Path(td))
        out = Path(td) / 'out'
        lines, rep, counts = P3.Rewriter(loose, assets, plan, api1, api2).write(str(out))
        inline = json.loads((out / 'inline_rewrites.json').read_text(encoding='utf-8'))
        assert inline == {LITE_DATA: "extractionPoint('_OWNER_' )"}       # the entity's actscript form
        z = (out / 'scripts/inv/outpost1.py').read_bytes().decode('latin-1')
        assert 'extractionPointLite' not in z
        assert z.split('\r\n')[:2] == ['extractionPoint("invented_beacon" )', 'extractionPoint("invented_beacon")']
        assert rep['stats']['rule extractionPointLite -> extractionPoint (flags dropped)'] == 2
    assert P3.VERSION >= 2                                                  # cached P3 outputs are rebuilt once


def _validator(folder: Path, files: dict, inline=None, runscripts=None):
    v = Validator.__new__(Validator)
    v.reg = {n: dict(rel=n, owner=owner, source='invented') for n, (owner, _) in files.items()}
    for n, (_, text) in files.items():
        (folder / Path(n).name).write_bytes(text.encode('latin-1'))
    v.idx = SimpleNamespace(get=lambda n: n if n in files else None,
                            path=lambda n: folder / Path(n).name if n in files else None)
    sc = Scan()
    sc.inline, sc.runscripts = dict(inline or {}), dict(runscripts or {})
    for n in list(sc.inline) + list(sc.runscripts):
        sc.files[n] = {'rel': n}
        v.reg.setdefault(n, dict(rel=n, owner='zones', source='invented'))
    v._scan = sc
    check = Check('V32', 'lite xtraction')
    v.lite_xtraction(check)
    return check


def test_v32_rejects_lite_calls_in_xml1_scripts_and_data_only():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        good = _validator(folder, {
            'scripts/inv/outpost1.py': ('scripts', 'extractionPoint("invented_beacon" )\r\n'
                                                   '# extractionPointLite("commented", "true", "false", "false" )\r\n'),
            'scripts/base/xml2_own.py': ('base', 'extractionPointLite("kept", "true", "false", "false" )\r\n')},
            inline={'maps/inv/outpost1.engb': [('entity', 'actscript', "extractionPoint('_OWNER_' )")]})
        assert not good.errors
        assert good.counts['lite_xtraction_scripts_checked'] == 1          # the XML2 base script is not ours
        assert good.counts['lite_xtraction_data_code_checked'] == 1
        bad = _validator(folder, {
            'scripts/inv/outpost1.py': ('scripts', 'wait(1)\r\nextractionPointLite("x", "true", "false", "false" )\r\n')},
            inline={'maps/inv/outpost1.engb': [('entity', 'actscript', LITE_DATA)]},
            runscripts={'dialogs/inv/menu.engb': ["extractionpointlite('_OWNER_', 'false', 'false', 'false' )"]})
        assert len(bad.errors) == 3, bad.errors
        assert 'outpost1.py:2' in bad.errors[0] and 'outpost1.engb' in bad.errors[1] + bad.errors[2]
