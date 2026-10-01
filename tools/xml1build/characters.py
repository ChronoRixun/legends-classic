"""xml1build.characters - XML1 characters in "XML1 mode" (tools/xml1build/SPEC.md section 5.1).

What run(ctx) produces (all through the ctx writers):
  * every XML1 character-namespace file, renamed collision-free (x1names / x1_namespace_map.json):
      - 182 numeric actors actors/CCVV.igb -> Actors/<CCVV+14000>.IGB with the in-IGB rename of '<id>',
        '<id>_outline' and '<id>_skel' (x1names.igb_rename; the empty actors/7501.igb is skipped);
      - the non-numeric anim DBs (21 clashing ones get 'x1_'; 'common', 'fightstyle_*', 'moveset_*' stay XML2's);
      - HUD heads, ui/hud/characters, ui/models/characters (+14000, in-IGB rename);
      - the 23 numeric loading screens xml1_assets/textures/loading/NNNN.igb -> Textures/loading/<+14000>.IGB;
      - the XML1 powerstyles (map_powerstyle; identical ps_def shared) and the 4 XML1-only fightstyles;
  * Data/npcstat.{XMLB,engb} in XML1 mode (each from its own XML2 base): the XML2 keep-list + every XML1 NPC +
    the XML1 heroes that zones use as NPCs (beast, frost, jubilee, magma, psylocke);
  * Data/shared_talents.{XMLB,engb} (ensure_talent for every talent the new entries reference, plus the NPC energy
    talent npc_values.ENERGY_TALENT that gives each converted entry XML1's energy pool, SPEC 24);
  * Data/values.XMLB (append the XML1 codes XML2 lacks);
  * Packages/generated/characters/<name>_<skin>[_nc].PKGB for every XML1 bundle of every written name (plus
    synthesized packages for zone monster_skin variants the XML1 disc has no bundle for) and <name>_xml;
  * Packages/generated/{powerstyles,fightstyles}/<mapped>.PKGB for every style written here;
  * Data/boltonactoranims.XMLB (append-only: XML1's cape/tail bolt-on anim maps; see MERGE_BOLTON_ANIMS).
Generic assets referenced by character/style bundles are brought in with ctx.import_x1_asset under the SPEC 4.4
policy, exactly as zones does: models/textures/effects are XML2-wins (shared, first importer owns them);
data/entities, conversations, dialogs, subtitles and motionpaths are XML1-wins (force) with their text patched
(map_tree_refs + the scripts provider rewrite_data_tree), so the output does not depend on module order.
Every asset the written styles and entity files name is then checked (check_style_refs); a file that is on the
XML1 disc but in no bundle is imported and appended to every package listing the referencing style/entity.

Provider: planned_stats(ctx) is pure and gives the full name plan (used by run(); other modules may call it when
characters did not run, e.g. --only zones).

The research prototype research/characters/build_chars.py (convert_stats, ensure_talent, pkg_entry,
build_packages, fix_package_for_boltons, copy_actor, copy_ui) is ported here as ctx-based code; it is not
imported (it runs argparse at import time). Deviations from the prototype, from XMen2.exe evidence: BoltOn
'onlyprecache' is kept (parsed at 0x44a868 with XML1's meaning) and weapon accessories use the valid slot
'ebolton_altweapon' (the prototype's 'ebolton_weapon2' is not in the slot table 0x6d6530, so XML2 dropped them).
"""
from __future__ import annotations

import collections
import concurrent.futures as _cf
import copy
import os
import re
import threading
import weakref
import xml.etree.ElementTree as ET
from pathlib import Path

from . import common as C
from . import combat_events as CE
from . import npc_values as NV       # SPEC 24: XML1 value codes in the styles, the NPC energy pool
from . import weapons as W           # SPEC 29: XML1 weapon definitions as style triggers (variant styles)
from . import scripts_transform as ST
from .lib import x1names as N   # the XML1 namespace (was research/characters/x1names.py)

# ------------------------------------------------------------------------------------------------ constants
# XML2 npcstat entries kept in XML1 mode (build_chars --keep-x2 default): the 4 main-character placeholders
# plus the 16 npcstat names that appear as strings in XMen2.exe (research/characters/x2_stats_refs.json
# in_exe). XML1 entries of the same name replace them (beast, forge, profx).
KEEP_X2 = ('_hero1_mc_', '_hero2_mc_', '_hero3_mc_', '_hero4_mc_', 'abyss', 'apocdummy', 'archangel', 'bastion',
           'beast', 'forge', 'garokk', 'holocaust', 'menu', 'mikhail', 'omegared', 'profx', 'sauron', 'scarabapoc',
           'stryfe', 'sugarman')
STATS_CAP = 296          # XMen2.exe 0x44c1a7 cmp count,0x129 (herostat + npcstat unique names)
HERO_COUNT = 21          # 0x44bb13 cmp esi,0x15 (hero index mapping)
TALENT_CAP = 99          # 0x4c05d0 shared talent ids 0..98
NAME_MAX = 31            # stats name strncpy 0x20 incl. NUL
# XML1-only stats attributes XML2's parser does not handle (schema_stats.txt 'handled=NO')
DROP_ATTRS = {'leader', 'ratingmelee', 'ratingranged', 'ratingsupport', 'ratingdurability', 'throwally'}
# costume names XML2 knows (table 0x6d8aa0); other skin_<x> attributes are dropped
COSTUMES_X2 = {'astonishing', 'aoa', '60s', '70s', 'weaponx', 'future', 'winter', 'civilian'}
XML2_TAG = {'talent': 'talent', 'race': 'Race', 'bolton': 'BoltOn', 'multipart': 'Multipart', 'flyeffect': 'FlyEffect'}
# XMen2.exe BoltOn slot table at 0x6d6530 (name -> attach index 0..5), looked up with _stricmp by 0x5602f0
BOLTON_SLOTS = {'ebolton_clawright': 0, 'ebolton_clawleft': 1, 'ebolton_weapon': 0, 'ebolton_altweapon': 1,
                'ebolton_cape': 2, 'ebolton_tail': 2, 'ebolton_wings': 2, 'ebolton_tongue': 3,
                'ebolton_autoanim': 4, 'ebolton_autoanim2': 5}
# XML1 Multipart attributes XMen2.exe's Multipart parser (0x48ce80: bone, NonMenuOnly, hideSkin[%d],
# showSkin[%d]) does not read: kept in the data (harmless), but XML2 ignores them
MULTIPART_X1_ONLY = ('effectondeath', 'linktopower', 'starthide', 'healthmul', 'loopeffect', 'effectbone')
# Append XML1's bolt-on actor anim mappings (data/boltonactoranims: 99_cape, 98_tail) to XML2's table under the
# mapped anim DB names, so the XML1 capes / tails (MagnetoBoss/Act2/Scripted, nightcrawler NPCs) follow the
# wearer's animations. Append-only (XML2 entries win). Not in SPEC 5.1 (which lists boltonactoranims as
# "XML2's kept"); set False to leave the XML2 file untouched.
MERGE_BOLTON_ANIMS = True
# SPEC 4.4: XML1 wins (force=True, text patched) for these prefixes, exactly as zones imports them
# (zones.FORCE_PREFIXES); a character/style bundle listing such a file imports it the same way so the result
# does not depend on which module imports it first (or whether zones runs at all).
FORCE_PREFIXES = ('conversations/', 'dialogs/', 'subtitles/', 'data/entities/', 'motionpaths/')
PATCH_DATA = 'characters.data'      # import_x1_asset patch key: map_tree_refs + scripts.rewrite_data_tree
PATCH_STYLE = 'characters.style'    # import_x1_asset patch key: map_tree_refs (+ rewrite_data_tree) on styles
# style attributes that name an effect (relative to effects/), checked by _Builder.check_style_refs
_STYLE_EFFECT_ATTR = re.compile(r'(?:effect|effect_cust\d|footstepfx)$')
# attribute names that can carry a character (stats) name in XML2 data (keep-list scan)
_CHAR_ATTR = re.compile(r'char|monster|spawn|summon|npc|actor')
_SKIN4 = re.compile(r'\d{4}')
_UI_CHAR = re.compile(r'(hud/hud_head_|ui/hud/characters/|ui/models/characters/)(\d{4})\.igb')
_BUNDLE = re.compile(r'packages/generated/characters/(.+)_(\d{4})(_nc)?\.fb')
_NS_DIRS = {'hud/hud_head_': 'HUD/hud_head_', 'ui/hud/characters/': 'UI/HUD/characters/',
            'ui/models/characters/': 'UI/models/characters/'}


def _lower_attrs(el):
    return {k.lower(): v for k, v in el.attrib.items()}


_REWRITE_LOCK = threading.Lock()
_REWRITE_FN = weakref.WeakKeyDictionary()     # ctx -> safe wrapper of scripts.rewrite_data_tree, or None


def _rewrite_data_tree_fn(ctx):
    """A wrapper of scripts.rewrite_data_tree (a pure SPEC 5.0 provider, usable before scripts.run), or None.
    The characters step must never fail because of another module: if scripts.py cannot be imported (any
    exception, e.g. a SyntaxError while it is being edited) or the provider raises, one warning is logged and
    the data is patched with map_tree_refs only. Nothing characters imports has script content today."""
    with _REWRITE_LOCK:
        if ctx not in _REWRITE_FN:
            fn, why = None, 'scripts.rewrite_data_tree is not defined'
            try:
                from . import scripts as S
                fn = getattr(S, 'rewrite_data_tree', None)
                fn = fn if callable(fn) else None
            except Exception as e:  # noqa: BLE001 - another module's bug must not fail this step
                why = f'scripts module not importable ({type(e).__name__}: {e})'
            if fn is None:
                ctx.warn(f'{why}: XML1 data imported by characters (data/entities, styles) is patched with '
                         f'map_tree_refs only')
                _REWRITE_FN[ctx] = None
            else:
                failed = []

                def safe(c, root, rel, fn=fn):
                    try:
                        return fn(c, root, rel)
                    except Exception as e:  # noqa: BLE001
                        if not failed:
                            failed.append(e)
                            ctx.warn(f'scripts.rewrite_data_tree raised {type(e).__name__}: {e} (on {rel}); '
                                     f'characters data is patched with map_tree_refs only where it fails')
                        return 0
                _REWRITE_FN[ctx] = safe
        return _REWRITE_FN[ctx]


def _stats_list(root):
    return [s for s in root.iter() if s.tag.lower() == 'stats' and s.get('name')]


_MISSION_ANIM = re.compile(rb'(?<![A-Za-z0-9_])mission(\d{1,2})\x00')


def mission_anim_names(data):
    """sorted 'missionN' anim names (1 <= N <= 20) stored as IGB string fields (u32 padded length prefix)."""
    import struct
    found = set()
    for m in _MISSION_ANIM.finditer(data):
        s = m.start()
        n = int(m.group(1))
        if s < 4 or not 1 <= n <= ST.MISSION_ANIM_MAX:
            continue
        (plen,) = struct.unpack_from('<I', data, s - 4)
        body = len(m.group(0)) - 1
        if plen % 4 == 0 and body + 1 <= plen <= body + 4:
            found.add(f'mission{n}')
    return sorted(found, key=lambda x: int(x[7:]))


def rename_mission_anims_igb(data):
    """XML1 mission / briefing anims 'missionN' -> XML2's 'zoneN' inside an anim DB IGB (XML1 EA_MISSIONn ->
    'missionN' vs XMen2.exe EA_ZONEn -> 'zoneN', Data/shared_anims.XMLB). The name is shorter, so it fits the
    string field's padding (x1names.igb_rename, in place). Returns (data, renamed, problems)."""
    import struct
    names = set(mission_anim_names(data))
    buf = bytearray(data)
    total, problems = 0, []
    for m in _MISSION_ANIM.finditer(data):
        s = m.start()
        old = m.group(0)[:-1].decode()
        if old not in names or s < 4:
            continue
        (plen,) = struct.unpack_from('<I', data, s - 4)
        if plen % 4 or not len(old) + 1 <= plen <= len(old) + 4:
            continue                                   # not a length-prefixed string field
        repl = ('zone' + old[len('mission'):]).encode()
        buf[s:s + plen] = repl + b'\x00' * (plen - len(repl))   # shorter: fits the field, no offset moves
        total += 1
    data = bytes(buf)
    left = mission_anim_names(data)
    if left:
        problems.append(('left', left))
    return data, total, problems


# ------------------------------------------------------------------------------------------------ provider
_PLAN_LOCK = threading.Lock()


