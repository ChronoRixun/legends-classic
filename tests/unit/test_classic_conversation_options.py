"""Default-off appearance, CLI propagation and safe rebuilds on synthetic inputs."""
import json
import time
from types import SimpleNamespace
from unittest.mock import patch

import build_xml1
from xml1build import common as C
from xml1builder.cli import make_parser
from xml1builder.errors import BuilderError
from xml1builder.pipeline import RealPipeline
from test_moves_builder_cli import job
from test_conversation_appearance import appearance, context, MODEL


def test_classic_conversation_defaults_off_and_explicit_modes_reach_pipeline():
    parser = make_parser()
    assert parser.parse_args(['build']).classic_conversation == 'off'
    assert build_xml1.parse_args(['--out', 'x']).classic_conversation == 'off'
    for mode in ('off', 'xml1'):
        parsed = parser.parse_args(['build', '--classic-conversation', mode])
        assert RealPipeline().build_args(job(classic_conversation=parsed.classic_conversation)).classic_conversation == mode
        assert build_xml1.parse_args(['--out', 'x', '--classic-conversation', mode]).classic_conversation == mode
    fields = vars(job()).copy()
    fields.pop('classic_conversation')
    assert RealPipeline().build_args(SimpleNamespace(**fields)).classic_conversation == 'off'


def test_classic_conversation_invalid_options_refused():
    try:
        make_parser().parse_args(['build', '--classic-conversation', 'on'])
    except BuilderError as exc:
        assert exc.code == 'E_USAGE'
    else:
        raise AssertionError('invalid public mode accepted')
    try:
        build_xml1.parse_args(['--out', 'x', '--classic-conversation', 'on'])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError('invalid developer mode accepted')


def test_classic_conversation_cli_job_real_args_and_report_roundtrip(tmp_path):
    from test_builder_cli import setup, build_argv, run
    from builder_stub import StubPipeline
    ctx, _, _ = context(tmp_path / 'assets')
    xml2, iso, out, cache = setup(tmp_path / 'cli')
    observed = []

    def module(synthetic_ctx, current_job):
        args = RealPipeline().build_args(current_job)
        observed.append(args.classic_conversation)
        # Exercise the real pipeline report writer, not the stub's summary.
        report_job = SimpleNamespace(ctx=ctx, args=args, out=ctx.out, xml2=current_job.xml2,
                                     movies=current_job.movies, t0=time.time())
        RealPipeline().write_report(report_job, {})

    for selection in ('xml1', 'off'):
        code, events, error = run(build_argv(xml2, iso, out, cache, '--classic-conversation', selection),
                                  stub={'module_fn': module})
        assert code == 0, error
        assert events[-1]['ok']
        assert json.loads((ctx.out / '_build/report.json').read_text())['build']['classic_conversation'] == selection
        assert C.args_for_out(ctx.out).classic_conversation == selection
    assert observed == ['xml1', 'off']
    assert StubPipeline.instances


def test_classic_conversation_developer_entry_records_selection_and_restores_base(tmp_path):
    from xml1build import frontend as F, savefiles
    ctx, source, base = context(tmp_path)
    (ctx.base / 'XMen2.exe').write_bytes(b'synthetic executable placeholder')
    argv = ['--out', str(ctx.out), '--base', str(ctx.base), '--only', 'frontend',
            '--no-validate', '--no-movies']
    # Only unrelated content families are stubbed: run the actual entry point,
    # argument parser, sync, carry decisions, conversation writer and report writer.
    with patch.object(build_xml1, 'make_sources', return_value=ctx.sources), \
            patch.object(F, 'run', side_effect=appearance().write), patch.object(savefiles, 'run'):
        for selection in ('xml1', 'off'):
            assert build_xml1.main(argv + ['--classic-conversation', selection]) == 0
            report = json.loads((ctx.out / '_build/report.json').read_text())
            assert report['build']['classic_conversation'] == selection
            expected = source if selection == 'xml1' else base
            assert (ctx.out / MODEL).read_bytes() == expected.read_bytes()


