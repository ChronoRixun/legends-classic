"""V44: complete-roster TalentRegistry demand and the stock loader's path/ID contract.

NPC powers/immunities stay in shared_talents. Hero NPCs retain their own precache except
explicitly reviewed noncombat props when the zone/possible party would overflow100/9.
Unknown file names share the default ID100 interval; formatted paths have a63-byte limit.
"""
import itertools
from . import common as C
from . import style_budget as SB
from . import actor_budget as AB
from . import talent_sets as TS

TALENTS = 100
FILES = 9
SHARED_CAP = 99               # 0x4c05d0 ids 0..98: the shared loader's exclusive upper bound

# Reviewed scene props, not fighting NPCs or required/seatable mission heroes.
# Party files still load normally. Only excess *zone* precache is removed.
PROP_HERO_ROLES = {
    'xjet/blackbird_arbiter': {
        name: 'noncombat Blackbird scene prop; not a forced mission party member'
        for name in ('cyclops', 'phoenix', 'storm', 'wolverine')
    },
}


def loader_problems(files, known_names):
    """The formatted 64-byte path and the default character's ID100 interval."""
    out, default = [], []
    known = {n.lower() for n in known_names}
    for rel in sorted(set(files)):
        rel = C.norm(rel)
        if rel == 'data/shared_talents':
            continue
        if not rel.startswith('data/talents/'):
            out.append(f'{rel}: talent path is not data/talents/<name>')
            continue
        name = rel[len('data/talents/'):]
        formatted = f'data/talents/{name}.xmlb'
        if len(formatted.encode('latin-1')) > 63:
            out.append(f'{formatted}: formatted talent path exceeds 63 bytes (64-byte loader buffer)')
        if '/' in name:
            out.append(f'{formatted}: nested talent paths are not supported by the zone loader')
        if name not in known or name == 'default':
            default.append(rel)
    if len(default) > 1:
        out.append(f'multiple default-ID-interval talent files (ID100): {", ".join(default)}')
    return out


def prune_props(base, eligible, parties, counts):
    """Remove only explicitly reviewed props, and only while the party budget overflows."""
    kept, dropped = set(base), {}
    total, _ = worst_party(kept, parties, counts)
    if problems(total):
        for rel in sorted(set(eligible) & kept):
            kept.remove(rel)
            dropped[rel] = eligible[rel]
    return kept, dropped


def mission_parties(ctx, zone, parties):
    """Actual forced seats plus later joins; otherwise preserve the four-hero bound."""
    if ctx is None or not hasattr(ctx, 'args'):
        return parties, None
    from . import scripts as S
    try:
        mission = S._x1_world_mission(ctx, zone)
        row = S.forced_party_plan(ctx).get(mission, {})
        if C.forced_teams_mode(ctx) == 'seat' and row.get('status') == 'seat':
            names = set(row['seat']) | {n.lower() for n in S.JOIN_LATER.get(mission, ())}
            return {n: parties[n] for n in names if n in parties}, mission
    except (AttributeError, FileNotFoundError, KeyError):
        pass
    return parties, None


def _canon(el):
    return (el.tag, tuple(sorted(el.attrib.items())), tuple(_canon(c) for c in el))


def package_talents(entries):
    return {C.norm(fn or '') for kind, fn in entries or ()
            if (kind or '').lower() == 'xml_talents' and fn}


def demand(files, counts):
    files = set(files)
    missing = sorted(files - counts.keys())
    if missing:
        raise ValueError('unknown talent file: ' + ', '.join(missing))
    values = [counts[f] for f in files]
    # Runtime lookup reuses an already registered talent name even if another file lists it.
    # Integer counts are useful for synthetic disjoint fixtures; production passes actual name sets.
    if all(isinstance(v, int) for v in values):
        total = sum(values)
    elif all(isinstance(v, (set, frozenset)) for v in values):
        total = len(set().union(*values))
    else:
        raise ValueError('talent demand needs all counts or all name sets')
    return dict(talents=total, files=len(files))


def problems(total):
    out = []
    if total['talents'] > TALENTS:
        out.append(f"{total['talents']} demanded unique talent names > {TALENTS}")
    if total['files'] > FILES:
        out.append(f"{total['files']} talent files > {FILES}")
    return out


def worst_party(base, heroes, counts, size=4):
    names = sorted(heroes)
    best, who = demand(base, counts), ()
    file_max, file_party = best['files'], ()
    for party in itertools.combinations(names, min(size, len(names))):
        d = demand(set(base).union(*(heroes[h] for h in party)), counts)
        if d['files'] > file_max:
            file_max, file_party = d['files'], party
        if (d['talents'], d['files']) > (best['talents'], best['files']) or not who:
            best, who = d, party
    best['files'] = file_max
    best['file_party'] = file_party
    return best, who


