"""Identities a save keeps (SPEC 61).

XMen2.exe names a hero's shared talents by their position in Data/shared_talents (talent ids below 100 are
the position; a hero's own talents are (stats index + 1) x 100 + the position in its talent file). Neither a name
nor a count is written, so a build that inserts, removes or reorders a shared talent moves the ranks of every
saved hero onto other talents: builder 0.1.8 dropped fightstyle_gun_rifle (slot 4) and inserted grab (slot 9) and
x1_fightstyle_gun_rifle (slot 32), so a 0.1.7 save read its leadership rank as grab and its acrobatics, toughness
and mutantmastery ranks as their neighbours'.

SHARED_TALENT_ORDER is the order 0.1.5-0.1.7 kept (the 61 names), then the names later releases appended. From
0.2.0 the LC save format stores talent names, so positions are no longer save-bound: old saves convert through
the frozen per-era tables (lcsave legacy) and the built file may drop or move names (the TalentRegistry fix moves
NPC-only talents to data/talents/npc set files). The order survives as a sanity rule for the survivors.
"""
from __future__ import annotations

# 0.1.5 - 0.1.7 (content versions 7 - 9): XML2's kept names in XML2's order, then the first game's additions
SHARED_TALENT_ORDER_017 = tuple("""
fightstyle_finesse1 fightstyle_hero fightstyle_wrestling fightstyle_psionic fightstyle_gun_rifle fightstyle_gun_hip
fightstyle_baton fightstyle_huge fightstyle_nonhuman leadership critical might flight energy_resistant
mental_resistant physical_resistant energy_resistant_share mental_resistant_share physical_resistant_share
spawn_invis dr_stun sentinel_special boss_resistances monst_dmg_high fightstyle_villain avalanche_special
aval_crack aval_quake blob_special blob_butt blob_belly forge_special havok_beam havok_nova havok_special
juggernaut_special jug_punch jug_slam jug_armor magnetoboss_special marrow_shards marrow_armor marrow_xtreme
mastermold_special physical_res sabre_special steal_form pyro_flame pyro_firering pyro_firebat sabretooth_special
sabre_spin sabre_claw sentspider_special shadow_special as_special toad_special acrobatics toughness mutantmastery
x1_npc_energy""".split())
# 0.1.8 added grab (issue #51) and x1_fightstyle_gun_rifle (issue #52); 0.1.10 moves them here, after the 0.1.7 list
SHARED_TALENT_ORDER = SHARED_TALENT_ORDER_017 + ('grab', 'x1_fightstyle_gun_rifle')
SHARED_TALENT_SLOTS = {n: i for i, n in enumerate(SHARED_TALENT_ORDER)}


def ordered_names(names):
    """the shared talent names in save-stable order: the SHARED_TALENT_ORDER names present first, in that order,
    then the others in their given order (a talent new to this release is appended)."""
    present = {n.lower() for n in names}
    pinned = [n for n in SHARED_TALENT_ORDER if n in present]
    return pinned + [n for n in names if n.lower() not in SHARED_TALENT_SLOTS]


def order_shared_talents(root):
    """reorder the <talent> children of a shared_talents root in place (ordered_names); other children keep their
    places before the talents. -> True when the order changed."""
    talents = [t for t in root if t.tag == 'talent']
    before = [(t.get('name') or '').lower() for t in talents]
    want = ordered_names(before)
    if want == before:
        return False
    by_name = {}
    for t in talents:
        by_name.setdefault((t.get('name') or '').lower(), []).append(t)
        root.remove(t)
    for n in want:
        root.extend(by_name.pop(n, []))
    for rest in by_name.values():                   # duplicates (V-H4 reports them): keep, after the rest
        root.extend(rest)
    return True


def shared_order_problems(names, label='shared_talents', moved=()):
    """-> (errors, warnings) for one built shared_talents name list (lower-case, file order).

    0.2.0 names a saved hero's talents, not their positions (lcsave), so the 0.1.x pin that every SHARED_TALENT_ORDER
    name keeps its slot is history: old saves convert through the frozen per-era tables and the new format stores
    names. The order remains only as a sanity rule - survivors must keep the pinned RELATIVE order, so an
    accidental reorder is still caught - and a name that disappears is a warning naming why (the TalentRegistry
    fix moves NPC-only talents to data/talents/npc set files; `moved` lists them)."""
    errors, warnings = [], []
    names = [n.lower() for n in names]
    present = set(names)
    pinned = [n for n in SHARED_TALENT_ORDER if n in present]
    if [n for n in names if n in SHARED_TALENT_SLOTS] != pinned:
        errors.append(f'{label}: the surviving save-order talents are out of pinned order '
                      f'(expected relative order of {SHARED_TALENT_ORDER[0]!r}..{SHARED_TALENT_ORDER[-1]!r})')
    missing = [n for n in SHARED_TALENT_ORDER if n not in present]
    if missing:
        moved = set(moved)
        why = [f'{n} (npc set file)' if n in moved else f'{n} (unreferenced)' for n in missing]
        warnings.append(f'{label}: {why} left the shared pool under the TalentRegistry fix / prune; '
                        f'saves store talent names, old saves convert through the era tables')
    return errors, warnings
