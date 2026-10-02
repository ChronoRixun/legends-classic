"""SPEC 39 (2026-10-01 audit W11) on made-up data - no game files:
a conversation whose response tagjumps into another file gets the tagged line (and its subtree) copied
into the jumping file (conversations.resolve_cross_file_tagjumps), so XMen2.exe's same-file lookup finds it."""
import types
import xml.etree.ElementTree as ET

from xml1build import conversations as CV

JUMP_CONV = 'conversations/test/hub/jumper.eng'
SRC_CONV = 'conversations/test/hub/menu.eng'
TABLE = {'test/hub/jumper': (('hub_menu', 'test/hub/menu'),)}

MENU = (
    '<conversation><startCondition>'
    '<participant name="default">'
    '<line text="%GUIDE%Pick one." tagindex="hub_menu">'
    '<response text="First"><line text="%GUIDE%The first one."><response text="%END%" conversationend="true"/></line></response>'
    '<response text="Again" tagjump="hub_menu"/>'
    '</line>'
    '</participant></startCondition></conversation>'
)

INTRO = (
    '<conversation><startCondition>'
    '<participant name="default">'
    '<line text="%GUIDE%Welcome.">'
    '<response text="%BLANK%" tagjump="hub_menu" chosenscriptfile="test/leave" conversationend="true"/>'
    '</line>'
    '</participant></startCondition></conversation>'
)


def ctx_with(source=MENU):
    warnings, notes, reads = [], [], []

    def read(rel):
        reads.append(rel)
        if rel != SRC_CONV:
            raise KeyError(rel)
        return ET.fromstring(source)

    return types.SimpleNamespace(read_x1_xml=read, warn=warnings.append,
                                 note=notes.append), warnings, notes, reads


def test_cross_file_tagjump_copies_the_tagged_subtree():
    ctx, warnings, notes, reads = ctx_with()
    root = ET.fromstring(INTRO)
    assert CV.resolve_cross_file_tagjumps(ctx, root, JUMP_CONV, TABLE) == 1
    assert not warnings
    assert reads == [SRC_CONV]
    tagged = [el for el in root.iter() if el.tag == 'line' and el.get('tagindex') == 'hub_menu']
    assert len(tagged) == 1
    menu = tagged[0]
    assert [r.get('text') for r in menu] == ['First', 'Again']      # both responses came with the subtree
    # the copy is the root line of a NEW participant of the jumping startCondition (where the engine registers
    # tagIndexes); the default participant keeps its single root line, so entry selection is untouched
    holder = next(el for el in root.iter() if el.tag == 'participant' and menu in list(el))
    assert holder.get('name') == 'x1_tagjump_hub_menu'
    assert holder is not next(el for el in root.iter() if el.tag == 'participant')
    default = next(el for el in root.iter() if el.tag == 'participant')
    assert default.get('name') == 'default' and len([c for c in default if c.tag == 'line']) == 1
    jumper = next(el for el in root.iter() if el.get('tagjump') == 'hub_menu')
    assert jumper.get('chosenscriptfile') == 'test/leave'           # the script stays
    assert jumper.get('conversationend') is None                    # the end flag goes: XMen2.exe ends the
    # conversation on a response's conversationEnd even when its tagJump resolves (SPEC 39.1), which would
    # preempt the menu the copy just made reachable (the menu copy ends at its own %END%)


def test_cross_file_tagjump_is_idempotent_and_marks_no_second_read():
    ctx, _, _, reads = ctx_with()
    root = ET.fromstring(INTRO)
    assert CV.resolve_cross_file_tagjumps(ctx, root, JUMP_CONV, TABLE) == 1
    snap = ET.tostring(root)
    assert CV.resolve_cross_file_tagjumps(ctx, root, JUMP_CONV, TABLE) == 0
    assert ET.tostring(root) == snap
    assert reads == [SRC_CONV]


def test_same_case_local_tagindex_needs_no_copy():
    ctx, _, _, reads = ctx_with()
    root = ET.fromstring(INTRO.replace(
        '</participant>', '<line text="%GUIDE%Local." tagindex="hub_menu"/></participant>'))
    assert CV.resolve_cross_file_tagjumps(ctx, root, JUMP_CONV, TABLE) == 0
    assert reads == []                                              # the source is never read


def test_lookup_is_case_sensitive_so_other_case_tagindex_does_not_count():
    ctx, warnings, _, _ = ctx_with()
    root = ET.fromstring(INTRO.replace(
        '</participant>', '<line text="%GUIDE%Local." tagindex="HUB_MENU"/></participant>'))
    assert CV.resolve_cross_file_tagjumps(ctx, root, JUMP_CONV, TABLE) == 1
    assert not warnings


def test_missing_source_conversation_warns_and_changes_nothing():
    ctx, warnings, _, _ = ctx_with()
    root = ET.fromstring(INTRO)
    table = {'test/hub/jumper': (('hub_menu', 'test/hub/absent'),)}
    assert CV.resolve_cross_file_tagjumps(ctx, root, JUMP_CONV, table) == 0
    assert warnings and 'absent' in warnings[0]


def test_source_without_the_tagindex_warns_and_changes_nothing():
    ctx, warnings, _, _ = ctx_with(source=MENU.replace(' tagindex="hub_menu"', ''))
    root = ET.fromstring(INTRO)
    assert CV.resolve_cross_file_tagjumps(ctx, root, JUMP_CONV, TABLE) == 0
    assert warnings and 'hub_menu' in warnings[0]


def test_no_jumping_response_and_no_table_entry_are_silent_noops():
    ctx, warnings, notes, reads = ctx_with()
    root = ET.fromstring(INTRO.replace(' tagjump="hub_menu"', ''))
    assert CV.resolve_cross_file_tagjumps(ctx, root, JUMP_CONV, TABLE) == 0
    assert CV.resolve_cross_file_tagjumps(ctx, root, 'conversations/test/hub/other.eng', TABLE) == 0
    assert CV.resolve_cross_file_tagjumps(ctx, root, 'dialogs/test/hub/jumper.eng', TABLE) == 0
    assert not warnings and not notes and reads == []