def _script_text_of(v, ref):
    r = C.norm(ref)
    ctx = getattr(v, 'ctx', None)
    cands = []
    if ctx is not None:
        out_rel = ctx.out_index.get(C.script_rel(r)) if hasattr(ctx, 'out_index') else None
        if out_rel:
            cands.append(ctx.out / out_rel)
        try:
            cands.append(ctx.research_path('scripts/out/scripts') / (r + '.py'))
        except (AttributeError, FileNotFoundError):
            pass
        try:
            path = ctx.x1_path(f'scripts/{r}.py')
            if path is not None:
                cands.append(path)
        except (AttributeError, FileNotFoundError):
            pass
    for path in cands:
        if path.is_file():
            return path.read_text(encoding='utf-8', errors='replace')
    return None


def zone_roster(v, zone, pkg, known):
    """Full CHRB / spawner / script closure / course roster, including hero NPCs."""
    roster = set(SB._chr_names(v, zone))
    for ext in ('.engb', '.xmlb'):
        roster |= TS.map_spawn_roster(v.tree(f'maps/{zone}{ext}'))
    roster |= TS.dangerroom_zone_roster(v.tree('data/dangerroom.engb'), zone)
    refs = [C.script_ref(fn) for kind, fn in pkg or () if (kind or '').lower() == 'script']
    closed = TS.script_closure_refs(refs, lambda r: _script_text_of(v, r))
    roster |= TS.script_zone_roster({r: _script_text_of(v, r) for r in closed}, lambda n: n in known)
    return roster


def prune_zone_precache(ctx, zone, root):
    """Emitter policy: only the reviewed scene can shed unnecessary zone talent loads."""
    roles = PROP_HERO_ROLES.get(C.norm(zone))
    if not roles:
        return root
    from . import heroes as H
    files = package_talents([(e.tag, e.get('filename')) for e in root]) | {'data/shared_talents'}
    plan = H.hero_plan(ctx)
    parties = {n.lower(): {f'data/talents/{n.lower()}'} for n in plan['heroes']}
    parties, mission = mission_parties(ctx, zone, parties)
    counts = {}
    for rel in files | set().union(*parties.values()):
        tree = ctx.read_out_xmlb(rel + '.engb')
        counts[rel] = frozenset(e.get('name').lower() for e in tree.iter('talent'))
    eligible = {f'data/talents/{name}': reason for name, reason in roles.items()
                if not mission or name not in parties}
    kept, dropped = prune_props(files, eligible, parties, counts)
    dropped_styles = {f"data/powerstyles/{plan['style'][name]}" for name in roles
                      if f'data/talents/{name}' in dropped and name in plan['style']}
    for e in list(root):
        filename = C.norm(e.get('filename', ''))
        if ((e.tag.lower() == 'xml_talents' and filename in dropped) or
                (e.tag.lower() == 'fightstyle' and filename in dropped_styles)):
            root.remove(e)
    if dropped:
        ctx.shared.setdefault('talent_precache_drops', {})[zone] = dropped
        ctx.note(f'{zone}: removed noncombat hero NPC precache to fit TalentRegistry: {dropped}; '
                 f'removed early prop styles {sorted(dropped_styles)} so party styles bind after their talents')
    return root


