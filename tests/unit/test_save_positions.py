"""Saved talent positions (SPEC 61): a save names a hero's shared talents by their position in
Data/shared_talents, so every release keeps the 0.1.7 slots and appends what it adds. Talent names here are the
engine identifiers the builder writes (no game text); the extra talents are invented."""
import xml.etree.ElementTree as ET
from types import SimpleNamespace

from xml1build import save_positions as SP
from xml1build.validate import Check, Validator

# the 61 slots of builder 0.1.5 - 0.1.7, as their saves hold them (ids 0..60): never edit, only append
V017 = """
fightstyle_finesse1 fightstyle_hero fightstyle_wrestling fightstyle_psionic fightstyle_gun_rifle fightstyle_gun_hip
fightstyle_baton fightstyle_huge fightstyle_nonhuman leadership critical might flight energy_resistant
mental_resistant physical_resistant energy_resistant_share mental_resistant_share physical_resistant_share
spawn_invis dr_stun sentinel_special boss_resistances monst_dmg_high fightstyle_villain avalanche_special
aval_crack aval_quake blob_special blob_butt blob_belly forge_special havok_beam havok_nova havok_special
juggernaut_special jug_punch jug_slam jug_armor magnetoboss_special marrow_shards marrow_armor marrow_xtreme
mastermold_special physical_res sabre_special steal_form pyro_flame pyro_firering pyro_firebat sabretooth_special
sabre_spin sabre_claw sentspider_special shadow_special as_special toad_special acrobatics toughness mutantmastery
x1_npc_energy""".split()


def shared_root(names):
    root = ET.Element('talents')
    for n in names:
        t = ET.SubElement(root, 'talent', {'name': n})
        ET.SubElement(t, 'level')
    return root


def names_of(root):
    return [t.get('name') for t in root if t.tag == 'talent']


def test_first_61_slots_are_the_017_order():
    assert len(V017) == 61
    assert list(SP.SHARED_TALENT_ORDER[:61]) == V017
    assert list(SP.SHARED_TALENT_ORDER_017) == V017
    # the slots players' saves hold ranks in (0.1.8 moved each of these)
    for slot, name in ((4, 'fightstyle_gun_rifle'), (9, 'leadership'), (57, 'acrobatics'), (58, 'toughness'),
                       (59, 'mutantmastery')):
        assert SP.SHARED_TALENT_SLOTS[name] == slot


def test_018_additions_follow_the_017_slots_in_the_order_added():
    assert list(SP.SHARED_TALENT_ORDER[61:]) == ['grab', 'x1_fightstyle_gun_rifle']
    assert len(set(SP.SHARED_TALENT_ORDER)) == len(SP.SHARED_TALENT_ORDER)
    assert len(SP.SHARED_TALENT_ORDER) < 99                     # shared ids 0..98


def test_ordering_puts_the_018_list_back_and_appends_new_talents():
    # the 0.1.8 list: gun_rifle gone, grab at 9, the rifle style at 32 - plus an invented talent mid-list
    v018 = [n for n in V017 if n != 'fightstyle_gun_rifle']
    v018.insert(9, 'grab')
    v018.insert(32, 'x1_fightstyle_gun_rifle')
    v018.insert(20, 'made_up_new_talent')
    root = shared_root(['fightstyle_gun_rifle'] + v018)   # held talent wherever the prune left it
    assert SP.order_shared_talents(root)
    assert names_of(root) == V017 + ['grab', 'x1_fightstyle_gun_rifle', 'made_up_new_talent']
    assert not SP.order_shared_talents(root)               # idempotent
    assert all(len(list(t)) == 1 for t in root)            # definitions moved whole


def test_order_problems_name_the_first_moved_slot():
    good = V017 + ['grab', 'x1_fightstyle_gun_rifle', 'made_up_new_talent']
    assert SP.shared_order_problems(good) == ([], [])
    moved = V017[:9] + ['grab'] + V017[9:] + ['x1_fightstyle_gun_rifle']
    errors, _ = SP.shared_order_problems(moved)
    assert len(errors) == 1 and 'slot 9' in errors[0] and "'grab'" in errors[0]


def test_a_dropped_slot_is_an_error_a_missing_tail_a_warning():
    hole = [n for n in V017 if n != 'fightstyle_gun_rifle'] + ['grab', 'x1_fightstyle_gun_rifle']
    errors, _ = SP.shared_order_problems(hole)
    assert any("['fightstyle_gun_rifle'] missing" in m for m in errors)
    errors, warnings = SP.shared_order_problems(V017)
    assert not errors and warnings and 'grab' in warnings[0]


def v31(talents, tail=None):
    validator = Validator.__new__(Validator)
    validator._stats = {'talents': talents}
    validator._scan = SimpleNamespace(fall_kill_volumes={'maps/invented/ridge.engb': []},
                                      entinst_tail=tail or {}, twins=set())
    check = Check('V31', 'save positions')
    validator.save_positions(check)
    return check


def test_v31_checks_both_halves_and_the_fall_volume_tail():
    good = V017 + ['grab', 'x1_fightstyle_gun_rifle']
    assert not v31({'.engb': good, '.xmlb': list(good)}).errors
    swapped = good[:4] + [good[5], good[4]] + good[6:]
    check = v31({'.engb': good, '.xmlb': swapped})
    assert any('shared_talents.xmlb' in m and 'slot 4' in m for m in check.errors)
    assert any('different orders' in m for m in check.errors)
    check = v31({'.engb': good, '.xmlb': list(good)},
                tail={'maps/invented/ridge.engb': ["maps/invented/ridge.engb: entinst 'pad_c' follows ..."]})
    assert len(check.errors) == 1 and 'pad_c' in check.errors[0]
    assert v31({'.engb': None, '.xmlb': good}).errors
