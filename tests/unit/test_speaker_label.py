"""XML1's "Alison" speaker label (scripts.SPEAKER_TOKEN_LABELS; XML2 Fix [Game] ClassicSpeakers=1), synthetic data."""
import copy
import types
import xml.etree.ElementTree as ET
from contextlib import ExitStack
from unittest.mock import patch

from xml1build import fix_ini as FI, scripts as S


def test_alias_label_only_where_the_alias_target_stays():
    assert S.speaker_alias_label("%ALISON%Invented first line.", "%MAGMA%Invented first line.") == 'Alison'
    assert S.speaker_alias_label('%alison%Ok.', '%MAGMA%Ok.') == 'Alison'
    # the NPC Alison's own lines become her speaker entries (labelled "Alison" by their charactername already)
    assert S.speaker_alias_label('%ALISON%Help!', '%ALISON%Help!') is None
    assert S.speaker_alias_label('%ALISON%Help!', '%ALISON_SCRIPTED%Help!') is None
    # Magma's own lines, other speakers, no token, a token not at the start
    assert S.speaker_alias_label('%MAGMA%Mine.', '%MAGMA%Mine.') is None
    assert S.speaker_alias_label('%FROST%Hello.', '%EMMA%Hello.') is None
    assert S.speaker_alias_label('Hello %ALISON%', 'Hello %MAGMA%') is None
    assert S.speaker_alias_label('', '') is None and S.speaker_alias_label(None, None) is None


def _rewrite(rel, xml):
    root = ET.fromstring(xml)
    ctx = types.SimpleNamespace(xml2_api={}, note=lambda *a: None, warn=lambda *a: None)
    with ExitStack() as stack:
        for target, name, value in ((S, '_inline_map', {}), (S, '_inline_end_refs', {}),
                                    (S, '_drop_cut_mission_responses', 0)):
            stack.enter_context(patch.object(target, name, lambda *a, value=value: value))
        stack.enter_context(patch.object(S.BP, 'rewrite_data', lambda *a: 0))
        stack.enter_context(patch.object(S.SF, 'fix_player_starts', lambda *a: 0))
        stack.enter_context(patch.object(S.CV, 'resolve_cross_file_tagjumps', lambda *a: 0))
        stack.enter_context(patch.object(S.CV, 'mark_auto_advance', lambda *a: 0))
        stack.enter_context(patch.object(S.C, 'frontend_mode', lambda *a: 'xml1'))
        n = S.rewrite_data_tree(ctx, root, rel)
        again = copy.deepcopy(root)
        assert S.rewrite_data_tree(ctx, again, rel) == 0           # idempotent, as scripts_selftest T7 checks
    return n, root


def test_party_magma_alison_lines_carry_the_label():
    n, root = _rewrite('conversations/mansion/dr_mag2/2_2_1.eng',
                       '<conversation><startCondition><participant name="default">'
                       '<line text="%ALISON%Invented first line." soundtoplay="voice/test/line_0001">'
                       '<response text="%CONTINUE%"><line text="%MAGMA%Mine." textb="%ALISON%Both."/></response>'
                       '</line><line text="%CYCLOPS%Go."/></participant></startCondition></conversation>')
    lines = [el for el in root.iter() if el.tag == 'line']
    assert [l.get('text') for l in lines] == ['%MAGMA%Invented first line.', '%MAGMA%Mine.', '%CYCLOPS%Go.']
    assert [l.get(S.SPEAKER_LABEL_ATTR) for l in lines] == ['Alison', 'Alison', None]   # textb alone carries it too
    assert lines[1].get('textb') == '%MAGMA%Both.'
    assert not any(el.get(S.SPEAKER_LABEL_ATTR) for el in root.iter() if el.tag != 'line')
    assert n == 4      # 2 tokens rewritten (a text, a textb) + 2 labels


def test_npc_alison_lines_keep_their_own_speaker_entry():
    # SPEC 18.1: 2_2_1_3b is the simulated Alison's (alison_scripted), 1_1_5_1b the NPC Alison's
    for rel, token in (('conversations/mansion/dr_mag2/2_2_1_3b.eng', '%ALISON_SCRIPTED%'),
                       ('conversations/nyc/alison/1_1_5_1b.eng', '%ALISON%')):
        _n, root = _rewrite(rel, '<conversation><line text="%ALISON%Somebody help me!"/></conversation>')
        line = next(el for el in root.iter() if el.tag == 'line')
        assert line.get('text').upper() == token + 'SOMEBODY HELP ME!' and line.get(S.SPEAKER_LABEL_ATTR) is None


def test_build_ini_turns_the_label_on():
    keys = FI.game_keys()
    assert keys['ClassicSpeakers'] == '1' and 'ClassicSpeakers' in FI.PORT_OWNED['Game']
    # display only, but 1.8.0-beta.7 is also the first DLL to read the schema 3 weapon-brain rows every build writes,
    # so the key is the builder's beta 7 marker: a beta 6 DLL is refused naming it (test_builder_parts)
    assert 'ClassicSpeakers' in FI.RELEASE_18_KEYS['Game']
