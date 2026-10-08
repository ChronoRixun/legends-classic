"""Talent-set files for NPC-only shared talents (SPEC <number assigned at merge>, the TalentRegistry 100/9 fix).

XMen2.exe's TalentRegistry admits 100 registered names from 9 distinct files (registration 0x4c0080, file list
0x4c0460; a 101st name or 10th file is refused without a word). Builder 0.1.x hoisted every XML1 NPC-only
special talent (sabre_claw, jug_punch, pyro_flame ...) into Data/shared_talents, so every zone paid their
registry cost whether or not the zone spawns the NPC: xjet/blackbird_arbiter reached 116 demanded unique names
with a four-hero party and silently lost the party's talents. XML1 kept those definitions inline in each NPC's
own stats entry; this module restores that per-NPC shape on the XML2 engine: NPC-only shared talents move out of
shared_talents into small per-set files under data/talents/npc/, and each NPC's character package lists its set
file as an xml_talents entry (loaded when the NPC's package loads, reused by name when several NPCs share a set).

Partition rule (heroes.py shared_keep): a shared talent referenced by any playable hero (stats or style) or
named by an XML2 base definition stays in shared_talents, as does the NPC energy pool (npc_values.ENERGY_TALENT,
SPEC 24: ~100 NPCs carry it, so a file would load in nearly every zone). A talent referenced only by npcstat
entries moves to the set file of the NPCs that use it. Saved games do not hold NPC-only talents; the new save
format stores hero talents by name, and old saves convert through the frozen per-era tables (lcsave legacy), so
removing mid-order names from shared_talents moves no saved rank.

Sets that need only generic combat talents collapse into one npc_generic file so a zone full of mixed mobs
pays a single extra file slot, not three.
"""
from __future__ import annotations

# generic combat talents most mobs share; any NPC set contained in this union uses the one shared file
GENERIC = frozenset(('fightstyle_villain', 'x1_fightstyle_gun_rifle', 'physical_res'))
GENERIC_FILE = 'data/talents/npc_generic'
NPC_DIR = 'data/talents/npc'


def npc_set(refs, moving):
    """the moving-talent set of one npcstat entry: its <talent> names that left shared_talents."""
    return frozenset(r for r in (refs or ()) if r in moving)


# XML2's own shared_talents names (the base install's 34): save-stable, never part of the NPC move
X2_BASE_TALENTS = frozenset("""
fightstyle_finesse1 fightstyle_hero fightstyle_wrestling fightstyle_psionic fightstyle_gun_rifle
fightstyle_gun_hip fightstyle_baton fightstyle_staff fightstyle_huge fightstyle_nonhuman mutantmaster leadership
block grab critical might flight psionic_fury energy_resistant mental_resistant physical_resistant
energy_resistant_share mental_resistant_share physical_resistant_share spawn_invis knock_resist dr_stun
sentinel_special boss_resistances corrupt_vampire deadpool_regen blimpyboy monst_dmg_high monst_dmg_low
""".split())


def npc_moving(refs, hero_refs, x2_base=None, energy_talent=''):
    """one entry's moving set under the single partition both the zones module and heroes use: its talent
    references minus names the XML1 heroes reference (those stay reachable for heroes), XML2 base
    definitions and the NPC energy pool (which stays in shared_talents)."""
    base = X2_BASE_TALENTS if x2_base is None else x2_base
    return frozenset(r for r in (refs or ())
                     if r not in hero_refs and r not in base and r != (energy_talent or '').lower())


def npc_talent_files(npc_refs, hero_refs, x2_base=None, energy_talent=''):
    """{npcstat name: its set-file rel} for every entry with a non-empty moving set."""
    out = {}
    for name, refs in npc_refs.items():
        s = npc_moving(refs, hero_refs, x2_base, energy_talent)
        if s:
            out[name] = set_file(s)
    return out


def set_file(talent_set):
    """the data/talents rel of a non-empty moving set ('' for an empty one). Generic subsets share npc_generic;
    every other set gets one file named by its sorted talents, so distinct sets never share a file."""
    s = frozenset(talent_set or ())
    if not s:
        return ''
    if s <= GENERIC:
        return GENERIC_FILE
    return NPC_DIR + '/' + '+'.join(sorted(s))


def partition_moves(keep, hero_refs, npc_refs, x2_shared_names, energy_talent):
    """the kept shared names that move to npc set files: kept names only npcstat entries reference - no hero
    stats/style, no XML2 base definition (those stay save-stable in shared), not the NPC energy pool."""
    npc_only = {n for n in npc_refs if npc_moving({n}, hero_refs, x2_shared_names, energy_talent)}
    return sorted(n for n in keep if n in npc_only)


def file_sets(npc_refs, moving):
    """{set-file rel: frozenset(talents)} over every npcstat entry's moving set (empty sets skipped); every set
    that maps to one file (npc_generic) contributes, so a file's content is the union of its users' sets."""
    out = {}
    for refs in npc_refs.values():
        s = npc_set(refs, moving)
        if s:
            f = set_file(s)
            out[f] = out.get(f, frozenset()) | s
    return out
