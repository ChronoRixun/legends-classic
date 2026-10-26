"""xml1build.anim_enums - the XML1 animation enums, their clips, mappings and flying carry nodes (SPEC 107).

XMen2.exe registers 210 animation enums (0x00..0xD1, every slot taken) in a fixed-capacity table; XML1 needs 23 more
for the flying carry (Phoenix / Rogue / Storm) and Juggernaut's grab victims. xml2-fix [Limits] AnimEnums=512
(gameplay rule 48, xml2-fix docs/anim-enums.md) raises the capacity and gives the 23 XML1 names fixed IDs 0xD2..0xE8 in
BUILTIN_ENUMS order; the DLL publishes the same list as a marked block (DLL_MARKER, u16 count, the names NUL-separated)
that the builder and validator compare with this one. With `--anim-enums xml1` (opt-in for now) the build:

  1. transplants the 21 XML1 clips into Actors/common.IGB (igb_anim_merge; the clips come from the player's disc);
  2. appends the 23 XML1 mappings to Data/shared_anims.XMLB (XML1's values verbatim, PC entries win, XML1's
     ea_mission1..20 are not added - PC's ea_zone1..20 stay, scripts_transform.rename_mission_anims): 209 + 23 = 232;
  3. adds XML1's carry FightMoves to Data/fightstyles/moveset_flying by MOVESET_FLYING_PRECEDENCE;
  4. writes [Limits] AnimEnums=512 (fix_ini.port_keys), refused on a DLL without the marker (fix_ini.check_anim_enums_dll).

Off (the default): none of the three files is written and no key: every output byte as before.

The two clips XML1's own common.igb lacks (igb_anim_merge.KNOWN_ABSENT_IN_XML1) are not invented: their mappings are
kept and the enums fall back to enum 0's animation, exactly as on XML1."""
from __future__ import annotations

import copy

# xml2-fix src/anim_enum_names.hpp extension order = IDs 0xD2.. (DESIGN 3.1; XML1 values 0x52..0x63, 0x75..0x79)
BUILTIN_ENUMS = (
    'ea_flyingcarry_flyfast', 'ea_flyingcarry_flyslow', 'ea_flyingcarry_idle', 'ea_flyingcarry_pickup',
    'ea_flyingcarry_throwdown', 'ea_flyingcarry_throwforward',
    'ea_flyingcarry_flyfast_v', 'ea_flyingcarry_flyslow_v', 'ea_flyingcarry_idle_v', 'ea_flyingcarry_pickup_v',
    'ea_flyingcarry_throwdown_v', 'ea_flyingcarry_throwforward_v',
    'ea_flyingcarry_flyfast_a', 'ea_flyingcarry_flyslow_a', 'ea_flyingcarry_idle_a', 'ea_flyingcarry_pickup_a',
    'ea_flyingcarry_throwdown_a', 'ea_flyingcarry_throwforward_a',
    'ea_jug_grab_start_v', 'ea_jug_grab_hold_v', 'ea_jug_grab_throw_v', 'ea_jug_grab_throw_left_v',
    'ea_jug_grab_throw_right_v',
)
FIRST_ID = 0xD2
NATIVE_ENUMS = 210                   # XMen2.exe 0x00..0xD1 (0x426990 cmp [ebp+0x10a4],0xd2)
CAPACITY = 512                       # [Limits] AnimEnums=512: the only value the DLL accepts
LIMIT_VALUE = str(CAPACITY)
MODES = ('off', 'xml1')
DLL_MARKER = b'XML2FIX.ANIMENUMS.1\0'
NO_ANIM = 'no_anim'                  # an ANIMTABLE value that maps an enum to no clip on purpose
X1_SHARED_ANIMS = 'data/shared_anims.xml'
X1_MOVESET_FLYING = 'data/fightstyles/moveset_flying.eng'
SHARED_ANIMS = 'Data/shared_anims'
MOVESET_FLYING = 'Data/fightstyles/moveset_flying'
COMMON_IGB = 'Actors/common.IGB'
X1_COMMON_IGB = 'actors/common.igb'

