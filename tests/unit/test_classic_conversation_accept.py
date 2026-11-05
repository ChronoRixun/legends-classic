"""beta.2: launchers 0.5.0-beta.4+ always send --classic-conversation to builders >= 0.6.0-beta.2. This builder accepts it:
off is a no-op (nothing reaches the pipeline), xml1 is refused with a clear message (the feature arrives in 0.6.0-beta.3)."""
from xml1builder.cli import make_parser
from xml1builder.commands import cmd_build
from xml1builder.errors import BuilderError
from xml1builder.pipeline import RealPipeline
from xml1builder.commands import Job


def test_parser_accepts_both_values_default_off():
    assert make_parser().parse_args(['build']).classic_conversation == 'off'
    assert make_parser().parse_args(['build', '--classic-conversation', 'off']).classic_conversation == 'off'
    assert make_parser().parse_args(['build', '--classic-conversation', 'xml1']).classic_conversation == 'xml1'


def test_xml1_refused_before_any_work(tmp_path):
    a = make_parser().parse_args(['build', '--xml2', str(tmp_path / 'x'), '--out', str(tmp_path / 'o'),
                                  '--classic-conversation', 'xml1'])
    try:
        cmd_build(a, None, None, None)
    except BuilderError as e:
        assert e.code == 'E_USAGE' and '0.6.0-beta.3' in e.msg
    else:
        raise AssertionError('xml1 must be refused')
    assert not (tmp_path / 'o').exists()


def test_off_never_reaches_the_build_args():
    assert 'classic_conversation' not in Job.__dataclass_fields__
    assert '--classic-conversation' not in RealPipeline.build_args.__code__.co_consts