def test_classic_conversation_standalone_validator_restores_mode_and_allows_override(tmp_path):
    from xml1build import validate as V
    ctx, _, _ = context(tmp_path)
    args = build_xml1.parse_args(['--out', str(ctx.out), '--classic-conversation', 'xml1'])
    record(ctx.out, args)
    modes = []

    def run_check(ctx):
        modes.append(ctx.args.classic_conversation)

    with patch.object(V, 'run', side_effect=run_check):
        argv = ['--out', str(ctx.out), '--base', str(ctx.base)]
        assert V.main(argv) == 0
        assert V.main(argv + ['--classic-conversation', 'off']) == 0
    assert modes == ['xml1', 'off']


def record(out, args, *, legacy=False):
    values = {key: getattr(args, key, default) for key, (_, default) in build_xml1.CONTENT_OPTS.items()}
    if legacy:
        values.pop('classic_conversation', None)
    (out / '_build').mkdir(parents=True, exist_ok=True)
    (out / '_build/report.json').write_text(json.dumps({'build': values}), encoding='utf-8')


def test_classic_conversation_old_records_mean_off_and_selection_invalidates_frontend(tmp_path):
    args = build_xml1.parse_args(['--out', str(tmp_path)])
    record(tmp_path, args, legacy=True)
    assert getattr(C.args_for_out(tmp_path), 'classic_conversation', None) == 'off'
    assert build_xml1.plan_content_opts(tmp_path, args, []) == []
    args.classic_conversation = 'xml1'
    assert build_xml1.plan_content_opts(tmp_path, args, []) == ['frontend']
    record(tmp_path, args)
    assert C.args_for_out(tmp_path).classic_conversation == 'xml1'
    args.classic_conversation = 'off'
    assert build_xml1.plan_content_opts(tmp_path, args, []) == ['frontend']


def test_classic_conversation_partial_rebuild_carry_and_on_to_off_restore(tmp_path):
    ctx, source, base = context(tmp_path)
    args = build_xml1.parse_args(['--out', str(ctx.out)])
    record(ctx.out, args, legacy=True)
    # Fresh OFF, then a partial build changing only this selection.
    appearance().write(ctx)
    args.classic_conversation = ctx.args.classic_conversation = 'xml1'
    selected = ['scripts'] + build_xml1.plan_content_opts(ctx.out, args, ['scripts'])
    carry, _ = build_xml1.plan_carry(ctx.registry, selected, ctx.out, True)
    C.sync_base(ctx.base, ctx.out, keep=carry, log=lambda *_: None)
    appearance().write(ctx)
    assert (ctx.out / MODEL).read_bytes() == source.read_bytes()
    record(ctx.out, args)
    carry, _ = build_xml1.plan_carry(ctx.registry, ['scripts'], ctx.out, True)
    assert MODEL.lower() in carry
    args.classic_conversation = ctx.args.classic_conversation = 'off'
    selected = ['scripts'] + build_xml1.plan_content_opts(ctx.out, args, ['scripts'])
    carry, _ = build_xml1.plan_carry(ctx.registry, selected, ctx.out, True)
    assert MODEL.lower() not in carry
    ctx.registry = C.Registry()
    C.sync_base(ctx.base, ctx.out, keep=carry, log=lambda *_: None)
    appearance().write(ctx)
    assert (ctx.out / MODEL).read_bytes() == base.read_bytes()
    assert not ctx.registry.entries


def test_classic_conversation_changes_no_save_fingerprint_or_other_resources(tmp_path):
    from lcsave.lcfiles import content_fingerprint
    ctx, _, _ = context(tmp_path, 'xml1')
    untouched = {'Data/catalogue.lcc': b'synthetic catalogue', 'Data/table.lcbind': b'synthetic binding',
                 'Data/fontmap.xmlb': b'synthetic fonts', 'Conversations/example.engb': b'synthetic conversation',
                 'HUD/speaker.igb': b'synthetic portrait',
                 'Packages/generated/maps/package/permanent.pkgb': b'synthetic package entry',
                 'xml2-fix.ini': b'[Game]\nAutoAdvance=1\nReplyVoices=1\nReplyCursor=1\nOnlineConversations=1\n'}
    for rel, data in untouched.items():
        path = ctx.out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    before = content_fingerprint(str(ctx.out))
    assert before is not None
    appearance().write(ctx)
    assert content_fingerprint(str(ctx.out)) == before
    assert all((ctx.out / rel).read_bytes() == data for rel, data in untouched.items())