# Design 5.3: every FightMove of PC's and XML1's moveset_flying, with the side that wins and why. A node in neither
# column is an error (merge_moveset_flying refuses it), so a data change on either disc cannot slip through.
XML1, PC, PC_UNLESS_UPKEEP = 'xml1', 'pc', 'pc-unless-xml1-upkeep'
MOVESET_FLYING_PRECEDENCE = {
    **{n: (XML1, "XML1's flying carry graph, absent from PC; XML1's engine enters flyguarddecide by name (a string "
                 "default.xbe has and XMen2.exe lacks), so the carry handler port requests it")
       for n in ('flyguarddecide', 'airgrabpickup', 'airpickupidle', 'airpickupwalk', 'airpickuprun',
                 'airpickupthrow', 'airpickupsmash', 'fastball')},
    **{n: (PC, "equivalent node on both discs; PC's charge collision is already the restored rule-45 mask-4 behaviour")
       for n in ('jump', 'jumploop', 'flycharge', 'flycharge_loop', 'flycharge_end', 'flycharge_hit', 'flymelee1',
                 'flymelee2', 'painairfeetfirst')},
    'flying': (PC_UNLESS_UPKEEP, "PC's node carries energypersecond=\"%flight_pwr\"; XML1's has the flight skill "
                                 "requirement and relies on XML1's flight upkeep (default.xbe 0xdb0e0). Switching one "
                                 "without the other double-debits or never debits, so XML1's node only with the "
                                 "XML1 flight upkeep port (fix7) in the same build"),
}
# xml2-fix 1.9.0-beta.1 (rule 45 revision 3, beta8/carry 063f2e8) ports XML1's strict one-second flight upkeep and
# filters only the `%flight_pwr` energypersecond expression at the native parser (0x4f74b2), so XML1's `flying` node
# replaces PC's whenever --anim-enums xml1 is built (that DLL is required by the same gate: AnimEnums table + the
# rule 45 revision 3 marker, fix_ini.RELEASE_MARKERS). PC's flymelee1/2 and painairfeetfirst keep %flight_pwr; the
# DLL's filter clears it there too, so nothing is charged twice.
XML1_FLIGHT_UPKEEP = True


class AnimEnumError(ValueError):
    pass


def mode(ctx) -> str:
    """the build's --anim-enums value ('off' when the option is absent: a build from before it)."""
    return str(ctx.opt('anim_enums') or 'off')


# ------------------------------------------------------------------------------------------------ the DLL block
def dll_builtin_names(data: bytes):
    """the names of the DLL's marked AnimEnums block (DLL_MARKER, u16 count, count NUL-terminated names), or None
    when the DLL has no (readable) block."""
    i = data.find(DLL_MARKER)
    if i < 0:
        return None
    off = i + len(DLL_MARKER)
    if off + 2 > len(data):
        return None
    count = int.from_bytes(data[off:off + 2], 'little')
    off += 2
    names = []
    for _ in range(count):
        end = data.find(b'\0', off)
        if end < 0 or end - off > 63:
            return None
        names.append(data[off:end].decode('latin-1'))
        off = end + 1
    return tuple(names)


# ------------------------------------------------------------------------------------------------ shared_anims
def _anims(root):
    """the <anims> element of an ANIMTABLE (attribute name = enum, value = clip)."""
    if root is None or root.tag.lower() != 'animtable':
        raise AnimEnumError('not an ANIMTABLE')
    els = [c for c in root if c.tag.lower() == 'anims']
    if len(els) != 1:
        raise AnimEnumError(f'ANIMTABLE has {len(els)} <anims> elements, not 1')
    return els[0]


def table_entries(root) -> dict:
    """{lower enum name: clip} of an ANIMTABLE."""
    return {k.lower(): v for k, v in _anims(root).attrib.items()}


