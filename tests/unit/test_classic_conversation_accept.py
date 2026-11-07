"""Launcher compatibility: both appearance choices are accepted and reach the builder."""
from xml1builder.cli import make_parser
from xml1builder.commands import Job
from xml1builder.pipeline import RealPipeline
from test_moves_builder_cli import job


def test_parser_accepts_both_values_default_off():
    assert make_parser().parse_args(['build']).classic_conversation == 'off'
    for mode in ('off', 'xml1'):
        assert make_parser().parse_args(['build', '--classic-conversation', mode]).classic_conversation == mode


def test_xml1_reaches_the_build_args():
    assert RealPipeline().build_args(job(classic_conversation='xml1')).classic_conversation == 'xml1'


def test_off_is_the_default_build_choice():
    assert Job.__dataclass_fields__['classic_conversation'].default == 'off'
    assert RealPipeline().build_args(job()).classic_conversation == 'off'
