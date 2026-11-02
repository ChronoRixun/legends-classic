"""Beta 9 moves (candidate 082b): the product CLI carries build_xml1's ini-only --telekinesis / --guard-decide /
--flying-carry options to the build; telekinesis and the flying carry on by default since 0.5.0-beta.1, the guard
decide off (Owen 10-28, the 082f real-pad check: Guard stays XML2's Block / Grab, as in beta 8)."""
from pathlib import Path

import build_xml1
from xml1builder.cli import make_parser
from xml1builder.commands import Job
from xml1builder.pipeline import RealPipeline

OPTS = ('telekinesis', 'guard_decide', 'flying_carry')
DEFAULTS = ('xml1', 'off', 'xml1')


def job(**kw):
    return Job(out=Path('out'), xml2=Path('xml2'), cache=Path('cache'), iso=None, movies=True, jobs=1, prepare_jobs=1, **kw)


def test_the_cli_parses_the_three_options_tk_and_carry_on_guard_off():
    plain = make_parser().parse_args(['build'])
    assert tuple(getattr(plain, o) for o in OPTS) == DEFAULTS
    on = make_parser().parse_args(['build', '--guard-decide', 'xml1'])
    assert on.guard_decide == 'xml1'
    off = make_parser().parse_args(['build', '--telekinesis', 'off', '--guard-decide', 'off', '--flying-carry', 'off'])
    assert all(getattr(off, o) == 'off' for o in OPTS)


def test_build_args_pass_them_through_and_a_default_job_is_the_default_build():
    p = RealPipeline()
    plain = p.build_args(job())
    assert tuple(getattr(plain, o) for o in OPTS) == DEFAULTS
    defaults = build_xml1.parse_args(['--out', 'x'])
    assert all(getattr(plain, o) == getattr(defaults, o) for o in OPTS)
    assert plain.grab_carry == 'xml1'                   # build_xml1's own dependency check passes with the default lifecycle
    # the 0.4.2-line options reach build_xml1 explicitly, so an 'off' is never replaced by build_xml1's default
    for opt in ('limits_wave3', 'save_layout', 'loot', 'loot_def_damage_scale'):
        assert getattr(plain, opt) == getattr(defaults, opt), opt
    off = p.build_args(job(telekinesis='off', guard_decide='off', flying_carry='off', limits_wave3='off',
                           save_layout='retail', loot='off'))
    assert all(getattr(off, o) == 'off' for o in OPTS)
    assert (off.limits_wave3, off.save_layout, off.loot, off.loot_def_damage_scale) == ('off', 'retail', 'off', 'noop')
    one = p.build_args(job(telekinesis='off', flying_carry='off'))
    assert (one.telekinesis, one.guard_decide, one.flying_carry) == ('off', 'off', 'off')
    guard = p.build_args(job(guard_decide='xml1'))
    assert (guard.telekinesis, guard.guard_decide, guard.flying_carry) == ('xml1', 'xml1', 'xml1')


def test_the_report_record_carries_them_for_fix_ini():
    # the pipeline's report records every CONTENT_OPTS option from these args; fix_ini.port_keys reads them back
    # CONTENT_OPTS keeps beta 8's value (what a record without the key means); the option defaults are on since 0.5.0
    assert all(o in build_xml1.CONTENT_OPTS and build_xml1.CONTENT_OPTS[o] == ((), 'off') for o in OPTS)


def test_default_build_record_removes_stale_guard_without_disabling_tk_or_carry():
    """082f real-pad refusal: the shipped default must reach the INI writer, including rebuilds."""
    import json
    import tempfile
    from xml1build import fix_ini as FI

    args = RealPipeline().build_args(job())
    record = {key: getattr(args, key, default)
              for key, (_, default) in build_xml1.CONTENT_OPTS.items()}
    # This fixture has metadata only, so choose the supported online-assets-off profile.
    record['online_menus'] = 'off'
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        (out / '_build').mkdir()
        (out / '_build/report.json').write_text(json.dumps({'build': record}), encoding='utf-8')
        # The INI writer requires the LC postgame marker before authorizing the W2 save identity.
        marker = out / 'Scripts' / (FI.POSTGAME_SCRIPT + '.py')
        marker.parent.mkdir(parents=True)
        marker.write_bytes(b'# synthetic port identity marker\n')
        keys = FI.port_keys(out)
        assert keys['Game']['TelekinesisRule'] == 'xml1'
        assert 'GuardDecideRule' not in keys['Game']
        assert 'Xml1FlyingCarry' not in keys['Game']
        merged = FI.merge_text('[Game]\nGuardDecideRule=xml1\nXml1FlyingCarry=0\nKeepMe=7\n',
                               keys, FI.dropped_keys(keys))
        assert 'GuardDecideRule' not in merged and 'Xml1FlyingCarry' not in merged
        assert 'TelekinesisRule=xml1' in merged and 'KeepMe=7' in merged


def test_missing_job_move_fields_keep_release_defaults_and_explicit_off_survives():
    from types import SimpleNamespace
    fields = vars(job()).copy()
    for opt in OPTS:
        fields.pop(opt)
    parsed = RealPipeline().build_args(SimpleNamespace(**fields))
    assert tuple(getattr(parsed, o) for o in OPTS) == DEFAULTS
    parsed = RealPipeline().build_args(job(telekinesis='off', flying_carry='off'))
    assert tuple(getattr(parsed, o) for o in OPTS) == ('off', 'off', 'off')