def validate(v, ck):
    ck.set('talent_capacity', TALENTS)
    ck.set('file_capacity', FILES)
    counts = {}

    def count(files):
        for rel in files:
            ln = C.norm(rel)
            if ln not in counts:
                tree = v.tree(ln + '.engb')
                if tree is None:
                    tree = v.tree(ln + '.xmlb')
                if tree is None:
                    raise ValueError('unknown talent file: ' + ln)
                counts[ln] = frozenset((e.get('name') or '').lower() for e in tree.iter()
                                       if e.tag.lower() == 'talent')
                if '' in counts[ln]:
                    raise ValueError('talent without a name in ' + ln)
        return files

    def entries(rel):
        return count(package_talents(SB._entries(v, rel)))

    shared = set(v.stats()['talents']['.engb'] or [])
    counts['data/shared_talents'] = frozenset(shared)
    if len(shared) > SHARED_CAP:
        ck.error(f'data/shared_talents: {len(shared)} talents > shared loader {SHARED_CAP} IDs')
    permanent = {'data/shared_talents'}
    for rel in SB.PERMANENT_PKGS:
        permanent.update(entries(rel + '.pkgb'))
    heroes = SB._heroes(v)
    hero_names = {name for name, _ in heroes}
    parties = {off: {name: entries(SB.CHARACTER_PKG.format(name=name, skin=skin, nc='_nc' if off else ''))
                     for name, skin in heroes} for off in (False, True)}
    by_name = v.stats()['by_name']
    npc_refs = {}
    tree = v.tree('data/npcstat.engb')
    if tree is None:
        ck.error('data/npcstat.engb missing or undecodable')
    try:
        base = {(e.get('name') or '').lower(): _canon(e)
                for e in v.ctx.read_base_xmlb('Data/npcstat.engb').iter('stats')}
    except Exception:          # synthetic validators need no source install
        base = {}
    for st in tree.iter('stats') if tree is not None else ():
        name = (st.get('name') or '').lower()
        if name and not (name in base and _canon(st) == base[name]):
            npc_refs[name] = {(e.get('name') or '').lower() for e in st.iter('talent')}
    global_names = shared | set().union(*(counts[f] for fs in parties[False].values() for f in fs))
    for name, refs in sorted(npc_refs.items()):
        for ref in sorted(refs - global_names):
            ck.error(f'npcstat {name}: talent {ref} resolves neither in shared_talents nor a hero file')
    for rel in v.idx.under('data/talents'):
        if rel.rsplit('/', 1)[-1].lower().startswith('npc_') and rel.lower().endswith(('.engb', '.xmlb')):
            ck.error(f'{rel}: NPC set/union files are forbidden; NPC talents belong in shared_talents')
    known = set(by_name) | hero_names | {'default'}
    zone_list = set(v.converted_zones())
    for rel in v.idx.under('packages/generated/maps'):
        if rel.lower().endswith('.pkgb'):
            zone_list.add(C.norm(rel)[len('packages/generated/maps/'):-5])
    high, rows, drops = 0, {}, {}
    for zone in sorted(zone_list):
        pkg = v.zone_pkg(zone)
        if pkg is None:
            continue
        actual = permanent | count(package_talents(pkg))
        roster = zone_roster(v, zone, pkg, known | set(npc_refs))
        expected = set(actual)
        npc_hero_files = set()
        for name in sorted(roster):
            if name in hero_names:
                rel = f'data/talents/{name}'
                count({rel})
                expected.add(rel)
                npc_hero_files.add(rel)
            elif name in by_name:
                skin = (by_name[name][1].get('skin') or '').strip()
                if skin:
                    fs = entries(SB.CHARACTER_PKG.format(name=name, skin=skin, nc=''))
                    actual |= fs
                    expected |= fs
        party_files, mission = mission_parties(getattr(v, 'ctx', None), zone, parties[AB.combat_off(pkg)])
        roles = PROP_HERO_ROLES.get(zone, {})
        eligible = {f'data/talents/{name}': reason for name, reason in roles.items()
                    if not mission or name not in party_files}
        expected, removed = prune_props(expected, eligible, party_files, counts)
        for rel in sorted(npc_hero_files - expected):
            if rel in actual:
                ck.error(f'{zone}: unnecessary prop file {rel} still precached despite budget overflow')
        for rel in sorted(npc_hero_files & expected - actual):
            ck.error(f'{zone}: {rel} not listed in zone package for a fighting/seatable hero NPC')
        if removed:
            drops[zone] = removed
            ck.notes.append(f'{zone}: dropped {removed}; noncombat props only, party files retained') if hasattr(ck, 'notes') else None
            for name in roles:
                if f'data/talents/{name}' not in removed or name not in by_name:
                    continue
                style = C.norm('data/powerstyles/' + by_name[name][1].get('powerstyle', ''))
                if any(k.lower() == 'fightstyle' and C.norm(f) == style for k, f in pkg):
                    ck.error(f'{zone}: dropped {name} talents but still registers {style} before party talents '
                             '(saved-load power binding regression)')
        total, party = worst_party(expected, party_files, counts)
        all_files = expected | set().union(*(party_files[h] for h in party))
        for issue in loader_problems(all_files, known):
            ck.error(f'{zone}: {issue}')
        available = set().union(*(counts[f] for f in expected))
        for name in sorted(roster):
            for ref in sorted(npc_refs.get(name, set()) - available):
                ck.error(f'{zone}: npcstat {name}: talent {ref} resolves nowhere in loaded shared/hero files')
        high = max(high, total['talents'])
        ck.count('zones_checked')
        for issue in problems(total):
            ck.error(f'{zone}: {issue}; party {", ".join(party)}; registry would refuse registration')
        if total['talents'] == TALENTS or total['files'] == FILES:
            ck.warn(f'{zone}: TalentRegistry exactly full: {total}')
        rows[zone] = {'talents': total['talents'], 'files': total['files'], 'party': list(party),
                      'forced_mission': mission, 'dropped_prop_files': removed}
    ck.details['zones'] = rows
    ck.details['dropped_prop_files'] = drops
    ck.set('talents_demand_max', high)
    ck.set('shared_pool', len(shared))
    ck.set('npc_set_files', 0)