def merge_shared_anims(pc_root, x1_root):
    """(PC's ANIMTABLE + XML1's mappings of the 23 built-in enums, report). PC wins on a shared name; XML1's values are
    kept verbatim, the two clips XML1 lacks included; nothing else of XML1's is added (its ea_mission* stay PC's
    ea_zone*). Refuses a result above CAPACITY."""
    out = copy.deepcopy(pc_root)
    anims = _anims(out)
    pc = {k.lower() for k in anims.attrib}
    x1 = table_entries(x1_root)
    missing = [n for n in BUILTIN_ENUMS if n not in x1]
    if missing:
        raise AnimEnumError(f'XML1 shared_anims lacks {missing}')
    added, pc_won = [], []
    for n in BUILTIN_ENUMS:
        if n in pc:
            pc_won.append(n)
            continue
        anims.set(n, x1[n])
        added.append(n)
    total = len(anims.attrib)
    if total > CAPACITY:
        raise AnimEnumError(f'{total} ANIMTABLE entries > {CAPACITY}')
    return out, {'pc_entries': len(pc), 'added': added, 'pc_won': pc_won, 'entries': total,
                 'x1_only_not_added': sorted(set(x1) - pc - set(BUILTIN_ENUMS))}


# ------------------------------------------------------------------------------------------------ moveset_flying
def _moves(root):
    out = {}
    for c in root:
        if c.tag.lower() != 'fightmove':
            continue
        name = next((v for k, v in c.attrib.items() if k.lower() == 'name'), '').lower()
        if not name or name in out:
            raise AnimEnumError(f'FightMove without a unique name: {name!r}')
        out[name] = c
    return out


def merge_moveset_flying(pc_root, x1_root, *, xml1_flight_upkeep=XML1_FLIGHT_UPKEEP):
    """(PC's moveset_flying with XML1's carry nodes, report) by MOVESET_FLYING_PRECEDENCE. x1_root is XML1's file
    already converted like every XML1 style (x1schema + the style patch). PC's node order is kept, XML1's added
    nodes follow in XML1's order; `flying` is replaced in place only with xml1_flight_upkeep."""
    pc, x1 = _moves(pc_root), _moves(x1_root)
    unknown = sorted((set(pc) | set(x1)) - set(MOVESET_FLYING_PRECEDENCE))
    if unknown:
        raise AnimEnumError(f'moveset_flying nodes without a precedence entry: {unknown}')
    for n, (side, _why) in MOVESET_FLYING_PRECEDENCE.items():
        if side == XML1 and (n not in x1 or n in pc):
            raise AnimEnumError(f'{n}: precedence says XML1-only, found PC {n in pc} / XML1 {n in x1}')
        if side != XML1 and (n not in pc or n not in x1):
            raise AnimEnumError(f'{n}: precedence says on both discs, found PC {n in pc} / XML1 {n in x1}')
    out = copy.deepcopy(pc_root)
    report = {'kept_pc': [], 'added_xml1': [], 'replaced_by_xml1': []}
    for i, c in enumerate(list(out)):
        if c.tag.lower() != 'fightmove':
            continue
        n = next(v for k, v in c.attrib.items() if k.lower() == 'name').lower()
        if MOVESET_FLYING_PRECEDENCE[n][0] == PC_UNLESS_UPKEEP and xml1_flight_upkeep:
            out.remove(c)
            out.insert(i, copy.deepcopy(x1[n]))
            report['replaced_by_xml1'].append(n)
        else:
            report['kept_pc'].append(n)
    for n, c in x1.items():
        if MOVESET_FLYING_PRECEDENCE[n][0] == XML1:
            out.append(copy.deepcopy(c))
            report['added_xml1'].append(n)
    report['animenums'] = sorted({(v or '').strip().lower() for c in _moves(out).values()
                                  for k, v in c.attrib.items() if k.lower() == 'animenum'})
    return out, report