def planned_stats(ctx):
    """Pure (no writes; cached in ctx.shared['_characters_plan']): the XML1-mode stats name plan, the single
    source of truth run() builds npcstat from. Usable when characters.run did not execute (--only zones).

    {'x1_npcs': [Name...]              XML1 npcstat names added (those equal to an XML2 herostat name excluded),
     'covered': [Name...]              XML1 npcstat/herostat names covered by an XML2 herostat stand-in,
     'heroes_as_npc': [Name...]        XML1 herostat names not in XML2 herostat that a zone .chr / zone spawner
                                       uses, or that live content looks up by name (conversation speaker %NAME%,
                                       unlockCharacter / setInCampaign literals: _x1_hero_name_refs),
     'hero_refs': {lower: [where]}     evidence for heroes_as_npc,
     'keep_x2': [lower...]             XML2 npcstat entries kept (KEEP_X2 + exe evidence + scan), minus XML1 names,
     'keep_evidence': set, 'keep_need': {lower: [where]}, 'keep_scanned': int,
     'herostat': [Name...], 'names': set(lower herostat + npcstat),
     'zone_monster_skins': {lower name: {4-digit XML1 skin}}  (zone entities with character + monster_skin)}"""
    with _PLAN_LOCK:
        p = ctx.shared.get('_characters_plan')
        if p is not None:
            return p
        x1npc = _stats_list(ctx.read_x1_xml('data/npcstat.eng'))
        x1hero = _stats_list(ctx.read_x1_xml('data/herostat.eng'))
        hero_root = ctx.read_base_xmlb('Data/herostat.engb')
        x2hero = [s.get('name') for s in hero_root.iter('stats')]
        x2hero_xmlb = [s.get('name') for s in ctx.read_base_xmlb('Data/herostat.XMLB').iter('stats')]
        x2npc = {s.get('name').lower(): s.get('name') for s in ctx.read_base_xmlb('Data/npcstat.engb').iter('stats')}
        h2 = {n.lower() for n in x2hero} | {n.lower() for n in x2hero_xmlb}
        zrefs = _x1_zone_char_refs(ctx)
        srefs = _x1_hero_name_refs(ctx, {s.get('name').lower() for s in x1hero} - h2)
        hero_refs = {}
        for s in x1hero:
            ln = s.get('name').lower()
            if ln in h2:
                continue
            where = sorted(zrefs['chr'].get(ln, ())) + sorted(zrefs['spawn'].get(ln, ())) + \
                sorted(srefs.get(ln, ()))
            if where:
                hero_refs[ln] = where
        heroes = [s.get('name') for s in x1hero if s.get('name').lower() in hero_refs]
        x1_npcs = [s.get('name') for s in x1npc if s.get('name').lower() not in h2]
        covered = sorted({s.get('name') for s in x1npc + x1hero if s.get('name').lower() in h2}, key=str.lower)
        x1names_l = {n.lower() for n in x1_npcs} | {h.lower() for h in heroes}
        # keep list: KEEP_X2 (build_chars --keep-x2 default) U exe-string evidence U names still-active XML2
        # content refers to (front-end zones, XML2 heroes' powers/packages, world tables, permanent package)
        refs = ctx.research_json('characters/x2_stats_refs.json')
        evidence = {o['name'].lower() for o in refs if o['file'] == 'npcstat' and
                    (o['in_exe'] or re.fullmatch(r'_hero\d_mc_', o['name'].lower()))}
        need, scanned = _scan_keep_needs(ctx, set(x2npc), hero_root)
        keep_all = set(KEEP_X2) | evidence | set(need)
        keep = [n for n in x2npc if n in keep_all and n not in x1names_l]
        p = {'x1_npcs': x1_npcs, 'covered': covered, 'heroes_as_npc': heroes, 'hero_refs': hero_refs,
             'keep_x2': keep, 'keep_evidence': evidence, 'keep_need': need, 'keep_scanned': scanned,
             'herostat': x2hero, 'names': {n.lower() for n in x2hero} | set(keep) | x1names_l,
             'zone_monster_skins': zrefs['monster_skins'], 'zone_parse_errors': zrefs['errors']}
        ctx.shared['_characters_plan'] = p
        return p


_HERO_NAME_FUNCS = ('unlockCharacter', 'setInCampaign')


def _x1_hero_name_refs(ctx, names):
    """{lower hero name: {where}} for the XML1 herostat names (not XML2 heroes) that live content looks up in the
    stats table by name besides zone spawns: conversation speaker tokens %NAME% (XML1 conversations, English /
    neutral files) and unlockCharacter / setInCampaign literals (the installed research scripts and the inline
    rewrite values). A name missing from the stats table resolves to index 0 on a miss (XMen2.exe 0x44acc0 ->
    0x44ad7e xor ax,ax), so a speaker line loses its name/portrait and an unlock touches the unused slot 0."""
    out = {}
    if not names:
        return out
    alt = '|'.join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    tok = re.compile(r'(?i)%(' + alt + r')%')
    call = re.compile(r'(?i)\b(' + '|'.join(_HERO_NAME_FUNCS) + r')\s*\(\s*["\'](' + alt + r')["\']')
    for rel in ctx.x1_rels('conversations/'):
        if not rel.endswith(('.eng', '.xml')):
            continue
        raw = ctx.x1_path(rel).read_bytes().decode('latin-1')
        for m in tok.finditer(raw):
            out.setdefault(m.group(1).lower(), set()).add(f'{rel}: speaker %{m.group(1)}%')
    sroot = ctx.research_path('scripts/out/scripts')
    if sroot.is_dir():
        for p in sroot.rglob('*.py'):
            text = p.read_bytes().decode('latin-1')
            for m in call.finditer(text):
                out.setdefault(m.group(2).lower(), set()).add(
                    f'scripts/{p.relative_to(sroot).as_posix()}: {m.group(1)}')
    try:
        inline = ctx.research_json('scripts/out/inline_rewrites.json')
    except FileNotFoundError:
        inline = {}
    for v in inline.values():
        for m in call.finditer(v):
            out.setdefault(m.group(2).lower(), set()).add(f'inline data: {m.group(1)}')
    return out


def _x1_zone_char_refs(ctx):
    """Character references of the XML1 zones: {'chr': {lower name: {zone .chr rels}}, 'spawn': {lower name:
    {zone xml rels}} (entities with character=...), 'monster_skins': {lower name: {4-digit skin}}, 'errors': []}.
    Empty .chr / zone files list nothing."""
    out = {'chr': {}, 'spawn': {}, 'monster_skins': {}, 'errors': []}
    for rel in ctx.x1_rels('maps/'):
        ext = C.split_ext(rel)[1]
        if ext not in ('.chr', '.eng', '.xml'):
            continue
        try:
            root = ctx.read_x1_xml(rel)
        except Exception as e:  # noqa: BLE001 - a broken zone file is the zones module's error to report
            out['errors'].append(f'{rel}: {type(e).__name__}: {e}')
            continue
        if root is None:
            continue
        for el in root.iter():
            if ext == '.chr':
                if el.tag.lower() == 'character' and el.get('name'):
                    out['chr'].setdefault(el.get('name').strip().lower(), set()).add(rel)
                continue
            ch = (el.get('character') or '').strip()
            if not ch:
                continue
            out['spawn'].setdefault(ch.lower(), set()).add(rel)
            ms = (el.get('monster_skin') or '').strip()
            if _SKIN4.fullmatch(ms):
                out['monster_skins'].setdefault(ch.lower(), set()).add(ms)
    return out


