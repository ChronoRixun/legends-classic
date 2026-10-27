"""Beta 9 moves (candidate 082b): the product CLI carries build_xml1's ini-only --telekinesis / --guard-decide /
--flying-carry options to the build, defaults off (unchanged until a live round and the owner's hand test pass)."""
from pathlib import Path

import build_xml1
from xml1builder.cli import make_parser
from xml1builder.commands import Job
from xml1builder.pipeline import RealPipeline

OPTS = ('telekinesis', 'guard_decide', 'flying_carry')


def job(**kw):
    return Job(out=Path('out'), xml2=Path('xml2'), cache=Path('cache'), iso=None, movies=True, jobs=1, prepare_jobs=1, **kw)


def test_the_cli_parses_the_three_options_and_they_default_off():
    plain = make_parser().parse_args(['build'])
    assert all(getattr(plain, o) == 'off' for o in OPTS)
    on = make_parser().parse_args(['build', '--telekinesis', 'xml1', '--guard-decide', 'xml1', '--flying-carry', 'xml1'])
    assert all(getattr(on, o) == 'xml1' for o in OPTS)


def test_build_args_pass_them_through_and_a_default_job_is_unchanged():
    p = RealPipeline()
    plain = p.build_args(job())
    assert all(getattr(plain, o) == 'off' for o in OPTS)
    assert all(getattr(plain, o) == getattr(build_xml1.parse_args(['--out', 'x']), o) for o in OPTS)
    on = p.build_args(job(telekinesis='xml1', guard_decide='xml1', flying_carry='xml1'))
    assert all(getattr(on, o) == 'xml1' for o in OPTS)
    assert on.grab_carry == 'xml1'                      # build_xml1's own dependency check passes with the default lifecycle
    one = p.build_args(job(guard_decide='xml1'))
    assert (one.telekinesis, one.guard_decide, one.flying_carry) == ('off', 'xml1', 'off')


def test_the_report_record_carries_them_for_fix_ini():
    # the pipeline's report records every CONTENT_OPTS option from these args; fix_ini.port_keys reads them back
    assert all(o in build_xml1.CONTENT_OPTS and build_xml1.CONTENT_OPTS[o] == ((), 'off') for o in OPTS)
