"""Synthetic serialized Skirmish help and owned-roster resource regressions."""
import copy
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import numpy as np
import xmlb
from xml1build import frontend as F, online_menus as O, heroes as H
from xml1build import main_fonts as MF
from xml1build.igb_file import IgbFile, IgbError
from test_main_appearance import fixture, raises


def test_skirmish_strings_replace_only_matching_localized_keys():
    keys = ['@DATA@SKIRMISH', '@DATA@SKIRMISH_MODE', '@DROOM@NOT_HIGH_ENOUGH',
            '@DROOM@NOT_HIGH_ENOUGH_SKIRMISH', '@DROOM@CHARACTER_LOCKED', '@DROOM@SKIRMISH']
    source_x, source_e = ET.Element('strings'), ET.Element('strings')
    for number, key in enumerate(keys + ['@SYNTHETIC@KEEP'], 9000):
        ET.SubElement(source_x, 'string', id=str(number), text=key)
        ET.SubElement(source_e, 'string', id=str(number), text='Synthetic text ' + str(number))
    before = xmlb.encode(source_x)
    ctx = SimpleNamespace(read_base_xmlb=lambda rel: copy.deepcopy(source_x if rel.endswith('.XMLB') else source_e))
    x, e, changed = F.strings_retext(ctx)
    # Exercise the emitted binary pair; token IDs and unrelated text must survive.
    actual = {a.get('id'): a.get('text') for a in xmlb.decode(xmlb.encode(e))}
    assert xmlb.encode(x) == before
    assert 'Experimental' in actual['9000']
    for number in ('9002', '9003'):
        assert actual[number].startswith('Play the campaign to unlock')
        for name, level in [('Brawl', '16'), ('King', '18'), ('Standing', '23'), ('Ladder', '30')]:
            assert name in actual[number] and level in actual[number]
    # The locked-row label must stay compact: it is also used in the roster list.
    assert actual['9004'] == 'Synthetic text 9004'
    assert 'lobby' in actual['9005'] and 'campaign' in actual['9005']
    assert actual['9006'] == 'Synthetic text 9006'
    assert changed == ['9000', '9001', '9002', '9003', '9005']


def test_skirmish_visible_game_tab_body_explains_each_campaign_unlock_level():
    # Live native Game-tab rows keep this body visible even when a grey row
    # cannot be selected; NOT_HIGH_ENOUGH is not their displayed help binding.
    source_x = ET.fromstring('<strings><string id="9100" text="@DATA@COMPETE_AGAINST_OTHER"/>'
                             '<string id="9101" text="@SYNTHETIC@KEEP"/></strings>')
    source_e = ET.fromstring('<strings><string id="9100" text="Synthetic mode overview"/>'
                             '<string id="9101" text="Synthetic unrelated text"/></strings>')
    ctx = SimpleNamespace(read_base_xmlb=lambda rel: copy.deepcopy(source_x if rel.endswith('.XMLB') else source_e))
    keys, english, changed = F.strings_retext(ctx)
    emitted = {row.get('id'): row.get('text') for row in xmlb.decode(xmlb.encode(english))}
    body = emitted['9100']
    assert body.startswith('Play the campaign to unlock modes:')
    for requirement in ('Brawl at level 16', 'King Of The Hill at 18',
                        'Last Man Standing at 23', 'Last Man Ladder at 30'):
        assert requirement in body
    assert 'Campaign character unlocks are also required.' in body
    assert len(body) <= 190
    assert xmlb.encode(keys) == xmlb.encode(source_x)
    assert emitted['9101'] == 'Synthetic unrelated text' and changed == ['9100']


def test_skirmish_fixed_roster_notice_is_authored_for_all_join_screens():
    from xml1build import online_fonts as OF
    for name in ('lc_online', 'lc_code', 'lc_browse'):
        screen = O.bound_layout(O.runtime_layout(name), OF.metrics())
        tree = xmlb.decode(xmlb.encode(O.menu_tree(screen)))
        node = tree.find("item[@name='lc_notice_skirmish']")
        assert node is not None, name
        text = node.get('text', '')
        assert 'fixed roster' in text and 'lobby' in text and 'host starts' in text
        assert not node.get('usecmd') and node.get('hide') == 'true'
        assert len(O.scene_layout(screen)) + len(O.backdrop_layouts()) <= O.engine_scene_anchors(O.ANCHOR_CAPABILITY)