# ------------------------------------------------------------------------------------------------ builder
class _Builder:
    def __init__(self, ctx):
        self.ctx = ctx
        self.lock = threading.RLock()
        self.detail = {'written': {}, 'dropped_attrs': [], 'dropped_children': [], 'dropped_pkg_entries': [],
                       'kept_xml2_assets': [], 'talents_added': [], 'sounddir_dropped': [], 'x2_dropped': [],
                       'x2_kept': [], 'packages': [], 'synth_packages': [], 'notes': []}
        self.actor_new = {}         # XML1 actor stem (lower) -> mapped stem written/used (or None if skipped)
        self.actor_empty = set()    # XML1 actor stems with 0-byte sources (7501)
        self.ui_new = {}            # 'hud/hud_head_1801' -> 'hud/hud_head_15801' (package form)
        self.styles = {}            # ('powerstyles'|'fightstyles', lower x1 name) -> mapped name (exists)
        self.styles_written = {}    # (kind, mapped lower) -> x1 rel
        self.npc_powerups = {}      # x1 style rel -> (Counter, report) of heroes.convert_npc_powerups (SPEC 22.7)
        self.x1_values = None       # heroes.Values of XML1's data/values.xml (loaded on the first style)
        self.npc_codes = {}         # x1 style rel -> (Counter, problems) of npc_values.resolve_style (SPEC 24)
        self.weapon_reports = {}    # variant style name -> (weapon, x1 style, weapons.apply counts) (SPEC 29)
        self.variant_base = {}      # weapon variant style name -> the mapped base style it replaces (SPEC 29.1)
        self.igb_renamed = 0
        self.import_stats = {}
        self.x1_weapons = {}
        self.talent_names = set()
        self.talent_roots = ()
        self.x1_talents = {}
        self.dep_extra = {}         # style/entity package filename -> [(kind, filename)] it needs in addition
        self.pending = {}           # staged packages: norm rel -> (rel, root, source)

    # ---------------------------------------------------------------- helpers
    def exists(self, rel):
        """rel exists in the final tree: a base-install file or a file registered this build."""
        return rel in self.ctx.base_index or rel in self.ctx.registry

    def pkg_entry_exists(self, kind, filename):
        cands = C.package_entry_files(kind, filename)
        return True if cands is None else any(self.exists(c) for c in cands)

    def _record(self, cat, x1_rel, out_rels):
        with self.lock:
            self.detail['written'].setdefault(cat, []).append([x1_rel, out_rels])

    # ---------------------------------------------------------------- 1. namespace files
    def _base_collision(self, dst_rel, src_rel, prefix):
        """dst exists in the base install: identical (by research collisions) -> share; else error."""
        stem = Path(src_rel).stem.lower()
        if stem in N._identical(prefix):
            return 'shared'
        self.ctx.error(f'{src_rel}: mapped destination {dst_rel} exists in XML2 with different content '
                       f'(namespace map check_errors should be empty)')
        return 'error'

    def _igb_job(self, src_rel, dst_rel, old, new):
        """read + in-IGB rename (pure, thread-safe); returns (data, n, problems)."""
        data = self.ctx.x1_path(src_rel).read_bytes()
        if old == new:
            return data, 0, []
        return N.igb_rename(data, old, new)

    def emit_namespace(self):
        ctx = self.ctx
        jobs = []          # (category, src_rel, dst_rel, old, new)
        copies = []        # (category, src_rel, dst_rel)
        # numeric actors + anim DBs
        for rel in ctx.x1_rels('actors/'):
            stem, ext = C.split_ext(rel[len('actors/'):])
            if ext != '.igb':
                continue
            if ctx.x1_is_empty(rel):
                self.actor_empty.add(stem)
                self.actor_new[stem] = None
                ctx.note(f'{rel}: 0-byte XML1 file, not written; package entries naming it are left out'
                         + (' (npcstat Computer skin 7501 -> 21501: stats entry kept, no actor, allowlisted '
                            'for validate)' if stem == '7501' else ''))
                ctx.count('actors_empty_skipped')
                continue
            if _SKIN4.fullmatch(stem):
                new = C.map_skin(stem)
                dst = f'Actors/{new}.IGB'
                self.actor_new[stem] = new
                if dst in ctx.base_index:
                    self._base_collision(dst, rel, 'actors/')
                    continue
                jobs.append(('skins', rel, dst, stem, new))
            else:
                if N.shares_xml2_animdb(stem):
                    self.actor_new[stem] = stem
                    if f'actors/{stem}.igb' in ctx.base_index:
                        ctx.count('animdb_shared_xml2')
                        continue
                    # an XML1 fightstyle/moveset anim DB XML2 does not ship: bring it in under its own name
                    copies.append(('animdbs', rel, f'Actors/{stem}.IGB'))
                    continue
                new = C.map_animdb(stem)
                self.actor_new[stem] = new
                dst = f'Actors/{new}.IGB'
                if dst in ctx.base_index:
                    self._base_collision(dst, rel, 'actors/')
                    continue
                copies.append(('animdbs', rel, dst))
        # HUD heads / UI character models
        for pre, out_pre in _NS_DIRS.items():
            for rel in ctx.x1_rels(pre):
                m = _UI_CHAR.fullmatch(rel)
                if not m or m.group(1) != pre:
                    ctx.warn(f'{rel}: unexpected non-numeric character UI file, not converted')
                    continue
                old = m.group(2)
                new = C.map_skin(old)
                self.ui_new[f'{pre}{old}'] = f'{pre}{new}'
                if ctx.x1_is_empty(rel):
                    ctx.warn(f'{rel}: 0-byte XML1 file, not written')
                    self.ui_new[f'{pre}{old}'] = None
                    continue
                dst = f'{out_pre}{new}.IGB'
                if dst in ctx.base_index:
                    self._base_collision(dst, rel, pre.rstrip('_').rsplit('/', 1)[0] + '/')
                    continue
                cat = {'hud/hud_head_': 'hud_heads', 'ui/hud/characters/': 'ui_hud',
                       'ui/models/characters/': 'ui_models'}[pre]
                jobs.append((cat, rel, dst, old, new))
        # numeric loading screens (engine: textures/loading/%02d%02d from the skin prefix byte, 0x487258)
        for rel in ctx.x1_rels('textures/loading/'):
            stem, ext = C.split_ext(rel[len('textures/loading/'):])
            if ext != '.igb' or not _SKIN4.fullmatch(stem):
                continue
            dst = f'Textures/loading/{C.map_skin(stem)}.IGB'
            if dst in ctx.base_index:
                self._base_collision(dst, rel, 'textures/loading/')
                continue
            copies.append(('loading', rel, dst))

        # renamed IGBs: read + rename in threads, write through the (locked) ctx writer; recorded afterwards in job
        # order, so characters_detail.json does not depend on thread timing (a build is reproducible file for file)
        def run_job(j):
            cat, src_rel, dst, old, new = j
            data, n, problems = self._igb_job(src_rel, dst, old, new)
            if problems:
                ctx.error(f'{src_rel} -> {dst}: {len(problems)} in-IGB names do not fit: {problems[:3]}')
            actual = ctx.write_bytes(dst, data, source=ctx.x1_path(src_rel))
            with self.lock:
                self.igb_renamed += n
            return cat, src_rel, actual

        workers = max(1, int(ctx.opt('jobs', 1) or 1))
        with _cf.ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(run_job, jobs))
        done = []
        for cat, src_rel, actual in results:
            self._record(cat, src_rel, [actual])
            done.append(cat)
        mission_dbs = {}
        for cat, src_rel, dst in copies:
            src = ctx.x1_path(src_rel)
            if cat == 'animdbs':
                data = src.read_bytes()
                if mission_anim_names(data):
                    # XML1 EA_MISSIONn anims -> XML2 EA_ZONEn names (scripts / data enums are renamed to match)
                    new, n, problems = rename_mission_anims_igb(data)
                    if problems:
                        ctx.error(f'{src_rel} -> {dst}: mission anim rename incomplete: {problems[:3]}')
                    actual = ctx.write_bytes(dst, new, source=src)
                    mission_dbs[src_rel] = n
                    self._record(cat, src_rel, [actual])
                    done.append(cat)
                    continue
            actual = ctx.copy_file(src, dst)
            self._record(cat, src_rel, [actual])
            done.append(cat)
        ctx.set_count('mission_anim_dbs_renamed', len(mission_dbs))
        ctx.set_count('mission_anims_renamed', sum(mission_dbs.values()))
        if mission_dbs:
            ctx.note(f'{sum(mission_dbs.values())} XML1 "missionN" anims in {len(mission_dbs)} anim DBs renamed to '
                     f'"zoneN" (XMen2.exe plays them as EA_ZONEn; it has no ea_mission* enum): '
                     f'{sorted(Path(r).stem for r in mission_dbs)}')
        for cat in ('skins', 'animdbs', 'hud_heads', 'ui_hud', 'ui_models', 'loading'):
            ctx.set_count(f'{cat}_written', done.count(cat))
        ctx.set_count('actors_written', done.count('skins') + done.count('animdbs'))
        ctx.set_count('igb_names_renamed', self.igb_renamed)
        ctx.log(f"namespace files: {done.count('skins')} skins, {done.count('animdbs')} anim DBs, "
                f"{done.count('hud_heads')} HUD heads, {done.count('ui_hud')}+{done.count('ui_models')} UI, "
                f"{done.count('loading')} loading screens, {self.igb_renamed} in-IGB names renamed")

    # ---------------------------------------------------------------- styles
    def _style_patch(self, root, rel=''):
        # trigger skin/actorskin (ps_toad 2605/9601 ...) and any actors/ paths; script references / inline code
        # through the scripts provider (none in the XML1 styles today, kept for consistency with zones' data)
        C.map_tree_refs(root)
        rewrite = _rewrite_data_tree_fn(self.ctx)
        if rewrite is not None:
            rewrite(self.ctx, root, rel)
        # SPEC 22.7: XML1-form powerup triggers (powerup= / remove="true") -> XML2's <affecter> / remove_tag form,
        # the heroes' converter plus the NPC-only forms; XML1's value codes resolved (NPC balance stays XML1's)
        from . import heroes as H                  # noqa: WPS433 - heroes imports characters lazily too
        with self.lock:
            if self.x1_values is None:
                self.x1_values = H.Values(self.ctx.read_x1_xml('data/values.xml'))
        where = f'{C.split_ext(C.norm(rel))[0].rsplit("/", 1)[-1]}:'
        changes, rep = H.convert_npc_powerups(root, self.x1_values, where)
        # SPEC 24: every other XML1 value code (damage L/M/H ranges, knockback K, powerusage P ...) -> XML1's
        # number(s); XMen2.exe reads any code but DMG2/3/4, K2, K3 as 0 (npc_values)
        codes = NV.resolve_style(root, self.x1_values, where)
        with self.lock:
            self.npc_powerups[C.norm(rel)] = (changes, rep)
            self.npc_codes[C.norm(rel)] = codes

    def emit_styles(self):
        """every XML1 powerstyle (map_powerstyle) and the XML1-only fightstyles."""
        ctx = self.ctx
        for kind in ('powerstyles', 'fightstyles'):
            seen = {}
            for rel in ctx.x1_rels(f'data/{kind}/'):
                stem, ext = C.split_ext(rel[len(f'data/{kind}/'):])
                if ext in ('.eng', '.xml'):
                    if stem in seen:
                        ctx.warn(f'data/{kind}/{stem}: both .eng and .xml on the disc; using {seen[stem]}')
                        continue
                    seen[stem] = rel
            for stem, rel in sorted(seen.items()):
                self.style(kind, stem, rel)
        ctx.set_count('powerstyles_written', sum(1 for k in self.styles_written if k[0] == 'powerstyles'))
        ctx.set_count('fightstyles_written', sum(1 for k in self.styles_written if k[0] == 'fightstyles'))

    def style(self, kind, name, rel=None):
        """make sure data/<kind>/<mapped name> exists (XML2's or converted from XML1); returns the mapped name
        or None when it exists nowhere."""
        key = (kind, name.lower())
        with self.lock:
            if key in self.styles:
                return self.styles[key]
            if key in self.styles_written:          # an already-mapped name (e.g. 'x1_ps_beast')
                return name.lower()
        ctx = self.ctx
        lname = name.lower()
        mapped = C.map_powerstyle(lname) if kind == 'powerstyles' else C.map_fightstyle(lname)
        base_has = ctx.base_index.find(f'data/{kind}/{mapped}', ('.xmlb', '.engb')) is not None
        if rel is None:
            rel = next((r for r in (f'data/{kind}/{lname}.eng', f'data/{kind}/{lname}.xml') if ctx.x1_path(r)), None)
        result = mapped
        if base_has:
            # XML2 has the mapped name: identical (ps_def) or an intentionally shared fightstyle -> XML2's file
            if kind == 'powerstyles' and mapped == lname and lname not in N._identical('data/powerstyles/'):
                ctx.error(f'data/powerstyles/{lname}: collides with XML2 but is not renamed')
            ctx.count(f'{kind}_shared_xml2')
        elif rel is None:
            ctx.error(f'data/{kind}/{name}: referenced but exists neither in XML2 nor on the XML1 disc')
            result = None
        elif ctx.x1_is_empty(rel):
            ctx.error(f'{rel}: 0-byte XML1 style file')
            result = None
        else:
            res = ctx.import_x1_asset(rel, out_rel_noext=f'Data/{kind}/{mapped}',
                                      patch=lambda root, r=rel: self._style_patch(root, r), patch_key=PATCH_STYLE)
            if not res.ok:
                ctx.error(f'{rel}: style import failed ({res.status})')
                result = None
            else:
                with self.lock:
                    self.styles_written[(kind, mapped)] = rel
                self._record(kind, rel, res.out_rels)
        with self.lock:
            self.styles[key] = result
        return result

    def weapon_style(self, x1_style, weapon, weapon_name):
        """SPEC 29: the variant of XML1 powerstyle `x1_style` armed with `weapon` (a data/weapons/weapons.eng
        entry): data/powerstyles/x1_<style>_<weapon>, the XML1 style with its weapon_fire triggers replaced by
        the weapon's own (weapons.apply) and then patched like every style (value codes resolved). Returns the
        variant's name, or None when the XML1 style does not exist."""
        ctx = self.ctx
        lname = x1_style.lower()
        mapped = C.map_powerstyle(lname)
        name = W.variant_name(mapped, weapon_name)
        key = ('powerstyles', name)
        with self.lock:
            self.variant_base[name] = mapped.lower()
            if key in self.styles:
                return self.styles[key]
        rel = next((r for r in (f'data/powerstyles/{lname}.eng', f'data/powerstyles/{lname}.xml') if ctx.x1_path(r)),
                   None)
        result = name
        if rel is None or ctx.x1_is_empty(rel):
            ctx.error(f'data/powerstyles/{x1_style}: weapon {weapon_name} needs it but the XML1 disc has no '
                      f'usable copy')
            result = None
        else:
            def patch(root, r=rel, w=weapon, nm=name):
                rep = W.apply(root, w, where=nm)
                with self.lock:
                    self.weapon_reports[nm] = (weapon_name, lname, dict(rep))
                self._style_patch(root, r)
            res = ctx.import_x1_asset(rel, out_rel_noext=f'Data/powerstyles/{name}', patch=patch,
                                      patch_key=f'{PATCH_STYLE}.weapon.{weapon_name.lower()}')
            if not res.ok:
                ctx.error(f'{rel}: weapon variant {name} import failed ({res.status})')
                result = None
            else:
                with self.lock:
                    self.styles_written[('powerstyles', name)] = rel
                self._record('powerstyles', rel, res.out_rels)
                ctx.count('weapon_styles_written')
        with self.lock:
            self.styles[key] = result
        return result

    # ---------------------------------------------------------------- talents
    def load_talents(self):
        ctx = self.ctx
        self.talent_roots = (ctx.read_base_xmlb('Data/shared_talents.XMLB'),
                             ctx.read_base_xmlb('Data/shared_talents.engb'))
        names = [set(t.get('name', '').lower() for t in r.iter('talent')) for r in self.talent_roots]
        if names[0] != names[1]:
            ctx.warn(f'XML2 shared_talents XMLB/engb list different names: {sorted(names[0] ^ names[1])}')
        self.talent_names = names[0] | names[1]
        self.base_talent_count = len(names[1])
        x1 = ctx.read_x1_xml('data/shared_talents.eng')
        self.x1_talents = {t.get('name', '').lower(): t for t in x1.iter() if t.tag.lower() == 'talent'}

    def ensure_talent(self, name, fightstyle, who):
        """XML2 resolves a stats <talent> by name among registered talents (0x4c05b0); add an empty shared
        definition (as build_chars.ensure_talent) for XML1 talents XML2 lacks, in both XMLB and engb."""
        ln = name.lower()
        with self.lock:
            if ln in self.talent_names:
                return
            self.talent_names.add(ln)
            t = ET.Element('talent', {'name': name})
            if fightstyle:
                t.set('fightstyle', 'true')
            ET.SubElement(t, 'level')
            for root in self.talent_roots:
                root.append(copy.deepcopy(t))
            self.detail['talents_added'].append([name, who])

    # ---------------------------------------------------------------- stats conversion
    def load_weapons(self):
        root = self.ctx.read_x1_xml('data/weapons/weapons.eng')
        self.x1_weapons = {w.get('name').lower(): _lower_attrs(w)
                           for w in root.iter() if w.tag.lower() == 'weapon' and w.get('name')}

    def _asset(self, rel, why):
        """import a generic XML1 asset (model/effect/texture/entity) under the SPEC 4.4 collision policy, the
        same way zones does: conversations/dialogs/subtitles/data/entities/motionpaths are XML1-wins (force) and
        their text is patched (map_tree_refs + scripts.rewrite_data_tree); everything else is XML2-wins and
        unpatched (shared and cacheable with other modules' imports). Returns an ImportResult."""
        ctx = self.ctx
        n = C.norm(rel)
        stem, ext = C.split_ext(n)
        if n.startswith(FORCE_PREFIXES):
            exts = C.TEXT_OUT.get(ext) or ('.IGB' if ext == '.igb' else ext,)
            prior = [ctx.registry.get(stem + e) for e in exts]
            src = ctx.x1_path(n)
            if src is not None and all(prior) and all(p['owner'] != ctx.module for p in prior) \
                    and all(p['source'] == str(src) for p in prior):
                # another module (zones, carried over with --only) already wrote it XML1-wins from this source
                res = C.ImportResult(n, 'written', stem, [p['rel'] for p in prior])
            elif ext in C.TEXT_OUT:
                res = ctx.import_x1_asset(n, force=True, patch=self._data_patch(n), patch_key=PATCH_DATA)
            else:
                res = ctx.import_x1_asset(n, force=True)
            if res.ok:
                ctx.count('assets_xml1_wins')
        else:
            res = ctx.import_x1_asset(n)
        with self.lock:
            self.import_stats.setdefault(res.status, set()).add(n)
        if res.status in ('missing', 'empty'):
            ctx.warn(f'{why}: {rel} is {res.status} on the XML1 disc')
        return res

    def _data_patch(self, n):
        rewrite = _rewrite_data_tree_fn(self.ctx)

        def patch(root, n=n):
            C.map_tree_refs(root)
            if rewrite is not None:
                rewrite(self.ctx, root, n)
            if n.startswith('data/entities/'):
                # SPEC 29 / 24: a projectile entity's damage / knockback codes (ice_bullet L3, bullet_time K10)
                # read as 0 on XMen2.exe like a style's; resolved to XML1's numbers the same way
                from . import heroes as H
                with self.lock:
                    if self.x1_values is None:
                        self.x1_values = H.Values(self.ctx.read_x1_xml('data/values.xml'))
                codes = NV.resolve_style(root, self.x1_values, f'{n.rsplit("/", 1)[-1]}:')
                with self.lock:
                    self.npc_codes[C.norm(n)] = codes
        return patch

    def _model_ok(self, model, why):
        """BoltOn / weapon model path 'models/...' -> exists (XML2's or imported)."""
        m = C.norm(model)
        if m.endswith('.igb'):
            m = m[:-4]
        if self.exists(m + '.igb'):
            return True
        return self._asset(m + '.igb', why).ok

    def _effect_ok(self, eff, why):
        e = C.norm(eff)
        e = e[:-4] if e.endswith('.xml') else e
        if self.pkg_entry_exists('effect', e):
            return True
        return self._asset(f'effects/{e}.xml', why).ok

    # ---------------------------------------------------------------- style / entity reference check
    def _x1_entity_index(self):
        """entity class name (lower) -> sorted XML1 files defining it (data/entities/*, common_ents, item_ents)."""
        ctx = self.ctx
        idx = {}
        rels = [r for r in ctx.x1_rels('data/entities/') if r.endswith(('.xml', '.eng'))]
        rels += [r for r in ('data/common_ents.xml', 'data/item_ents.xml') if ctx.x1_path(r)]
        for rel in rels:
            try:
                root = ctx.read_x1_xml(rel)
            except Exception:  # noqa: BLE001 - reported by whoever imports that file
                continue
            if root is None:
                continue
            for top in C.iter_roots(root):
                for e in [top] + list(top):
                    if e.get('name'):
                        idx.setdefault(e.get('name').strip().lower(), set()).add(rel)
        return {k: sorted(v) for k, v in idx.items()}

    def _x2_entity_names(self):
        ctx = self.ctx
        names = set()
        for a in ctx.base_index.under('data/'):
            la = a.lower()
            if not la.endswith(('.xmlb', '.engb')):
                continue
            if not (la.startswith('data/entities/') or Path(la).stem in ('common_ents', 'item_ents')):
                continue
            try:
                root = C.decode_xmlb(ctx.base_index.path(a).read_bytes())
            except Exception:  # noqa: BLE001 - XML2 ships a few undecodable files
                continue
            for top in C.iter_roots(root):
                for e in [top] + list(top):
                    if e.get('name'):
                        names.add(e.get('name').strip().lower())
        return names

    def check_style_refs(self, stats_names):
        """Every asset a style file written here (and every data/entities file imported for a character/style
        bundle) names must be available in the output: effects (effect, hiteffect, beameffect, spawneffect, ...,
        footstepfx, loopfx), models/bolt-ons, skins, spawned characters (stats names), entity classes and icon
        textures. XML1's own bundles are the source of truth for what a character loads, so this is a check:
          * available (XML2's or imported)                         -> ok;
          * on the XML1 disc, listed by XML1's permanent package   -> ok (zones appends it to permanent.PKGB);
          * on the XML1 disc, unlisted                             -> imported here and appended to the style
                                                                      package and to the characters using the style;
          * absent from the XML1 disc                              -> warning (dead in XML1 too);
          * a character name that is no stats name / a missing skin actor -> error."""
        ctx = self.ctx
        permanent = {C.norm(p) for p, _ in ctx.manifest.get('packages/generated/maps/package/permanent.fb', [])}
        x1_ents = self._x1_entity_index()
        x2_ents = self._x2_entity_names()
        written_ents = {n for n in self.import_stats.get('written', ()) if n.startswith('data/entities/')}
        world_ents = {C.norm(r) for r in ('data/common_ents.xml', 'data/item_ents.xml')}   # merged by zones
        dead, perm, added = {}, set(), []
        n_checked = 0

        def need(src_rel, entry, where):
            """entry (kind, filename) whose file is src_rel on the XML1 disc is not available yet; `where` is the
            package filename of the style / entity file that references it."""
            if src_rel in permanent:
                perm.add(src_rel)
                return
            if ctx.x1_path(src_rel) is None or ctx.x1_is_empty(src_rel):
                dead.setdefault(src_rel, set()).add(where)
                return
            res = self._asset(src_rel, where)
            if res.ok:
                with self.lock:
                    lst = self.dep_extra.setdefault(where, [])
                    if entry not in lst:
                        lst.append(entry)
                added.append((where, entry))
                if src_rel.startswith('data/entities/') and src_rel not in written_ents:
                    written_ents.add(src_rel)                    # check the newly imported entity file too
                    files.append((False, C.split_ext(src_rel)[0]))

        files = [(True, f'Data/{kind}/{mapped}') for (kind, mapped) in sorted(self.styles_written)]
        files += [(False, C.split_ext(n)[0]) for n in sorted(written_ents)]
        done = set()
        while files:
            is_style, rel_noext = files.pop(0)
            if C.norm(rel_noext) in done:
                continue
            done.add(C.norm(rel_noext))
            actual = ctx.out_index.find(rel_noext, ('.XMLB', '.engb'))
            if actual is None:
                continue
            root = C.decode_xmlb((ctx.out / actual).read_bytes())
            where = C.norm(rel_noext)
            is_ent = not is_style
            for el in root.iter():
                for a, v in el.attrib.items():
                    v = (v or '').strip()
                    al = a.lower()
                    if not v or v.lower() in ('true', 'false', 'none', '0', '1'):
                        continue
                    if _STYLE_EFFECT_ATTR.search(al) or (is_ent and al in ('loopfx', 'trailfx')):
                        n_checked += 1
                        e = C.norm(v)
                        e = e[:-4] if e.endswith('.xml') else e
                        e = e[len('effects/'):] if e.startswith('effects/') else e
                        if not self.pkg_entry_exists('effect', e):
                            need(f'effects/{e}.xml', ('effect', e), where)
                    elif al in ('model', 'bolton') and not _SKIN4.fullmatch(v) and not N.is_skin_id(v):
                        n_checked += 1
                        m = C.norm(v).removesuffix('.igb')
                        if is_ent and not m.startswith('models/'):
                            m = 'models/' + m                       # entity models are relative to models/
                        if not self.exists(m + '.igb'):
                            need(m + '.igb', ('model', m), where)
                    elif al in ('skin', 'actorskin') or (al == 'model' and N.is_skin_id(v)):
                        n_checked += 1
                        if not self.exists(f'actors/{v}.igb'):
                            ctx.error(f'{where}: <{el.tag} {a}="{v}"> actors/{v}.igb does not exist')
                    elif al == 'character':
                        n_checked += 1
                        if v.lower() not in stats_names:
                            ctx.error(f'{where}: <{el.tag} {a}="{v}"> spawns a character that is no stats name')
                    elif al in ('entity', 'deathspawn', 'xdeathspawn', 'actspawn'):
                        n_checked += 1
                        ln = v.lower()
                        if ln in x2_ents or any(C.norm(f) in written_ents or C.norm(f) in world_ents
                                                for f in x1_ents.get(ln, ())):
                            continue
                        defs = x1_ents.get(ln)
                        if not defs:
                            dead.setdefault(f'entity class {v}', set()).add(where)
                            continue
                        f = C.norm(defs[0])
                        need(f, ('xml', C.split_ext(f)[0]), where)
                    elif al == 'iconfile':
                        n_checked += 1
                        t = C.split_ext(C.norm(v))[0]
                        if not self.exists(t + '.igb'):
                            need(t + '.igb', ('texture', t), where)
        ctx.set_count('style_refs_checked', n_checked)
        ctx.set_count('style_refs_files', len(done))
        ctx.set_count('style_refs_dead', len(dead))
        ctx.set_count('style_refs_imported', len(added))
        for what, wh in sorted(dead.items()):
            ctx.warn(f'{what}: referenced by {sorted(wh)} but absent from the XML1 disc (dead in XML1 too; '
                     f'the effect/spawn does nothing)')
        if perm:
            ctx.note(f'{len(perm)} style/entity references are XML1 permanent-package files, loaded through '
                     f'permanent.PKGB (zones appends XML1-only permanent entries): {sorted(perm)}')
        if added:
            ctx.note(f'{len(added)} style/entity references were on the XML1 disc but in no bundle; imported and '
                     f'appended to every package listing the referencing style/entity file: {added[:10]}')
        self.detail['style_refs'] = {'dead': {k: sorted(v) for k, v in dead.items()}, 'permanent': sorted(perm),
                                     'added': [[w, list(e)] for w, e in added]}

    def convert_stats(self, st, origin):
        """XML1 <stats> -> XML2 npcstat <stats> (port of build_chars.convert_stats). origin: 'xml1' (NPC) or
        'xml1_hero_as_npc' (herostat entry used as an NPC: hero-only children dropped)."""
        ctx = self.ctx
        hero = origin == 'xml1_hero_as_npc'
        a = _lower_attrs(st)
        name = a['name']
        out = {}
        for k, v in a.items():
            if v == '' or k in DROP_ATTRS:
                self.detail['dropped_attrs'].append([name, k, v])
                continue
            if k.startswith('skin_') and k[5:] not in COSTUMES_X2:
                self.detail['dropped_attrs'].append([name, k, v])
                ctx.defer(f'{name}: costume attribute {k}={v} has no XML2 costume slot (table 0x6d8aa0); dropped')
                continue
            out[k] = v
        if 'skin' in out:
            out['skin'] = C.map_skin(out['skin'])
        for k in ('leaderskin', 'mutantskin'):
            if k in out:
                out[k] = C.map_skin(out[k])
        if 'characteranims' in out:
            ca = out['characteranims']
            out['characteranims'] = C.map_animdb(ca)
            if not self.exists(f"actors/{out['characteranims']}.igb"):
                ctx.error(f"{name}: characteranims actors/{out['characteranims']}.igb does not exist")
        if 'powerstyle' in out:
            ps = self.style('powerstyles', out['powerstyle'])
            if ps is None:
                self.detail['dropped_attrs'].append([name, 'powerstyle', out.pop('powerstyle')])
            else:
                out['powerstyle'] = ps
        if 'moveset1' in out:
            fs = self.style('fightstyles', out['moveset1'])
            if fs is None:
                self.detail['dropped_attrs'].append([name, 'moveset1', out.pop('moveset1')])
            else:
                out['moveset1'] = fs
        sd = out.get('sounddir')
        if sd:
            if ctx.sound_bank_rel(sd) is None:
                self.detail['sounddir_dropped'].append([name, sd])
                self.detail['dropped_attrs'].append([name, 'sounddir', out.pop('sounddir')])
                zsds = ctx.x1_xbox / 'sounds' / 'zsds'
                on_disc = zsds.is_dir() and any(zsds.rglob(f'{sd.lower()}.zs[ms]'))
                ctx.defer(f'{name}: sounddir {sd} has no planned PC bank (ctx.sound_bank_rel is None; '
                          + ('the XML1 disc has the bank but the sound research did not convert it'
                             if on_disc else 'the XML1 disc has no such bank either, so it was silent in XML1 too')
                          + '); attribute omitted')
                ctx.count('sounddir_dropped')
            else:
                ctx.count('sounddir_kept')
        weapon_name = out.pop('weapon', '')
        weapon = self.x1_weapons.get(weapon_name.lower()) if weapon_name else None
        if weapon_name and weapon is None:
            ctx.warn(f'{name}: weapon {weapon_name} not in XML1 data/weapons/weapons.eng; dropped')
        new = ET.Element('stats', out)
        fight_talent = False
        for c in st:
            tag = c.tag.lower()
            ca = _lower_attrs(c)
            if tag == 'talent':
                tn = ca.get('name', '')
                inline = len(c) > 0 or 'power' in ca or 'descname' in ca
                lvl = ca.get('level', '')
                if hero and (inline or lvl in ('', '0')):
                    self.detail['dropped_children'].append(
                        [name, f'talent {tn}', 'hero talent tree (hero conversion)' if inline else 'level 0'])
                    continue
                if not hero and len(c):
                    self.detail['dropped_children'].append([name, f'talent {tn} <level> tree',
                                                            'inline XML1 definition; kept as a reference'])
                is_fs = tn.lower().startswith('fightstyle_')
                if is_fs:
                    fight_talent = True
                    mapped = self.style('fightstyles', tn)
                    tn = mapped or tn
                x1def = self.x1_talents.get(tn.lower())
                self.ensure_talent(tn, is_fs or (x1def is not None and (x1def.get('fightstyle') or '').lower()
                                                 == 'true'), name)
                e = {'name': tn}
                if lvl:
                    e['level'] = lvl
                ET.SubElement(new, 'talent', e)
            elif tag == 'race':
                ET.SubElement(new, 'Race', {'name': ca.get('name', '')})
            elif tag == 'bolton':
                if len(c):
                    self.detail['dropped_children'].append([name, f"BoltOn {ca.get('model')}",
                                                            'talent-gated upgrade (<require>)'])
                    continue
                # onlyprecache is kept: XMen2.exe's BoltOn loop reads it (0x44a868) and, like XML1, skips a
                # BoltOn whose onlyprecache is "true" (only precached for a power: psi whip, tongue, spear)
                m = ca.get('model', '')
                if _SKIN4.fullmatch(m):
                    ca['model'] = C.map_skin(m)
                    if not self.exists(f"actors/{ca['model']}.igb"):
                        ctx.error(f"{name}: BoltOn actor actors/{ca['model']}.igb does not exist")
                elif m and not self._model_ok(m, f'{name} BoltOn'):
                    ctx.error(f'{name}: BoltOn model {m} exists neither in XML2 nor on the XML1 disc')
                if ca.get('anim'):
                    ca['anim'] = C.map_animdb(ca['anim'])
                    if not self.exists(f"actors/{ca['anim']}.igb"):
                        ctx.error(f"{name}: BoltOn anim actors/{ca['anim']}.igb does not exist")
                ET.SubElement(new, 'BoltOn', ca)
            elif tag in ('multipart', 'flyeffect'):
                for k in ('effect', 'effectondeath', 'loopeffect'):
                    if ca.get(k):
                        self._effect_ok(ca[k], f'{name} {tag} {k}')
                if tag == 'multipart':
                    ign = sorted(k for k in ca if k in MULTIPART_X1_ONLY)
                    if ign:
                        with self.lock:
                            self.detail.setdefault('multipart_ignored', []).append([name, ign])
                ET.SubElement(new, XML2_TAG[tag], ca)
            else:
                self.detail['dropped_children'].append([name, f'<{c.tag}>', 'hero-only XML1 child'])
        if weapon:
            model = weapon.get('model', '')
            b = {'bolt': weapon.get('actorbolt', 'Bip01 R Hand'), 'model': C.norm(model).removesuffix('.igb'),
                 'slot': 'ebolton_weapon'}
            if model and not self._model_ok(model, f'{name} weapon {weapon_name}'):
                ctx.error(f'{name}: weapon model {model} exists neither in XML2 nor on the XML1 disc')
            ET.SubElement(new, 'BoltOn', b)
            if weapon.get('accessorymodel'):
                am = weapon['accessorymodel']
                if not self._model_ok(am, f'{name} weapon accessory'):
                    ctx.error(f'{name}: weapon accessory model {am} exists neither in XML2 nor on the XML1 disc')
                # second attach slot: 'ebolton_altweapon' (slot index 1; the weapon is index 0). The prototype's
                # 'ebolton_weapon2' is not in XMen2.exe's slot table (0x6d6530), so XML2 would drop the BoltOn.
                ET.SubElement(new, 'BoltOn', {'bolt': weapon.get('accessorybolt', 'Bip01 L Hand'),
                                              'model': C.norm(am).removesuffix('.igb'), 'slot': 'ebolton_altweapon'})
            if not fight_talent and weapon.get('fightstyle'):
                fs = self.style('fightstyles', weapon['fightstyle'])
                if fs:
                    self.ensure_talent(fs, True, name)
                    ET.SubElement(new, 'talent', {'level': '1', 'name': fs})
            if 'powerstyle' not in out and weapon.get('powerstyle'):
                ps = self.style('powerstyles', weapon['powerstyle'])
                if ps:
                    new.set('powerstyle', ps)
            if (weapon.get('type') or '').lower() in W.WEAPON_TYPES:
                # SPEC 29: a gun fires through the style; the variant carries this weapon's triggers
                base = a.get('powerstyle') or weapon.get('powerstyle') or ''
                vs = self.weapon_style(base, weapon, weapon_name) if base else None
                if vs:
                    new.set('powerstyle', vs)
                    ctx.count('weapon_styles_used')
            self.detail['notes'].append(f"{name}: XML1 weapon {weapon_name} -> BoltOn {b['model']} "
                                        f"(XML2's stats parser accepts and ignores 'weapon', XMen2.exe 0x4ba383)")
            ctx.count('weapons_to_bolton')
        self._check_bolton_slots(name, new)
        # SPEC 24: XML1's energy pool / regeneration (30 + 4 level + 7 mind; 15 x (1 + mind / 100) per second) on
        # XMen2.exe's formulas (2 mind, no mind factor): the NPC energy talent at rank = mind
        NV.attach_energy_talent(new)
        C.normalize_attrs(new)
        return new

    def _check_bolton_slots(self, name, st):
        """XMen2.exe's stats BoltOn loop (0x44a820..0x44a9d2) skips a BoltOn whose onlyprecache is "true", that
        has no slot or model, or whose slot is not in the table at 0x6d6530 (case-insensitive); each slot name
        maps to one of 6 attach indices, so two BoltOns on the same index compete."""
        used = {}
        for b in st.iter('BoltOn'):
            if (b.get('onlyprecache') or '').lower() == 'true':
                self.ctx.count('bolton_onlyprecache')
                continue
            slot = (b.get('slot') or '').lower()
            if slot not in BOLTON_SLOTS or not b.get('model'):
                self.ctx.warn(f'{name}: BoltOn {b.get("model")!r} slot {b.get("slot")!r} is not a valid XML2 slot '
                              f'{sorted(BOLTON_SLOTS)} (or no model): XMen2.exe skips it (0x44a8df)')
                continue
            idx = BOLTON_SLOTS[slot]
            if idx in used:
                self.ctx.warn(f'{name}: BoltOns {used[idx]!r} and {b.get("model")!r} share attach index {idx}')
            used[idx] = b.get('model')

    # ---------------------------------------------------------------- packages
    def map_entry(self, kind, path, who):
        """one XML1 bundle entry -> (kind, XML2 packagedef filename) with its file guaranteed to exist,
        or None (entry dropped; reason recorded)."""
        ctx = self.ctx
        k = (kind or '').lower()
        p = C.norm(path)
        stem, ext = C.split_ext(p)
        if ext in ('.fre', '.ger'):
            return None
        drop = lambda why: (self.detail['dropped_pkg_entries'].append([who, kind, path, why]), None)[1]  # noqa: E731
        if k in ('actorskin', 'actoranimdb'):
            s = stem[len('actors/'):] if stem.startswith('actors/') else stem
            if s in self.actor_empty:
                return drop('0-byte XML1 actor (not written)')
            kind2, fn = C.map_package_entry(kind, p)
            if not self.pkg_entry_exists(kind2, fn):
                ctx.warn(f'{who}: {kind} {path} -> actors/{fn}.igb does not exist; entry dropped')
                return drop('actor missing')
            return kind2, fn
        m = _UI_CHAR.fullmatch(p)
        if m:
            key = f'{m.group(1)}{m.group(2)}'
            fn = self.ui_new.get(key)
            if fn is None:
                if key in self.ui_new:
                    return drop('0-byte XML1 UI file')
                ctx.warn(f'{who}: {kind} {path} not on the XML1 disc; entry dropped')
                return drop('missing')
            return kind, fn
        if (k == 'fightstyle' or k in ('xml', 'xml_resident')) and \
                stem.startswith(('data/powerstyles/', 'data/fightstyles/')):
            d, _, n = stem.rpartition('/')
            skind = d.split('/')[1]
            mapped = self.style(skind, n)
            if mapped is None:
                return drop('style missing')
            return kind, f'{d}/{mapped}'
        if k == 'texture' and re.fullmatch(r'textures/loading/\d{4}', stem):
            kind2, fn = C.map_package_entry(kind, p)
            if not self.pkg_entry_exists(kind2, fn):
                return drop('loading screen missing')
            return kind2, fn
        if k in C.NO_FILE_KINDS:
            return C.map_package_entry(kind, p)
        if k in ('effect', 'model', 'texture', 'xml', 'xml_resident', 'motionpath'):
            res = self._asset(p, who)
            if not res.ok:
                return drop(res.status)
            kind2, fn = C.map_package_entry(kind, p)
            if not self.pkg_entry_exists(kind2, fn):
                ctx.error(f'{who}: {kind} {path} imported as {res.out_rels} but entry {fn} does not resolve')
                return drop('unresolvable')
            return kind2, fn
        ctx.warn(f'{who}: package entry kind {kind!r} ({path}) not handled; dropped')
        return drop('unhandled kind')

    def build_pkg(self, entries, who):
        root = ET.Element('packagedef')
        seen = set()
        for path, kind in entries:
            e = self.map_entry(kind, path, who)
            if e and e not in seen:
                seen.add(e)
                ET.SubElement(root, e[0], {'filename': e[1]})
        return root, seen

    def swap_variant_style(self, root, stats_el):
        """SPEC 29.1: a package of a stats entry that uses a weapon variant style lists the VARIANT where XML1's
        bundle listed the base style. A power style the engine loads on demand (named by a stats entry but by no
        package) breaks the party's power wheels: in haarp_ext01 (0.1.2) the third and fourth heroes seated had
        no wheel until the next zone; with the variant in the packages all four do (verified in game)."""
        vs = (stats_el.get('powerstyle') or '').lower()
        base = self.variant_base.get(vs)
        if not base:
            return
        for e in root:
            if e.tag == 'fightstyle' and C.norm(e.get('filename', '')) == f'data/powerstyles/{base}':
                e.set('filename', f'data/powerstyles/{vs}')
                self.ctx.count('package_styles_to_variant')

    def add_boltons(self, root, seen, stats_el, who):
        """XML2 packages list every BoltOn model (fix_package_for_boltons) and its anim DB."""
        for b in stats_el.iter('BoltOn'):
            m = b.get('model', '')
            if not m:
                continue
            e = ('actorskin', m) if N.is_skin_id(m) else ('model', C.norm(m).removesuffix('.igb'))
            if e not in seen and self.pkg_entry_exists(*e):
                seen.add(e)
                ET.SubElement(root, e[0], {'filename': e[1]})
            an = b.get('anim')
            if an and ('actoranimdb', an) not in seen and self.pkg_entry_exists('actoranimdb', an):
                seen.add(('actoranimdb', an))
                ET.SubElement(root, 'actoranimdb', {'filename': an})

    def write_pkg(self, rel, root, source=None, allow_base=False):
        """Stage a package; flush_pkgs() writes it after check_style_refs() (which may add dependencies).
        Returns rel, or None when the package is refused (empty, or a character package whose name an XML2
        package already has, which would mean the skin mapping is broken)."""
        ctx = self.ctx
        if len(root) == 0:
            ctx.error(f'{rel}: package would be empty; not written')
            return None
        if not allow_base and rel in ctx.base_index and 'packages/generated/characters/' in C.norm(rel):
            ctx.error(f'{rel}: character package name collides with an XML2 package (skin mapping broken?)')
            return None
        with self.lock:
            if C.norm(rel) in self.pending:
                ctx.error(f'{rel}: package staged twice')
            self.pending[C.norm(rel)] = (rel, root, source)
        return rel

    def flush_pkgs(self):
        """Append to every staged package the dependencies check_style_refs() found for the style / entity
        files it lists (transitively), then write all staged packages. Returns {norm rel: actual rel}."""
        ctx = self.ctx
        written, n_extra = {}, 0
        for key, (rel, root, source) in sorted(self.pending.items()):
            have = {(e.tag, C.norm(e.get('filename') or '')) for e in root}
            queue = [C.norm(e.get('filename') or '') for e in root]
            while queue:
                for kind, fn in self.dep_extra.get(queue.pop(0), ()):
                    if (kind, C.norm(fn)) not in have:
                        have.add((kind, C.norm(fn)))
                        ET.SubElement(root, kind, {'filename': fn})
                        queue.append(C.norm(fn))
                        n_extra += 1
            written[key] = ctx.write_bytes(rel, C.encode_xmlb(root), source=source)
        ctx.set_count('pkg_entries_added_for_refs', n_extra)
        return written

    def character_packages(self, stats_by_lname, zone_skins):
        """Packages/generated/characters/<name>_<mapped skin>[_nc].PKGB from every XML1 bundle of every
        written XML1-origin stats name, plus synthesized ones for zone monster_skin variants without a
        bundle, plus (fallback) synthesized ones when an entry's own skin has no bundle."""
        ctx = self.ctx
        bundles = {}          # lname -> {skin4: {'': entries, '_nc': entries}}
        for k, v in ctx.manifest.items():
            m = _BUNDLE.fullmatch(k)
            if m:
                bundles.setdefault(m.group(1), {}).setdefault(m.group(2), {})[m.group(3) or ''] = v
        written = set()
        for lname, st in stats_by_lname.items():
            skin = st.get('skin')
            own4 = str(int(skin) - N.SKIN_OFFSET).zfill(4) if skin and skin.isdigit() and int(skin) >= N.SKIN_OFFSET else None
            by_skin = bundles.get(lname, {})
            if not by_skin:
                ctx.warn(f'{st.get("name")}: no XML1 character bundle; packages synthesized from the stats entry')
            want = set(by_skin)
            if own4:
                want.add(own4)
            for s4 in sorted(zone_skins.get(lname, ())):
                want.add(s4)
            for s4 in sorted(want):
                for suffix in ('', '_nc'):
                    ents = by_skin.get(s4, {}).get(suffix)
                    how = 'bundle'
                    if ents is None:
                        ents, how = self._synth_entries(lname, st, by_skin, s4, suffix)
                    if ents is None:
                        continue
                    who = f'{lname}_{s4}{suffix}'
                    root, seen = self.build_pkg(ents, who)
                    self.add_boltons(root, seen, st, who)
                    self.swap_variant_style(root, st)
                    rel = C.char_package_rel(lname, C.map_skin(s4), suffix == '_nc')
                    actual = self.write_pkg(rel, root)
                    if actual:
                        written.add(C.norm(actual))
                        self.detail['packages'].append([actual, how, len(root)])
                        if how != 'bundle':
                            self.detail['synth_packages'].append([actual, how])
            # generated/characters/<name>_xml (XMen2.exe 'generated/characters/%s_xml', 0x4bc1f6): the style
            # data of characters that are spawned by powers / scripts (multipleman, spiderpod, bots, heroes ...)
            xb = ctx.manifest.get(f'packages/generated/characters/{lname}_xml.fb')
            rel = f'Packages/generated/characters/{lname}_xml.PKGB'
            if xb is not None:
                root, _ = self.build_pkg(xb, f'{lname}_xml')
                self.swap_variant_style(root, st)
                if len(root) == 0:
                    ctx.warn(f'{lname}_xml: XML1 bundle has no usable entry; not written')
                    continue
                if rel in ctx.base_index:
                    old = [(e.tag, e.get('filename')) for e in ctx.read_base_xmlb(rel)]
                    ctx.note(f'{rel}: XML2 package of the replaced XML2 entry {old} overwritten by XML1\'s')
                actual = self.write_pkg(rel, root, allow_base=True)
                if actual:
                    written.add(C.norm(actual))
                    self.detail['packages'].append([actual, 'bundle', len(root)])
                    ctx.count('char_xml_packages')
            elif rel in ctx.base_index:
                old = ctx.read_base_xmlb(rel)
                bad = [(e.tag, e.get('filename')) for e in old if not self.pkg_entry_exists(e.tag, e.get('filename'))]
                ctx.note(f'{rel}: XML1 has no {lname}_xml bundle; XML2\'s package is kept '
                         f'{[(e.tag, e.get("filename")) for e in old]}' + (f' (unresolved: {bad})' if bad else ''))
                if bad:
                    ctx.warn(f'{rel}: kept XML2 package has unresolved entries {bad}')
        return written

    def _synth_entries(self, lname, st, by_skin, s4, suffix):
        """entries for a (name, skin) the XML1 disc has no bundle for: the stats-skin bundle (or any bundle)
        with actorskin and ui/hud/characters swapped to this skin (the pattern of XML1's costume bundles,
        e.g. magma_1801 vs magma_1803), else a minimal package from the stats entry."""
        ctx = self.ctx
        skin = st.get('skin')
        own4 = str(int(skin) - N.SKIN_OFFSET).zfill(4) if skin and skin.isdigit() and int(skin) >= N.SKIN_OFFSET else None
        src4 = own4 if own4 in by_skin else (sorted(by_skin)[0] if by_skin else None)
        if src4 is not None and by_skin[src4].get(suffix) is not None:
            out = []
            for p, kind in by_skin[src4][suffix]:
                q = C.norm(p)
                if kind.lower() == 'actorskin' and q == f'actors/{src4}.igb':
                    q = f'actors/{s4}.igb'
                elif q == f'ui/hud/characters/{src4}.igb' and ctx.x1_path(f'ui/hud/characters/{s4}.igb'):
                    q = f'ui/hud/characters/{s4}.igb'
                out.append([q, kind])
            return out, f'synth:variant of {lname}_{src4}{suffix}'
        # minimal package from the stats entry
        out = [[f'actors/{s4}.igb', 'actorskin']]
        ca = st.get('characteranims')
        if ca:
            out.append([f'actors/{ca}.igb', 'actoranimdb'])       # already mapped: entry mapper maps idempotently
        if ctx.x1_path(f'hud/hud_head_{s4}.igb'):
            out.append([f'hud/hud_head_{s4}.igb', 'model'])
        if ctx.x1_path(f'ui/hud/characters/{s4}.igb'):
            out.append([f'ui/hud/characters/{s4}.igb', 'model'])
        if suffix == '' and st.get('powerstyle'):
            out.append([f"data/powerstyles/{st.get('powerstyle')}.xml", 'fightstyle'])
        for t in st.iter('talent'):
            if t.get('name', '').lower().startswith('fightstyle_'):
                out.append([f"actors/{t.get('name')}.igb", 'actoranimdb'])
                out.append([f"data/fightstyles/{t.get('name')}.eng", 'fightstyle'])
        return out, 'synth:stats'

    def style_packages(self):
        """Packages/generated/{powerstyles,fightstyles}/<mapped>.PKGB for every style written here."""
        ctx = self.ctx
        n = 0
        for (kind, mapped), rel in sorted(self.styles_written.items()):
            x1name = C.split_ext(rel)[0].rsplit('/', 1)[1]
            bundle = ctx.manifest.get(f'packages/generated/{kind}/{x1name}.fb')
            if bundle is None:
                ents = [[rel, 'xml']]
                ctx.warn(f'{rel}: no XML1 style bundle; package lists only the style file')
            else:
                ents = bundle
            who = f'{kind}/{mapped}'
            root, _ = self.build_pkg(ents, who)
            dst = f'Packages/generated/{kind}/{mapped}.PKGB'
            if dst in ctx.base_index:
                old = ctx.read_base_xmlb(dst)
                self.detail['notes'].append(f'{dst}: replaces XML2 leftover package '
                                            f'{[(e.tag, e.get("filename")) for e in old]} (XML2 ships no such style)')
                ctx.count('style_packages_replaced_xml2_leftover')
            actual = self.write_pkg(dst, root)
            if actual:
                n += 1
                self.detail['packages'].append([actual, 'style bundle', len(root)])
        nw = sum(1 for k in ctx.manifest if k.startswith('packages/generated/weapons/'))
        ctx.set_count('weapon_bundles_deferred', nw)
        ctx.defer(f"{nw} XML1 weapon bundles (packages/generated/weapons/*.fb) not converted: XML2 ignores "
                  f"'weapon' (0x4ba383); weapons become BoltOns + fightstyle talents; gun/grenade combat "
                  f"(ch_weapon_semi_auto, ch_grenade) needs the powers rework")
        return n


