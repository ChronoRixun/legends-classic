"""xml1build.testhooks - test-only hooks for build_xml1.py --start-zone / --tour (SPEC.md section 7).

--start-zone Z : Scripts/menus/new_game.py and new_game_hard.py (XMen2.exe startFirstMission runs them after
                 setting up its own 4-hero roster, 0x4a7c42/0x4a7c57) become
                     setCurrentAct(<act of Z>) ; loadMapKeepTeam("Z")
--start-party h1,h2 [--start-skinset costume:heroes]  (with --start-zone; SPEC 19.5)
               : unlockCharacter(h, "") for each hero (as the begin bodies unlock their REQUIRED heroes), then the
                 load becomes the forced-teams seat block (FORCED_TEAMS_DESIGN 3.8): with xml2-fix [Game]
                 ForcedTeams=1 seatParty(h1, h2, ...) + setSkinset(costume, heroes) + loadMapKeepTeam("Z"), else
                 loadMapChooseTeam("Z") - a forced-team start in any zone without playing up to it.
--tour N       : every converted zone reachable from New Game (research/sweep/graph.json order, starting at
                 --start-zone if given) gets a wrapper zone script Scripts/x1/tour/<zone>.py
                     waittimed(N) ; loadZone("<next zone>", "")
                 set as its world entity's zonescript (Maps/<zone>.XMLB/.engb) and listed in its PKGB.
                 The zone's own script is NOT run in tour mode (a load/render/spawn smoke test; the own
                 script could queue its own loadmap/movie and break the chain). New Game jumps to stop 1.
                 <out>/_tour.json lists the order for the orchestrator.
Runs after the content modules and overrides files they own (replace=True).
"""
from . import common as C
from . import scripts_transform as T

SKINSET_COSTUMES = ('default', 'astonishing', 'aoa', '60s', '70s', 'weaponx', 'future', 'winter', 'civilian')  # 0x6d8aa0


def start_party_args(ctx):
    """(seat [names], costume, heroes) from --start-party / --start-skinset, or None when --start-party is absent.
    Problems are ctx errors (then None)."""
    party = ctx.opt('start_party')
    if not party:
        if ctx.opt('start_skinset'):
            ctx.error('--start-skinset needs --start-party')
        return None
    if C.forced_teams_mode(ctx) != 'seat':
        ctx.error('--start-party needs --forced-teams seat (the menu build registers no xml2-fix function)')
        return None
    seat = []
    for h in str(party).split(','):
        h = h.strip().lower()
        if h and h not in seat:
            seat.append(h)
    if not seat or len(seat) > 4:
        ctx.error(f'--start-party {party!r}: 1 to 4 hero names')
        return None
    try:
        from . import heroes as H                              # noqa: WPS433
        known = set(H.hero_plan(ctx)['x1'])
    except Exception:          # noqa: BLE001
        known = None
    if known is not None and any(h not in known for h in seat):
        ctx.error(f'--start-party {party!r}: {[h for h in seat if h not in known]} are not heroes of this build\'s '
                  f'herostat {sorted(known)} (seatParty would refuse the whole party)')
        return None
    costume, heroes = 'default', ''
    if ctx.opt('start_skinset'):
        costume, _, heroes = str(ctx.opt('start_skinset')).partition(':')
        costume = costume.strip().lower()
        heroes = ','.join(h.strip().lower() for h in heroes.split(',') if h.strip())
        if costume not in SKINSET_COSTUMES:
            ctx.error(f'--start-skinset {ctx.opt("start_skinset")!r}: costume must be one of {SKINSET_COSTUMES}')
            return None
    return seat, costume, heroes


def _zone_act(ctx, zone):
    try:
        acts = ctx.research_json('scripts/out/zone_acts.json')
    except FileNotFoundError:
        return 1
    z = acts.get(zone) or {}
    if z.get('inject_act'):
        return int(z['inject_act'])
    if z.get('acts'):
        return int(z['acts'][0])
    return 1


def _converted_zones(ctx):
    """zones with both Maps/<zone>.XMLB and Packages/generated/maps/<zone>.PKGB written this build."""
    shared = ctx.shared.get('zones_converted')
    if shared is not None:
        return list(shared)
    out = []
    for z in ctx.x1_zones():
        if f'maps/{z}.xmlb' in ctx.registry and f'packages/generated/maps/{z}.pkgb' in ctx.registry:
            out.append(z)
    return out


def _has_world(ctx, zone):
    try:
        return C.find_world(ctx.read_out_xmlb(f'Maps/{zone}.XMLB')) is not None
    except (KeyError, ValueError):
        return False