# ------------------------------------------------------------------------------------------------ the build step
def run(ctx, builder):
    """characters' step (after the styles): the three files of SPEC 107 when --anim-enums xml1, else nothing."""
    if mode(ctx) != 'xml1':
        return None
    from . import igb_anim_merge as IAM
    report = {}
    # 1. clips
    tgt, src = ctx.base_index.path(COMMON_IGB), ctx.x1_path(X1_COMMON_IGB)
    if tgt is None or src is None:
        ctx.error(f'--anim-enums xml1: {COMMON_IGB} (XML2) or {X1_COMMON_IGB} (XML1) missing')
        return None
    try:
        data, clips = IAM.transplant(tgt.read_bytes(), src.read_bytes())
    except IAM.IgbError as e:
        ctx.error(f'--anim-enums xml1: {COMMON_IGB}: the XML1 clips could not be transplanted ({e})')
        return None
    ctx.write_bytes(COMMON_IGB, data, source=str(src))
    report['clips'] = {k: v for k, v in clips.items() if k != 'per_clip'}
    ctx.note(f'{COMMON_IGB}: {len(clips["clips"])} XML1 clips transplanted from the XML1 disc ({clips["objects_added"]} '
             f'objects, {clips["blocks_added"]} memory blocks; animations {clips["animations_before"]} -> '
             f'{clips["animations_after"]}); absent in XML1 too, falling back to enum 0 as on XML1: '
             f'{sorted(IAM.KNOWN_ABSENT_IN_XML1)}')
    # 2. mappings
    try:
        x1_table = ctx.read_x1_xml(X1_SHARED_ANIMS)
        root, rep = merge_shared_anims(ctx.read_base_xmlb(SHARED_ANIMS + '.XMLB'), x1_table)
    except (KeyError, AnimEnumError) as e:
        ctx.error(f'--anim-enums xml1: {SHARED_ANIMS}: {e}')
        return None
    ctx.write_xmlb(SHARED_ANIMS, root, ('.XMLB',), source=f'characters:{X1_SHARED_ANIMS}')
    report['shared_anims'] = rep
    ctx.note(f'{SHARED_ANIMS}: {rep["pc_entries"]} PC entries + {len(rep["added"])} XML1 mappings = {rep["entries"]} '
             f'(capacity {CAPACITY}); PC kept on {rep["pc_won"] or "no"} shared names')
    # 3. flying carry nodes
    try:
        x1_moves = ctx.read_x1_xml(X1_MOVESET_FLYING)
    except KeyError as e:
        ctx.error(f'--anim-enums xml1: {e}')
        return None
    ctx.x1_schema(x1_moves, X1_MOVESET_FLYING)
    builder._style_patch(x1_moves, X1_MOVESET_FLYING)
    roots = {}
    try:
        for ext in ('.XMLB', '.engb'):
            roots[ext], rep = merge_moveset_flying(ctx.read_base_xmlb(MOVESET_FLYING + ext), x1_moves)
    except (KeyError, AnimEnumError) as e:
        ctx.error(f'--anim-enums xml1: {MOVESET_FLYING}: {e}')
        return None
    ctx.write_xmlb_pair(MOVESET_FLYING, roots['.XMLB'], roots['.engb'], source=f'characters:{X1_MOVESET_FLYING}')
    report['moveset_flying'] = rep
    ctx.note(f'{MOVESET_FLYING}: XML1 carry nodes added {rep["added_xml1"]}; PC kept {rep["kept_pc"]}'
             + (f'; XML1 replaced {rep["replaced_by_xml1"]}' if rep['replaced_by_xml1'] else '')
             + ' (anim_enums.MOVESET_FLYING_PRECEDENCE)')
    for k, v in (('anim_enums_clips_added', len(clips['clips'])), ('anim_enums_table_entries', report['shared_anims']['entries']),
                 ('anim_enums_carry_nodes_added', len(rep['added_xml1']))):
        ctx.set_count(k, v)
    ctx.write_meta('anim_enums.json', report)
    return report