# ------------------------------------------------------------------------------------------------ keep scan
def _scan_keep_needs(ctx, x2npc_lower, herostat_root):
    """Names of XML2 npcstat entries that XML2 content still active in XML1 mode refers to by name:
    front-end zone CHRBs (Maps/menu), the XML2 herostat heroes' powerstyles / talent files / character and
    powerstyle packages (and the entity/script files those list), the XML2 world tables zones keeps, and
    the permanent package. Returns {lower name: [where...]}, files scanned."""
    files = []
    for a in ctx.base_index.under('maps/menu/'):
        files.append(a)
    pk_chars = ctx.base_index.under('packages/generated/characters/')
    pkgs = []
    for st in herostat_root.iter('stats'):
        n = (st.get('name') or '').lower()
        ps = (st.get('powerstyle') or '').lower()
        for rel in (f'data/talents/{n}', f'data/powerstyles/{ps}' if ps else None):
            if rel:
                files += ctx.base_index.find_all(rel, ('.xmlb', '.engb'))
        pkgs += [a for a in pk_chars if Path(a).name.lower().startswith(n + '_')]
        if ps:
            pkgs += ctx.base_index.find_all(f'packages/generated/powerstyles/{ps}', ('.pkgb',))
    for t in ('common_ents', 'item_ents', 'items', 'shared_nodes', 'shared_powerups', 'team_bonus',
              'boltonactoranims', 'shared_anims', 'shared_combat_events', 'autospend', 'styles'):
        files += ctx.base_index.find_all(f'data/{t}', ('.xmlb', '.engb'))
    pkgs += ctx.base_index.find_all('packages/generated/maps/package/permanent', ('.pkgb',))
    for t in ('common_ents', 'item_ents', 'items', 'shared_nodes'):
        pkgs += ctx.base_index.find_all(f'packages/generated/{t}', ('.pkgb',))
    for p in pkgs:
        files.append(p)
        try:
            root = ctx.read_base_xmlb(p)
        except (KeyError, ValueError, OSError):
            continue
        for e in root:
            fn = e.get('filename') or ''
            k = e.tag.lower()
            if k in ('xml', 'xml_resident', 'fightstyle'):
                files += ctx.base_index.find_all(fn, ('.xmlb', '.engb'))
            elif k == 'script':
                files += ctx.base_index.find_all(fn, ('.py',))
    need = {}
    scanned = 0
    for rel in dict.fromkeys(files):
        low = rel.lower()
        path = ctx.base_index.path(rel)
        if path is None:
            continue
        scanned += 1
        if low.endswith('.py'):
            text = path.read_bytes().decode('latin-1')
            for mm in re.finditer(r'(\w+)\s*\(([^)]*)\)', text):
                for s in re.findall(r'"([^"]*)"', mm.group(2)):
                    if s.lower() in x2npc_lower:
                        need.setdefault(s.lower(), []).append(f'{rel}: {mm.group(1)}("{s}")')
            continue
        if not low.endswith(('.xmlb', '.engb', '.chrb', '.pkgb')):
            continue
        try:
            root = C.decode_xmlb(path.read_bytes())
        except Exception:  # noqa: BLE001 - XML2 ships a few undecodable files (e.g. mansion6_1.NAVB)
            continue
        is_chr = low.endswith('.chrb')
        for el in root.iter():
            for k, v in el.attrib.items():
                lv = (v or '').strip().lower()
                if lv in x2npc_lower and (is_chr or _CHAR_ATTR.search(k.lower())):
                    need.setdefault(lv, []).append(f'{rel}: <{el.tag} {k}="{v}">')
    return need, scanned