def _new_game(ctx, lines, why):
    body = [f'# xml1-port test hook: {why}'] + lines
    for name in ('new_game', 'new_game_hard'):
        ctx.write_script(f'Scripts/menus/{name}.py', body, replace=True)


def run(ctx):
    start = ctx.opt('start_zone')
    dwell = ctx.opt('tour')
    converted = _converted_zones(ctx)
    conv_set = set(converted)

    if start and start not in conv_set and f'maps/{start}.xmlb' not in ctx.out_index:
        ctx.error(f'--start-zone {start}: no converted zone and no Maps/{start}.XMLB in <out>')
        start = None

    party = start_party_args(ctx) if (ctx.opt('start_party') or ctx.opt('start_skinset')) else None
    if party is not None and (not start or dwell):
        ctx.error('--start-party needs --start-zone (and no --tour)')
        party = None
    if not dwell:
        if start:
            act = _zone_act(ctx, start)
            if party is not None:
                seat, costume, heroes = party
                # the seated heroes are unlocked first, as XML1's begin bodies unlock their REQUIRED heroes before
                # the seat block (decision 7.4; begin_mansion1: unlockCharacter("magma", "") ... seatParty("magma"))
                unlock = [f'unlockCharacter("{h}", "" )' for h in seat]
                load = T.seat_block('', seat, costume, heroes, start)
                why = f'--start-zone {start} --start-party {",".join(seat)} --start-skinset {costume}:{heroes}'
                _new_game(ctx, [f'setCurrentAct({act} )'] + unlock + load, why)
                ctx.note(f'new_game(_hard).py -> setCurrentAct({act}), unlockCharacter {seat}, forced-teams seat block: '
                         f'{T.seat_party_call(seat)} {T.set_skinset_call(costume, heroes)} loadMapKeepTeam("{start}") '
                         f'(else loadMapChooseTeam; xml2-fix [Game] ForcedTeams=1 picks the seat branch)')
                ctx.set_count('start_party_hook', 1)
            else:
                _new_game(ctx, [f'setCurrentAct({act} )', f'loadMapKeepTeam("{start}" )'], f'--start-zone {start}')
                ctx.note(f'new_game(_hard).py -> setCurrentAct({act}), loadMapKeepTeam("{start}")')
        return

    order_src = ctx.tour_order()
    if start:
        order_src = ([start] + [z for z in order_src if z != start]) if start not in order_src else \
            order_src[order_src.index(start):] + order_src[:order_src.index(start)]
    order, skipped = [], {}
    for z in order_src:
        if z not in conv_set and z != start:
            skipped[z] = 'not converted'
        elif not _has_world(ctx, z):
            skipped[z] = 'no world entity in Maps/<zone>.XMLB'
        else:
            order.append(z)
    if not order:
        ctx.error('--tour: no converted zone with a world entity to tour')
        return

    stops = []
    for i, z in enumerate(order):
        nxt = order[i + 1] if i + 1 < len(order) else None
        ref = f'x1/tour/{z}'
        lines = [f'# xml1-port tour stop {i + 1}/{len(order)}: {z}', f'waittimed({float(dwell):.3f} )']
        if nxt:
            lines.append(f'loadZone("{nxt}", "" )')
        else:
            lines.append('# last stop')
        ctx.write_script(C.script_rel(ref), lines)

        def set_script(root, ref=ref):
            w = C.find_world(root)
            if w is None:
                return False
            w.set('zonescript', ref)
            return True

        def add_pkg(root, ref=ref):
            fn = f'scripts/{ref}'
            if any(e.tag == 'script' and (e.get('filename') or '').lower() == fn for e in root):
                return False
            root.append(C.ET.Element('script', {'filename': fn}))
            return True

        ctx.patch_out_xmlb(f'Maps/{z}', set_script, exts=('.XMLB', '.engb'))
        ctx.patch_out_xmlb(f'Packages/generated/maps/{z}', add_pkg, exts=('.PKGB',))
        stops.append({'i': i, 'zone': z, 'next': nxt, 'script': ref})

    act = _zone_act(ctx, order[0])
    _new_game(ctx, [f'setCurrentAct({act} )', f'loadMapKeepTeam("{order[0]}" )'], f'--tour {dwell}s')
    tour = {'dwell_seconds': dwell, 'count': len(order), 'start': order[0], 'order': [s['zone'] for s in stops],
            'stops': stops, 'skipped': skipped,
            'note': 'New Game -> stop 1; each stop waits dwell_seconds after its zone script starts, then '
                    'loadZone(next). Zone scripts of the original zones are not run in tour mode.'}
    ctx.write_json('_tour.json', tour)
    ctx.shared['tour'] = tour
    ctx.set_count('tour_stops', len(order))
    ctx.set_count('tour_skipped', len(skipped))