def texture(pixels):
    h, w = pixels.shape[:2]
    fields = [(2, 'i'), (3, 'i'), (11, 'i'), (12, 'i'), (13, 'b'), (19, 'i')]
    return fixture([('igImage', None, fields)], [('igImage', {2:w, 3:h, 11:7, 12:pixels.nbytes, 13:1, 19:w*4})], [pixels.tobytes()])


def test_skirmish_portraits_replace_only_reserved_cells_and_keep_locked_cell():
    from xml1build import roster_portraits as R
    base = np.full((256, 256, 4), (11, 33, 55, 255), np.uint8)
    heads = {}
    for number, hero in enumerate(('beast', 'frost', 'jubilee', 'magma', 'psylocke')):
        pixels = np.full((128, 128, 4), (80 + 20*number, 120, 200, 255), np.uint8)
        pixels[:64, :, 0] = 220  # bottom-up asymmetry detects accidental image inversion.
        heads[hero] = texture(pixels)
    result = R.regenerate(texture(base), heads)
    actual = MF._image(IgbFile(result))
    mask = np.zeros((256, 256), bool)
    for number, hero in enumerate(('beast', 'frost', 'jubilee', 'magma', 'psylocke')):
        cell = int(H.TEXTUREICON.get(hero, H.TEXTUREICON_NONE)); assert cell == 48 + number
        y, x = (7 - cell//8)*32, (cell%8)*32
        mask[y:y+32, x:x+32] = True
        assert tuple(actual[y+4, x+16]) == (220, 120, 200, 255)
        assert tuple(actual[y+28, x+16]) == (80+20*number, 120, 200, 255)
    assert np.array_equal(actual[~mask], base[~mask])
    assert np.array_equal(actual[:32, 224:256], base[:32, 224:256])  # locked index 63
    raises(IgbError, lambda: R.regenerate(texture(base), {k:v for k,v in heads.items() if k != 'magma'}))


def test_skirmish_portrait_collision_refuses_to_replace_an_npc_icon():
    from xml1build import roster_portraits as R
    npc = ET.fromstring('<characters><stats name="synthetic_npc" textureicon="48"/></characters>')
    raises(IgbError, lambda: R.check_cells(npc))
    npc[0].set('textureicon', '45')
    R.check_cells(npc)

def test_skirmish_builds_require_the_profile_and_admission_guard_release():
    from xml1build import fix_ini as FI
    for version in ('0.6.1', '0.6.1-beta.1', '0.6.1-rc.1', FI.RI.PRIVATE_CANDIDATE.release):
        assert FI.required_xml2fix(version) == '>=1.11.1'
    assert b'lc_notice_skirmish' in O.DLL_PROBES


def test_skirmish_portrait_writer_emits_the_native_resource_path(tmp_path):
    from xml1build import roster_portraits as R
    base = np.full((256, 256, 4), (9, 19, 29, 255), np.uint8)
    template = tmp_path / 'native.igb'
    template.write_bytes(texture(base))
    paths = {}
    for hero, skin in R.HEADS.items():
        head = tmp_path / (skin + '.igb')
        head.write_bytes(texture(np.full((128, 128, 4), (210, 90, 40, 255), np.uint8)))
        paths['hud/hud_head_' + skin + '.igb'] = head
    output = tmp_path / 'out.igb'
    written = []
    def write(rel, data, **options):
        written.append(rel)
        output.write_bytes(data)
    ctx = SimpleNamespace(base_index=SimpleNamespace(path=lambda rel: template), x1_path=paths.get, write_bytes=write)
    R.write(ctx, ET.fromstring('<characters><stats name="synthetic_npc" textureicon="45"/></characters>'))
    assert written == ['Textures/ui/mini_convo_icons.IGB']
    atlas = MF._image(IgbFile(output.read_bytes()))
    assert tuple(atlas[36, 16]) == (210, 90, 40, 255)  # hero cell 48
    assert tuple(atlas[4, 240]) == (9, 19, 29, 255)  # locked cell 63
    ctx.out_index = SimpleNamespace(path=lambda rel: output)
    npc = ET.fromstring('<characters/>')
    R.validate(ctx, npc)
    output.write_bytes(texture(base))
    raises(IgbError, lambda: R.validate(ctx, npc))