# ------------------------------------------------------------------------------------------------ run
def run(ctx):
    b = _Builder(ctx)
    for k in ('sounddir_kept', 'sounddir_dropped', 'weapons_to_bolton', 'actors_empty_skipped', 'char_xml_packages'):
        ctx.set_count(k, 0)
    plan = planned_stats(ctx)            # single source of truth for the name plan (also a --only provider)
    for e in plan['zone_parse_errors']:
        ctx.warn(f'zone file not parsed for character references (zones reports it): {e}')

    # ---------------- sources
    x1npc = _stats_list(ctx.read_x1_xml('data/npcstat.eng'))
    x1hero = {s.get('name').lower(): s for s in _stats_list(ctx.read_x1_xml('data/herostat.eng'))}
    base = {e: ctx.read_base_xmlb(f'Data/npcstat.{e}') for e in ('XMLB', 'engb')}
    hero_roots = {e: ctx.read_base_xmlb(f'Data/herostat.{e}') for e in ('XMLB', 'engb')}
    hero_names = {e: [s.get('name') for s in r.iter('stats')] for e, r in hero_roots.items()}
    h2 = {n.lower() for n in hero_names['engb']} | {n.lower() for n in hero_names['XMLB']}
    x2npc = {s.get('name').lower(): s.get('name') for s in base['engb'].iter('stats')}
    b.load_talents()
    b.load_weapons()

    # ---------------- keep list (KEEP_X2 + exe strings via x2_stats_refs.json + scan of still-active XML2 content)
    evidence, need, scanned = plan['keep_evidence'], plan['keep_need'], plan['keep_scanned']
    if evidence != set(KEEP_X2):
        ctx.warn(f'keep-list evidence (x2_stats_refs.json in_exe + MC placeholders) differs from KEEP_X2: '
                 f'extra {sorted(evidence - set(KEEP_X2))}, missing {sorted(set(KEEP_X2) - evidence)}; using the union')
    keep = set(KEEP_X2) | evidence | set(need)
    added_keep = sorted(n for n in need if n not in set(KEEP_X2) | evidence)
    for n in added_keep:
        ctx.note(f'keep-list: XML2 npcstat {x2npc[n]} kept because {need[n][:3]}')
    ctx.note(f'keep-list scan: {scanned} XML2 files still active in XML1 mode scanned (front-end zones, XML2 '
             f'herostat powerstyles/talents/packages and the entity/script files they list, world tables, '
             f'permanent package); {len(need)} kept-able names referenced, {len(added_keep)} of them added to '
             f'KEEP_X2: {added_keep}')
    ctx.set_count('keep_scan_files', scanned)
    ctx.set_count('keep_added_by_scan', len(added_keep))
    missing_keep = sorted(n for n in set(KEEP_X2) | evidence if n not in x2npc)
    if missing_keep:
        ctx.error(f'keep-list names absent from XML2 npcstat (wrong base install?): {missing_keep}')

    # ---------------- namespace files and styles
    b.emit_namespace()
    b.emit_styles()

    # ---------------- stats entries
    new_entries = []          # (Element, origin)
    x1npc_by = {s.get('name').lower(): s for s in x1npc}
    for n in plan['x1_npcs']:
        new_entries.append((b.convert_stats(x1npc_by[n.lower()], 'xml1'), 'xml1'))
    heroes = plan['heroes_as_npc']
    for hn in heroes:
        new_entries.append((b.convert_stats(x1hero[hn.lower()], 'xml1_hero_as_npc'), 'xml1_hero_as_npc'))
        ctx.note(f'hero used as NPC: {hn} (referenced by {plan["hero_refs"][hn.lower()][:4]})')
    ctx.note(f'XML1 stats names covered by XML2 herostat stand-ins (not added to npcstat; XML2 hero entry and '
             f'packages used): {plan["covered"]}')
    unused = sorted(s.get('name') for k, s in x1hero.items() if k not in h2 and s.get('name') not in heroes)
    _hero_refs_report(ctx, unused)
    _npc_scaling(ctx, new_entries, base['engb'])
    _npc_energy(ctx, b, new_entries)
    new_names = {e.get('name').lower() for e, _ in new_entries}
    if new_names | set(plan['keep_x2']) | {n.lower() for n in plan['herostat']} != plan['names']:
        ctx.error('internal: planned_stats names differ from the entries built')

    # ---------------- npcstat in XML1 mode (each file from its own base)
    roots = {}
    for ext, root in base.items():
        r = copy.deepcopy(root)
        for st in list(r):
            n = (st.get('name') or '').lower()
            if n not in keep or n in new_names:
                r.remove(st)
                if ext == 'engb':
                    b.detail['x2_dropped'].append(st.get('name'))
            elif ext == 'engb':
                b.detail['x2_kept'].append(st.get('name'))
        for e, _ in new_entries:
            r.append(copy.deepcopy(e))
        roots[ext] = r
    replaced = sorted(x2npc[n] for n in keep if n in new_names and n in x2npc)
    same_name = sorted(x2npc[n] for n in x2npc if n in new_names)
    ctx.note(f'npcstat: {len(b.detail["x2_kept"])} XML2 entries kept {b.detail["x2_kept"]}; '
             f'{len(b.detail["x2_dropped"])} XML2 entries dropped. {len(same_name)} of the dropped names have an '
             f'XML1 entry of the same name (XML1 wins): {same_name}; {len(replaced)} of those are on the keep list '
             f'{replaced}')
    ctx.set_count('x2_npc_same_name_replaced', len(same_name))
    ctx.set_count('x2_npc_kept', len(b.detail['x2_kept']))
    ctx.set_count('x2_npc_dropped', len(b.detail['x2_dropped']))

    # XML2 content that referenced dropped names (reported; danger room / codex are out of scope)
    dropped_l = {n.lower() for n in b.detail['x2_dropped']} - new_names
    try:
        dr = ctx.read_base_xmlb('Data/dangerroom.XMLB')
        dr_refs = sorted({(el.get('character') or '').lower() for el in dr.iter() if el.get('character')} & dropped_l)
        if dr_refs and C.frontend_mode(ctx) == 'xml2':
            ctx.defer(f'XML2 Danger Room courses (data/dangerroom) spawn {len(dr_refs)} dropped XML2 NPCs '
                      f'(e.g. {dr_refs[:6]}); the danger room menu is out of phase-1 scope')
        elif dr_refs:
            ctx.note(f'XML2 Danger Room courses name {len(dr_refs)} dropped XML2 NPCs; --frontend xml1 replaces the '
                     f'table with XML1\'s courses (frontend module, SPEC 21 B)')
    except KeyError:
        pass

    # ---------------- caps / table invariants
    _check_caps(ctx, roots, hero_roots, b)

    # ---------------- write stats + talents + values
    ctx.write_xmlb_pair('Data/npcstat', roots['XMLB'], roots['engb'], source='xml1build.characters')
    ctx.write_xmlb_pair('Data/shared_talents', b.talent_roots[0], b.talent_roots[1], source='xml1build.characters')
    ctx.set_count('talents_added', len(b.detail['talents_added']))
    ctx.note(f"shared_talents: {len(b.detail['talents_added'])} empty definitions added "
             f"{sorted({t for t, _ in b.detail['talents_added']})}")
    ctx.defer('the added shared talents are empty definitions: XML1 passive talent effects (acrobatics, '
              'toughness, mutantmastery, *_special activepowerups ...) do nothing unless reworked (powers phase)')
    _values(ctx, b)

    # ---------------- packages
    stats_by_lname = {e.get('name').lower(): e for e, _ in new_entries}
    zone_skins = {n: s for n, s in plan['zone_monster_skins'].items() if n in stats_by_lname}
    char_pkgs = b.character_packages(stats_by_lname, zone_skins)
    # check the two packages the engine asks for (own skin) exist for every new entry
    for lname, st in stats_by_lname.items():
        for nc in (False, True):
            rel = C.norm(C.char_package_rel(lname, st.get('skin'), nc))
            if rel not in char_pkgs:
                ctx.error(f'{st.get("name")}: package {rel} not written')
    n_style_pkgs = b.style_packages()
    # every asset the written styles / imported entity files name must be loadable, then write all packages
    b.check_style_refs(plan['names'])
    b.flush_pkgs()
    _engb_shadow_guard(ctx, b)
    ctx.set_count('packages_written', len(char_pkgs) + n_style_pkgs)
    ctx.set_count('char_packages', len(char_pkgs))
    ctx.set_count('style_packages', n_style_pkgs)
    ctx.set_count('char_packages_synthesized', len(b.detail['synth_packages']))
    if b.detail['synth_packages']:
        ctx.note(f"{len(b.detail['synth_packages'])} character packages synthesized for (name, skin) pairs the "
                 f"XML1 disc has no bundle for (zone monster_skin variants; XML2 packages every monster_skin it "
                 f"spawns): {[p for p, _ in b.detail['synth_packages']][:8]} ...")
    drops = b.detail['dropped_pkg_entries']
    if drops:
        by = {}
        for _, kind, path, why in drops:
            by.setdefault(why, set()).add(f'{kind}:{path}')
        ctx.note('package entries dropped: ' + '; '.join(f'{w}: {len(v)} distinct (e.g. {sorted(v)[:3]})'
                                                          for w, v in sorted(by.items())))
    for k, v in sorted(b.import_stats.items()):
        ctx.set_count(f'assets_{k}', len(v))            # distinct generic XML1 assets by import status
    b.detail['kept_xml2_assets'] = sorted(b.import_stats.get('kept_xml2', ()))
    ctx.note(f"generic assets referenced by character/style bundles: {len(b.import_stats.get('written', ()))} "
             f"imported from XML1, {len(b.import_stats.get('kept_xml2', ()))} same-path XML2 files used instead "
             f"(collision policy: XML2 wins for models/textures/effects)")
    if MERGE_BOLTON_ANIMS:
        _bolton_anims(ctx, b)

    # ---------------- reports
    _report_styles(ctx, b)
    if 'heroes' in (ctx.shared.get('selected_modules') or ()):
        ctx.note('herostat / hero-as-NPC entries: rewritten by the heroes module next (SPEC_heroes.md): XML1 roster, '
                 'talent files, collapsed powerstyles, packages, npcstat and shared_talents patches')
    else:
        ctx.defer('XML1 hero conversion (herostat stays XML2\'s 21 stand-ins): talent trees -> data/talents, '
                  'activepowerup, power1-4, menus, textureicon, HUD heads per costume (run the heroes module)')
    mp = b.detail.get('multipart_ignored', [])
    if mp:
        ctx.defer(f'{len(mp)} XML1 Multipart parts use attributes XMen2.exe does not parse (0x48ce80 reads only '
                  f'bone/NonMenuOnly/hideSkin/showSkin): {sorted({a for _, x in mp for a in x})} on '
                  f'{sorted({n for n, _ in mp})}: breakable-part death effects, loop effects, power links, '
                  f'health multipliers and parts hidden at start (Juggernaut helmet) are lost; the scripts '
                  f'research emulates destroyMultipartPiece with setSegmentVisible + spawnEffectBone')
        ctx.set_count('multipart_x1_attrs_ignored', len(mp))
    if b.detail['dropped_children']:
        heroes_dropped = sum(1 for d in b.detail['dropped_children'] if 'hero' in d[2] or d[2] == 'level 0')
        ctx.note(f"{len(b.detail['dropped_children'])} stats children dropped or reduced "
                 f"({heroes_dropped} hero talents/boltons of the heroes used as NPCs; NPC inline talent "
                 f"<level> trees kept as references with empty shared definitions)")

    # ---------------- shared hand-over
    stats = {}
    origin_of = {e.get('name').lower(): o for e, o in new_entries}
    for ext_root, f in ((hero_roots['engb'], 'herostat'), (roots['engb'], 'npcstat')):
        for st in ext_root.iter('stats'):
            n = st.get('name')
            ln = n.lower()
            origin = origin_of.get(ln, 'xml2') if f == 'npcstat' else 'xml2'
            stats[ln] = {'name': n, 'file': f, 'skin': st.get('skin'), 'characteranims': st.get('characteranims'),
                         'powerstyle': st.get('powerstyle'), 'sounddir': st.get('sounddir'), 'origin': origin}
    ctx.shared['stats'] = stats
    ctx.shared['stats_names'] = set(stats)
    ctx.shared['weapon_variant_base'] = dict(b.variant_base)                       # SPEC 29.1 (zones packages)
    ctx.shared['stats_powerstyle'] = {n: (e.get('powerstyle') or '').lower() for n, e in stats_by_lname.items()}
    ctx.shared['char_packages'] = set(char_pkgs)
    ctx.set_count('npc_entries', sum(1 for _, o in new_entries if o == 'xml1'))
    ctx.set_count('hero_as_npc', sum(1 for _, o in new_entries if o == 'xml1_hero_as_npc'))
    ctx.set_count('stats_names', len(stats))
    ctx.set_count('shared_talents', len(list(b.talent_roots[1].iter('talent'))))
    ctx.note(f'heroes used as NPCs (origin xml1_hero_as_npc): {heroes}')
    b.detail['stats_names'] = sorted(stats)
    b.detail['heroes_as_npc'] = heroes
    b.detail['keep_scan'] = {k: v[:5] for k, v in need.items()}
    ctx.write_meta('characters_detail.json', b.detail)


_ROSTER_FUNCS = {'unlockcharacter', 'ischaracterunlocked', 'setincampaign'}
_MISSION_HERO_TAGS = {'requiredhero', 'restrictedhero', 'recommendedhero', 'mustlivehero', 'course'}


def _hero_refs_report(ctx, unused):
    """SPEC 5.1: XML1 heroes that zones use as NPCs come from zone .chr files and spawners; also check the
    (rewritten, installed) scripts and the conversations / data for the XML1 heroes that were NOT added
    (neither XML2 herostat nor zone-spawned), and classify every reference:
      roster     unlockCharacter / isCharacterUnlocked (the XML1 roster: hero conversion, deferred)
      speaker    %NAME% conversation speaker tokens (speaker markup, deferred)
      mission    REQUIREDHERO / RESTRICTEDHERO / ... / COURSE hero (forced per-mission heroes, deferred)
      actor      script calls on a zone entity that carries the hero's name (not a stats lookup)
      other      anything else -> warning (a stats lookup of a name that is not registered)."""
    if not unused:
        return
    want = {n.lower(): n for n in unused}
    pat = re.compile(r'(?i)"(' + '|'.join(re.escape(n) for n in want) + r')"')
    tok = re.compile(r'(?i)%(' + '|'.join(re.escape(n) for n in want) + r')%')
    call = re.compile(r'(\w+)\s*\(([^()]*)\)')
    attr = re.compile(r'(?i)<\s*([\w]+)[^<>]*?\b([\w]+)\s*=\s*"(' + '|'.join(re.escape(n) for n in want) + r')"')
    found = {n: {} for n in want}

    def add(n, cls, where):
        found[n.lower()].setdefault(cls, set()).add(where)

    sroot = ctx.research_path('scripts/out/scripts')
    for p in sroot.rglob('*.py'):
        text = p.read_bytes().decode('latin-1')
        if not pat.search(text):
            continue
        rel = p.relative_to(sroot).as_posix()
        for m in call.finditer(text):
            for s in pat.findall(m.group(2)):
                cls = 'roster' if m.group(1).lower() in _ROSTER_FUNCS else 'actor'
                add(s, cls, f'scripts/{rel}: {m.group(1)}')
    needles = [n.encode() for n in want]
    for rel in ctx.x1_rels(''):
        if not rel.endswith(('.eng', '.xml')) or rel.startswith(('data/npcstat', 'data/herostat')):
            continue
        raw = ctx.x1_path(rel).read_bytes()
        low = raw.lower()
        if not any(nd in low for nd in needles):
            continue
        text = raw.decode('latin-1')
        for m in tok.finditer(text):
            add(m.group(1), 'speaker', rel)
        for m in attr.finditer(text):
            tag, a, v = m.group(1).lower(), m.group(2).lower(), m.group(3)
            if tag in _MISSION_HERO_TAGS:
                cls = 'mission'
            elif a == 'character':
                cls = 'other'                       # a spawn (planned_stats adds zone-spawned heroes)
            elif tag in ('answer', 'line', 'page') or a in ('text', 'name', 'group', 'item', 'exclusive', 'hero',
                                                           'monster_name', 'descname'):
                cls = 'text/data label'
            else:
                cls = 'other'
            add(v, cls, f'{rel} <{m.group(1)} {m.group(2)}>')
    for ln, name in sorted(want.items()):
        classes = found[ln]
        summary = {c: len(w) for c, w in sorted(classes.items())}
        ctx.defer(f'XML1 hero {name} is neither an XML2 herostat hero nor spawned by any zone: not added to '
                  f'npcstat (hero conversion). References: {summary or "none"}; roster/speaker/mission uses are '
                  f'deferred with the hero conversion / speaker markup / forced heroes')
        for w in sorted(classes.get('other', ()))[:10]:
            ctx.warn(f'{name}: referenced by {w}, which may look the name up in the stats table (not registered)')
        ctx.set_count(f'hero_not_added_refs_{ln}', sum(summary.values()))


NPC_SCALING_MODES = ('off', 'xml2curve')
SPECIFIC_ATTRS = ('specific_attack', 'specific_defense', 'specific_health')


def npc_scaling_mode(ctx) -> str:
    m = (ctx.opt('npc_scaling') or os.environ.get('XML1BUILD_NPC_SCALING') or 'off').lower()
    return m if m in NPC_SCALING_MODES else 'off'


def xml2_level_curve(npc_root):
    """level -> {specific_attack, specific_defense, specific_health} from XML2 retail's own enemies: the median of
    the numeric values at each level (XML2 also writes value codes like 'M_AR22', which XMen2.exe's atoi 0x67233c
    reads as 0: skipped), linearly interpolated between levels and held flat past the ends."""
    per = collections.defaultdict(lambda: collections.defaultdict(list))
    for s in npc_root.iter('stats'):
        lv = (s.get('level') or '').strip()
        if not lv.isdigit():
            continue
        for a in SPECIFIC_ATTRS:
            v = (s.get(a) or '').strip()
            if v.isdigit():
                per[a][int(lv)].append(int(v))
    curve = {}
    for a in SPECIFIC_ATTRS:
        pts = sorted((lv, sorted(vs)[len(vs) // 2]) for lv, vs in per[a].items())
        if not pts:
            continue
        for lv in range(1, 61):
            lo = max((p for p in pts if p[0] <= lv), default=pts[0])
            hi = min((p for p in pts if p[0] >= lv), default=pts[-1])
            if hi[0] == lo[0]:
                v = lo[1]
            else:
                v = lo[1] + (hi[1] - lo[1]) * (lv - lo[0]) / (hi[0] - lo[0])
            curve.setdefault(lv, {})[a] = int(round(v))
    return curve


def _npc_scaling(ctx, new_entries, x2_npc_root):
    """XML2 enemies carry specific_attack/defense/health and a monst_dmg_high talent at their level (XMen2.exe
    reads specific_* at 0x4ba450..0x4ba4fd); XML1 NPCs carry XML1's own level (1..40) and strength/body/mind/speed
    instead. Default ('off'): keep XML1's values and defer the tuning (the XML1-authored level and stats are what
    the fallback path gets; whether XML1 enemies are too weak against XML2's hero stand-ins is an in-game check).
    --npc-scaling xml2curve: give every XML1 enemy with a level the XML2 retail per-level curve (xml2_level_curve)
    and monst_dmg_high at its level, like XML2's own enemies (npchealthscale, which XML1 bosses use, still
    multiplies the health)."""
    mode = npc_scaling_mode(ctx)
    enemies = [(e, o) for e, o in new_entries if (e.get('team') or '').lower() == 'enemy'
               and (e.get('level') or '').strip().isdigit()]
    ctx.set_count('npc_scaling_candidates', len(enemies))
    if mode == 'off':
        lv = collections.Counter(int(e.get('level')) for e, _ in enemies)
        ctx.defer(f'NPC combat scaling: {len(enemies)} XML1 enemies keep XML1\'s level (1..{max(lv) if lv else 0}) and '
                  f'strength/body/mind/speed, without XML2\'s specific_attack/defense/health and monst_dmg_* talents '
                  f'(XML2 enemies: 168-183 of 275 carry them). In-game check: XML1 enemies vs the XML2 hero stand-ins '
                  f'(grso_riot in nyc1_1_1 is level 1, the weakest). Ready fallback: --npc-scaling xml2curve '
                  f'(XML2 retail per-level curve + monst_dmg_high)')
        ctx.set_count('npc_scaling_applied', 0)
        return
    curve = xml2_level_curve(x2_npc_root)
    n = 0
    for e, _ in enemies:
        if any(e.get(a) for a in SPECIFIC_ATTRS):
            continue
        lv = int(e.get('level'))
        row = curve.get(min(max(lv, 1), 60)) or {}
        for a in SPECIFIC_ATTRS:
            if a in row:
                e.set(a, str(row[a]))
        if not any(t.tag == 'talent' and (t.get('name') or '').lower().startswith('monst_dmg') for t in e):
            ET.SubElement(e, 'talent', {'level': str(lv), 'name': 'monst_dmg_high'})
        n += 1
    ctx.set_count('npc_scaling_applied', n)
    ctx.note(f'--npc-scaling xml2curve: {n} XML1 enemies got XML2\'s per-level specific_attack/defense/health and '
             f'monst_dmg_high at their level (curve e.g. L1 {curve.get(1)}, L15 {curve.get(15)}, L40 {curve.get(40)})')


def _npc_energy(ctx, b, new_entries):
    """SPEC 24: every converted entry with a mind carries npc_values.ENERGY_TALENT at rank = mind (convert_stats);
    add the talent's definition (XMLB and engb) for ranks up to the highest used, and report XML1's pools."""
    ranks = {e.get('name').lower(): NV.energy_rank(e) for e, _ in new_entries}
    used = {n: r for n, r in ranks.items() if r}
    capped = sorted(e.get('name') for e, _ in new_entries if (NV._int_attr(e, 'mind') or 0) > NV.RANK_MAX)
    if capped:
        ctx.warn(f'NPC energy: mind above {NV.RANK_MAX} capped at rank {NV.RANK_MAX} (XML2 NPC talents stop at 99): '
                 f'{capped}')
    top = max(used.values(), default=0)
    if top:
        with b.lock:
            for root in b.talent_roots:
                for t in [t for t in root.iter('talent') if (t.get('name') or '').lower() == NV.ENERGY_TALENT]:
                    root.remove(t)
                root.append(NV.energy_talent(top))
            b.talent_names.add(NV.ENERGY_TALENT)
    ctx.set_count('npc_energy_entries', len(used))
    ctx.set_count('npc_energy_max_rank', top)
    ex = []
    for e, _ in new_entries:
        n = e.get('name').lower()
        if n in ('pyroact1', 'sabretoothact2', 'acolyteenergy', 'magnetoact4') and used.get(n):
            lv = NV._int_attr(e, 'level') or 1
            r = used[n]
            ex.append(f'{e.get("name")} L{lv} M{r}: pool {NV.x2_max_energy(lv, r)} -> '
                      f'{NV.x2_max_energy(lv, r, r)} (XML1 {NV.x1_max_energy(lv, r)}), regen '
                      f'{NV.x2_regen():g} -> {NV.x2_regen(r):g}/s (XML1 {NV.x1_regen(r):g})')
    b.detail['npc_energy'] = {'ranks': dict(sorted(used.items())), 'max_rank': top,
                              'no_mind': sorted(n for n, r in ranks.items() if not r)}
    ctx.note(f'NPC energy (SPEC 24): {len(used)} converted stats entries carry {NV.ENERGY_TALENT} at rank = mind '
             f'(1..{top}): maxenergy +5 mind, energy_regen x (1 + mind / 100), so XMen2.exe\'s 30 + 4 level + '
             f'2 mind pool and 15/s regeneration become XML1\'s 30 + 4 level + 7 mind and 15 x (1 + mind / 100)/s; '
             f'{len(ranks) - len(used)} entries without a mind need none. E.g. {ex}')


def _check_caps(ctx, roots, hero_roots, b):
    for ext in ('XMLB', 'engb'):
        hn = [s.get('name') for s in hero_roots[ext].iter('stats')]
        nn = [s.get('name') for s in roots[ext].iter('stats')]
        hl, nl = [n.lower() for n in hn], [n.lower() for n in nn]
        if len(hl) != HERO_COUNT:
            ctx.error(f'herostat.{ext}: {len(hl)} heroes (XMen2.exe maps exactly {HERO_COUNT}, 0x44bb13)')
        dup = sorted({n for n in nl if nl.count(n) > 1})
        if dup:
            ctx.error(f'npcstat.{ext}: duplicate names {dup} (second registration ignored)')
        both = sorted(set(hl) & set(nl))
        if both:
            ctx.error(f'npcstat.{ext}: names also in herostat {both} (second registration ignored)')
        uniq = set(hl) | set(nl)
        if len(uniq) > STATS_CAP:
            ctx.error(f'{ext}: {len(uniq)} unique stats names > {STATS_CAP} (XMen2.exe 0x44c1a7); extra names '
                      f'are silently skipped')
        for n in uniq:
            if len(n) > NAME_MAX:
                ctx.error(f'stats name {n!r} longer than {NAME_MAX} characters')
        for st in list(hero_roots[ext].iter('stats')) + list(roots[ext].iter('stats')):
            for k, v in st.attrib.items():
                if k in ('skin', 'leaderskin', 'mutantskin'):
                    if not re.fullmatch(r'\d{4,5}', v) or int(v[:-2]) > 255:
                        ctx.error(f"{st.get('name')}: {k}={v!r} is not 4-5 digits with prefix <= 255 (0x4b9c40)")
                elif k.startswith('skin_') and not re.fullmatch(r'\d{1,2}', v):
                    ctx.error(f"{st.get('name')}: costume {k}={v!r} is not a 2-digit variant")
    if {s.get('name').lower() for s in roots['XMLB'].iter('stats')} != \
            {s.get('name').lower() for s in roots['engb'].iter('stats')}:
        ctx.error('npcstat XMLB and engb list different names')
    tl = [len(list(r.iter('talent'))) for r in b.talent_roots]
    for ext, n in zip(('XMLB', 'engb'), tl):
        if n > TALENT_CAP:
            ctx.error(f'shared_talents.{ext}: {n} talents > {TALENT_CAP} (ids 0..98, XMen2.exe 0x4c05d0)')
    ctx.log(f'stats names {len(set(s.get("name").lower() for s in hero_roots["engb"].iter("stats")) | set(s.get("name").lower() for s in roots["engb"].iter("stats")))}/{STATS_CAP}, '
            f'shared talents {tl[1]}/{TALENT_CAP}')


def _values(ctx, b):
    """append the XML1 value codes XML2 lacks (A1-A10, XTL1-6) to Data/values.XMLB; report the differing ones."""
    x2 = ctx.read_base_xmlb('Data/values.XMLB')
    x1 = ctx.read_x1_xml('data/values.xml')
    have = {(v.get('name') or ''): v for v in x2.iter('value')}
    added, differ = [], []
    for v in x1.iter():
        if v.tag.lower() != 'value' or not v.get('name'):
            continue
        n = v.get('name')
        if n not in have:
            x2.append(ET.Element('value', {k.lower(): val for k, val in v.attrib.items()}))
            added.append(n)
        elif {k: have[n].get(k) for k in ('min', 'max')} != {k: v.get(k) for k in ('min', 'max')}:
            differ.append(n)
    if added:
        ctx.write_xmlb('Data/values', x2, ('.XMLB',), source=ctx.x1_path('data/values.xml'))
    ctx.set_count('values_added', len(added))
    ctx.note(f'values: appended {len(added)} XML1 codes {added}')
    ctx.defer(f'values: {len(differ)} XML1 codes differ from XML2 ({differ}); left to the powers phase')
    ctx.note('values: XMen2.exe reads data/values.xmlb only at 0x4c4640 and only keeps DMG2/DMG3/DMG4/K2/K3 '
             '(name table 0x6da240; any other code in a style reads as 0, 0x4c4870), so the appended codes are '
             'never read: the converted styles carry the XML1 numbers instead (npc_values.resolve_style, SPEC 24)')


def _bolton_anims(ctx, b):
    """append XML1 data/boltonactoranims <actor_skin> entries (name = bolt-on anim DB) absent from XML2's,
    renamed with map_animdb; only entries whose anim DB exists in the output."""
    if ctx.x1_path('data/boltonactoranims.xml') is None or not ctx.base_exists('Data/boltonactoranims.XMLB'):
        return
    x2 = ctx.read_base_xmlb('Data/boltonactoranims.XMLB')
    have = {(e.get('name') or '').lower() for e in x2}
    added, skipped = [], []
    for e in ctx.read_x1_xml('data/boltonactoranims.xml').iter():
        if e.tag.lower() != 'actor_skin' or not e.get('name'):
            continue
        mapped = C.map_animdb(e.get('name').lower())
        if mapped in have:
            continue
        if not b.exists(f'actors/{mapped}.igb'):
            skipped.append(e.get('name'))
            continue
        ne = copy.deepcopy(e)
        ne.set('name', mapped)
        x2.append(ne)
        have.add(mapped)
        added.append(mapped)
    if added:
        ctx.write_xmlb('Data/boltonactoranims', x2, ('.XMLB',), source=ctx.x1_path('data/boltonactoranims.xml'))
    ctx.set_count('bolton_anims_added', len(added))
    ctx.note(f'boltonactoranims: appended XML1 bolt-on anim maps {added} (XML2 entries kept); skipped {skipped} '
             f'(their anim DBs are not on the XML1 disc)')


def _engb_shadow_guard(ctx, b):
    """A non-localized XML1 .xml is written as .XMLB only. If XML2 ships a same-stem .engb (which the English
    game may read for that name), write the same bytes there too so XML2's stale copy never shadows ours
    (the same guard zones applies to its imports)."""
    n = 0
    for key, e in sorted(ctx.registry.owned_by(ctx.module).items()):
        if not key.endswith('.xmlb'):
            continue
        stem = key[:-len('.xmlb')]
        base_engb = ctx.base_index.get(stem + '.engb')
        if not base_engb or (stem + '.engb') in ctx.registry:
            continue
        ctx.write_bytes(base_engb, (ctx.out / e['rel']).read_bytes(), source=e['source'])
        ctx.note(f'{base_engb}: XML2 file replaced by a copy of {e["rel"]} so it cannot shadow the XML1 data')
        n += 1
    ctx.set_count('engb_shadow_fixed', n)


def _report_npc_powerups(ctx, b):
    """SPEC 22.7: counts / notes of heroes.convert_npc_powerups over the styles written here. XML1 herostat styles are
    counted apart (with the npcstat heroes the heroes module seats, heroes.ROSTER_NPC): the heroes module rewrites
    those files from XML1 with its own collapse (SPEC_heroes 4)."""
    from . import heroes as H                      # noqa: WPS433
    heroes = set()
    for rel, names in (('data/herostat.eng', None), ('data/npcstat.eng', {n.lower() for n in H.ROSTER_NPC})):
        try:
            root = ctx.read_x1_xml(rel)
        except KeyError:
            continue
        heroes |= {C.norm(f'data/powerstyles/{s.get("powerstyle").lower()}') for s in root.iter()
                   if s.get('powerstyle') and (names is None or (s.get('name') or '').lower() in names)}
    written = {C.norm(rel) for rel in b.styles_written.values()}
    total, hero_total, styles = collections.Counter(), collections.Counter(), {}
    losses, warnings, notes = [], [], []
    for rel, (changes, rep) in sorted(b.npc_powerups.items()):
        if rel not in written or not changes:
            continue
        if C.split_ext(rel)[0] in heroes:
            hero_total.update(changes)
            continue
        total.update(changes)
        styles[C.split_ext(rel)[0].rsplit('/', 1)[-1]] = dict(sorted(changes.items()))
        losses += rep['losses']
        warnings += rep['warnings']
        notes += rep['notes']
        for e in rep['errors']:
            ctx.error(f'NPC powerups: {e}')
        for u in rep['unverified_affecters']:
            ctx.warn(f'NPC powerups: affecter {u} is registered in XMen2.exe but no XML2 retail style uses it '
                     f'(UNVERIFIED)')
    applied = sum(v for k, v in total.items() if k.startswith('npc_powerup:'))
    removals = sum(v for k, v in total.items() if k.startswith('npc_powerup_remove:'))
    ctx.set_count('npc_powerups_converted', applied)
    ctx.set_count('npc_powerup_removals_converted', removals)
    ctx.set_count('npc_powerup_tag_names', total.get('npc_powerup_tag_name', 0))
    ctx.set_count('npc_powerup_styles', len(styles))
    ctx.note(f'NPC powerups (SPEC 22.7, heroes.convert_npc_powerups): {applied} XML1-form powerup triggers and '
             f'{removals} XML1 removals in {len(styles)} NPC styles converted to the XML2 <affecter> / remove_tag form '
             f'(the buff value codes resolved to XML1 numbers, powerusage included, SPEC 24): '
             f'{dict(sorted(total.items()))}; XML1 hero styles (rewritten by heroes): '
             f'{sum(hero_total.values())} changes')
    for msg in losses:
        ctx.note(f'NPC powerups: {msg}')
    for msg in warnings:
        ctx.warn(f'NPC powerups: {msg}')
    b.detail['npc_powerups'] = {'styles': styles, 'losses': losses, 'warnings': warnings, 'notes': notes}


def _report_npc_codes(ctx, b):
    """SPEC 24: counts of npc_values.resolve_style over the NPC styles written here (the XML1 hero styles the
    heroes module rewrites from XML1 with its own resolver are counted apart, as in _report_npc_powerups)."""
    from . import heroes as H                      # noqa: WPS433
    heroes = set()
    for rel, names in (('data/herostat.eng', None), ('data/npcstat.eng', {n.lower() for n in H.ROSTER_NPC})):
        try:
            root = ctx.read_x1_xml(rel)
        except KeyError:
            continue
        heroes |= {C.norm(f'data/powerstyles/{s.get("powerstyle").lower()}') for s in root.iter()
                   if s.get('powerstyle') and (names is None or (s.get('name') or '').lower() in names)}
    written = {C.norm(rel) for rel in b.styles_written.values()}
    total, hero_total, per_style, problems = collections.Counter(), collections.Counter(), {}, []
    for rel, (codes, probs) in sorted(b.npc_codes.items()):
        if rel not in written:
            continue
        if C.split_ext(rel)[0] in heroes:
            hero_total.update(codes)
            continue
        problems += probs
        if codes:
            total.update(codes)
            per_style[C.split_ext(rel)[0].rsplit('/', 1)[-1]] = {k: v for k, v in sorted(codes.items())
                                                                  if not k.startswith('code:')}
    for p in problems:
        ctx.error(f'NPC value codes: {p}')
    attrs = {k: v for k, v in total.items() if not k.startswith('code:')}
    for k in NV.REPORTED_ATTRS + ('other',):
        ctx.set_count(f'npc_codes_{k}', attrs.get(k, 0))
    ctx.set_count('npc_codes_resolved', sum(attrs.values()))
    ctx.set_count('npc_code_styles', len(per_style))
    by_code = dict(sorted((k[5:], v) for k, v in total.items() if k.startswith('code:')))
    hero_n = sum(v for k, v in hero_total.items() if not k.startswith('code:'))
    ctx.note(f'NPC value codes (SPEC 24, npc_values.resolve_style): {sum(attrs.values())} XML1 codes in '
             f'{len(per_style)} NPC styles resolved to the XML1 numbers {dict(sorted(attrs.items()))} (XMen2.exe '
             f'read them as 0: no base damage / knockback / energy cost); codes {by_code}; XML1 hero styles '
             f'(rewritten by heroes): {hero_n}')
    b.detail['npc_codes'] = {'styles': per_style, 'attrs': attrs, 'problems': problems}


def _report_styles(ctx, b):
    try:
        cc = ctx.research_json('characters/combat_compat.json')
    except FileNotFoundError:
        cc = {}
    uh = {h: v for h, v in cc.get('unknown_handlers', {}).items() if h not in CE.HANDLER_RENAME}
    written = {C.split_ext(rel)[0].rsplit('/', 1)[1]: mapped for (kind, mapped), rel in b.styles_written.items()}
    handler_styles = sorted(written[s] for s in {s for v in uh.values() for s in v} if s in written)
    # the combat rewrite x1schema applied to the styles written here (combat_events.rewrite_style, SPEC 22)
    x1_rels = {C.norm(rel) for rel in b.styles_written.values()}
    combat = collections.Counter()
    for kind, files in ctx.schema_log.items():
        if kind.startswith('combat_'):
            combat[kind] += sum(n for r, n in files.items() if r in x1_rels)
    combat = {k: v for k, v in sorted(combat.items()) if v}
    ctx.set_count('combat_events_rebased', sum(v for k, v in combat.items() if k.startswith('combat_event:')))
    ctx.set_count('combat_handlers_renamed', sum(v for k, v in combat.items() if k.startswith('combat_handler:')))
    ctx.set_count('combat_affecters_renamed', sum(v for k, v in combat.items() if k.startswith('combat_affecter:')))
    ctx.note(f'combat rewrite (x1schema -> combat_events.rewrite_style, SPEC 22) in the styles written here: {combat}; '
             f'every trigger / event name then resolves to a registered ce_* type except the allowlisted XML1 no-ops '
             f'(validator V18)')
    _report_npc_powerups(ctx, b)
    _report_npc_codes(ctx, b)
    ctx.defer(f'{len(b.styles_written)} converted XML1 styles keep XML1 combat semantics: power-system review '
              f'pending (powers rework). {len(handler_styles)} use FightMove handlers XMen2.exe lacks and XML2 has no '
              f'counterpart for (they run as %default%: the move without its logic; combat_events.'
              f'UNREGISTERED_HANDLER_NOTES): {handler_styles}')
    shared_fs = sorted(k for (kind, k), v in b.styles.items() if kind == 'fightstyles' and v and
                       (kind, v) not in b.styles_written)
    ctx.note(f'fightstyles shared with XML2 by name (XML2 versions used): {shared_fs}; XML1 fightstyle_gun_rifle '
             f'has 9 anim names XML2\'s lacks (research collisions)')
    ctx.set_count('styles_review_pending', len(b.styles_written))
