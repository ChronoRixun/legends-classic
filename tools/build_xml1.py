"""Build an XML1-on-XML2 install: copy the XML2 base install, run the xml1build modules, validate.

usage: python tools/build_xml1.py --out <dir> [--base "<XML2 folder>"] [--start-zone <zone>]
                                  [--tour <seconds>] [--no-movies] [--only <module,...>] [--no-validate]
                                  [--test-ini] [--adopt] [--jobs N]
                                  [--blackbird menu|chooseteam] [--npc-scaling off|xml2curve]
                                  [--hero-roster 21|17|21xml2] [--hero-icons xml1|generic] [--hero-bleed on|off]
                                  [--newgame chooseteam|keepteam] [--forced-teams seat|menu]
                                  [--start-party h1,h2 [--start-skinset costume:heroes]] [--frontend xml1|xml2]
                                  [--xp-curve xml1|xml2]
                                  [--sources developer|prepared [--cache DIR] [--iso IMAGE]]

Steps (tools/xml1build/SPEC.md section 2):
  1. sync <out> from the base install (xml2-fix proxy never copied; *.sfd skipped with --no-movies); only
     changed files are copied, so rebuilding into the same <out> is fast and restores replaced base files.
     With --only, outputs of the modules NOT listed are carried over from the previous build's registry;
     files the previous build's test hooks overrode are carried only with the same --start-zone/--tour, else
     their module is re-run as well (plan_carry).
  2. run the content modules in order: characters, heroes, scripts, zones, media, frontend (each
     xml1build.<name>.run(ctx)); heroes (SPEC_heroes.md) replaces XML2's stand-in herostat with the XML1 roster and
     patches the characters output, so --only characters implies heroes; frontend (SPEC 21) writes XML1's main menu
     and the Danger Room / Review / codex / trivia / credits tables (nothing with --frontend xml2).
  3. testhooks (only with --start-zone / --tour): new-game jump (with --start-party: the SPEC 19 seat block) and/or
     the zone tour (+ <out>/_tour.json).
  4. sweep files that are neither base files nor registered this build, save <out>/_build/registry.json.
  5. validate (xml1build.validate.run) and heroes.validate_out (V-H1..V-H12) unless --no-validate; save
     <out>/_build/report.json.
Inputs (--sources, tools/xml1build/sources.py, SPEC.md section 27):
  developer (default): the repo's xml1_loose / xml1_assets / xml1_xbox folders and research/ (as always).
  prepared: the prepare stages' cache (--cache DIR): P1 `disc` reads the XML1 Xbox disc image (--iso: a Redump
     image or an XISO; cached by content, so --iso is needed only when the cache has no prepared disc) into the three
     XML1 trees (the movie files only without --no-movies), P2 `tables` regenerates mission_plan / collisions /
     x2_stats_refs / names_xml1 from them and --base, P3 `scripts` rewrites the XML1 scripts, P4 `sound` converts
     and merges the sound banks, P5 `music` rebuilds the music banks (--jobs worker processes). Each stage is
     reused while its inputs are unchanged. Only the tracked research tables (API tables, graph.json, ...) come
     from research/.
Exit code: 0 = no errors, 1 = module failure or validator errors (or a prepare stage failed), 2 = refused (unsafe
--out etc.), 3 = input not usable (prepared mode: the disc image or the cache; BUILDER_DESIGN.md 2.2).
"""
import argparse
import importlib
import json
import os
import sys
import time
from pathlib import Path

from xml1build import common as C  # noqa: E402  (tools/ = this script's folder, sys.path[0]; the builder imports us)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', required=True, help='output install directory (created / updated in place)')
    ap.add_argument('--base', default=str(C.DEFAULT_BASE), help='XML2 PC install to copy (read-only)')
    ap.add_argument('--start-zone', dest='start_zone', help='New Game jumps straight to this zone (e.g. nyc/alison/nyc1_1_1)')
    ap.add_argument('--tour', type=float, help='smoke-test tour: every reachable zone waits N seconds, then loads the next')
    ap.add_argument('--no-movies', dest='no_movies', action='store_true', help='leave out all .sfd movies (base and XML1)')
    ap.add_argument('--only', help='comma list of content modules to run: ' + ','.join(C.MODULE_ORDER))
    ap.add_argument('--no-validate', dest='no_validate', action='store_true')
    ap.add_argument('--test-ini', dest='test_ini', action='store_true',
                    help='windowed mode + engine reporting in alchemy.ini, and a .codegpt-game.json launch manifest')
    ap.add_argument('--adopt', action='store_true',
                    help='allow building into an existing non-empty directory that was not made by this tool')
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) // 2), help='worker threads modules may use')
    ap.add_argument('--blackbird', choices=('menu', 'chooseteam'), default='menu',
                    help="mission starts: keep XML1's blackbirdMenu team menu (default) or use loadMapChooseTeam "
                         "(fallback if the menu never runs its stored loadMapKeepTeam)")
    ap.add_argument('--npc-scaling', dest='npc_scaling', choices=('off', 'xml2curve'), default='off',
                    help="XML1 enemies: keep XML1's level/stats (default) or add XML2's per-level specific_* + "
                         "monst_dmg_high")
    ap.add_argument('--tiles', choices=('used', 'folder'), default='used',
                    help="zone packages list only the tile models the zone's tile instances can name (default; "
                         "SPEC 13, XMen2.exe's 200-record IGB cache) or the whole models/tiles/<x> folder")
    ap.add_argument('--hero-roster', dest='hero_roster', choices=('21', '17', '21xml2'), default='21',
                    help="herostat: default + 15 XML1 heroes + hidden Magneto placeholder + 3 hidden pads + "
                         "ProfXGladiator (the promoted XML1 npcstat hero, stats index 21) (21, the count XML2 always "
                         "shipped); 17 drops the pads (18 entries); 21xml2 uses XML2's Deadpool/Ironman/Professorx/"
                         "Sunfire as pads and has no ProfXGladiator (A/B builds; SPEC_heroes.md)")
    ap.add_argument('--hero-icons', dest='hero_icons', choices=('xml1', 'generic'), default='xml1',
                    help="hero talent icons: XML1's 2x2 <hero>_all atlases (default) or XML2's generic talent_icons.png")
    ap.add_argument('--hero-bleed', dest='hero_bleed', choices=('on', 'off'), default='on',
                    help="Wolverine's bleed passive as an XML2 add_harming powerup (default) or dropped")
    ap.add_argument('--newgame', choices=('chooseteam', 'keepteam'), default='keepteam',
                    help="New Game hook: XML1's opening, Wolverine alone, Cyclops joins in nyc1_1_3 (default "
                         "keepteam; needs xml2-fix 1.2+ with [Game] NewGameTeam=wolverine, ResetUnlocks=0 - "
                         "tools/harness.py writes them) or the team menu before nyc1_1_1 (chooseteam)")
    ap.add_argument('--forced-teams', dest='forced_teams', choices=('seat', 'menu'), default='seat',
                    help="XML1's forced parties (SPEC 19): every forced mission start emits the xml2-fix seat block "
                         "with the team menu as its else branch, side missions push/pop the party, the joins try "
                         "addHero first (default seat; xml2-fix [Game] ForcedTeams=1 picks the seat branch, "
                         "tools/harness.py writes it) or no xml2-fix call at all (menu)")
    ap.add_argument('--start-party', dest='start_party',
                    help='with --start-zone: New Game unlocks these heroes (comma list, herostat names) and seats '
                         'them through the forced-teams seat block (test hook, SPEC 19.5; needs xml2-fix [Game] '
                         'ForcedTeams=1)')
    ap.add_argument('--start-skinset', dest='start_skinset',
                    help='with --start-party: setSkinset costume:heroes for that start (e.g. civilian:magma)')
    ap.add_argument('--frontend', choices=C.FRONTEND_MODES,
                    default=(os.environ.get(C.FRONTEND_ENV) or C.FRONTEND_DEFAULT).lower()
                    if (os.environ.get(C.FRONTEND_ENV) or C.FRONTEND_DEFAULT).lower() in C.FRONTEND_MODES
                    else C.FRONTEND_DEFAULT,
                    help="front end (SPEC 21): XML1's main menu (Cerebro backdrop, 3D logo, XML1 buttons + Quit), "
                         "intro logos, menu music, Danger Room courses, Review / codex / trivia / credits data "
                         "(xml1, the default; also $XML1BUILD_FRONTEND) or XML2's front end exactly as before SPEC 21 "
                         "(xml2, the A/B fallback)")
    ap.add_argument('--xp-curve', dest='xp_curve', choices=C.XP_CURVE_MODES,
                    default=(os.environ.get(C.XP_CURVE_ENV) or C.XP_CURVE_DEFAULT).lower()
                    if (os.environ.get(C.XP_CURVE_ENV) or C.XP_CURVE_DEFAULT).lower() in C.XP_CURVE_MODES
                    else C.XP_CURVE_DEFAULT,
                    help="the XP curve the game runs (SPEC 23.1): xml1 (the default; also $XML1BUILD_XP_CURVE) = "
                         "xml2-fix [Game] XPCurve=xml1, which tools/harness.py writes, and XML1's own XP amounts where "
                         "the pipeline chooses one (Danger Room completion 0, XP pickups their XML1 count); xml2 = "
                         "XMen2.exe's curve (no XPCurve key) with the XML2-scaled amounts (Danger Room rewardxp by "
                         "XML2's reclevel curve, XP pickup 5000)")
    ap.add_argument('--sources', choices=('developer', 'prepared'), default='developer',
                    help="where the inputs come from: the repo's xml1_* folders and research/ (developer, the default) "
                         "or the prepare stages' cache (prepared: needs --cache, and --iso unless the cache already "
                         "holds a prepared disc)")
    ap.add_argument('--cache', help='prepared mode: the prepare cache directory (created; kept between builds)')
    ap.add_argument('--iso', help='prepared mode: the XML1 Xbox disc image (Redump .iso or XISO; read-only)')
    a = ap.parse_args(argv)
    if a.sources == 'prepared' and not a.cache:
        ap.error('--sources prepared needs --cache DIR')
    if a.sources != 'prepared' and (a.cache or a.iso):
        ap.error('--cache / --iso are for --sources prepared')
    if (a.start_party or a.start_skinset) and not a.start_zone:
        ap.error('--start-party / --start-skinset need --start-zone')
    if a.start_skinset and not a.start_party:
        ap.error('--start-skinset needs --start-party')
    if a.only:
        sel = [m.strip().lower() for m in a.only.split(',') if m.strip()]
        bad = [m for m in sel if m not in C.MODULE_ORDER]
        if bad:
            ap.error(f'--only: unknown module(s) {bad}; choose from {C.MODULE_ORDER}')
        if 'characters' in sel and 'heroes' not in sel and 'heroes' in C.MODULE_ORDER:
            sel.append('heroes')              # heroes rewrites characters' npcstat / shared_talents / hero styles
            print('[build] --only characters implies heroes (it patches the characters output)')
        a.only = [m for m in C.MODULE_ORDER if m in sel]
    if a.tour is not None and a.tour <= 0:
        ap.error('--tour needs a positive number of seconds')
    if a.start_zone:
        a.start_zone = C.norm(a.start_zone).removeprefix('maps/')
    return a


def check_out_dir(out: Path, adopt: bool):
    """Refuse to take over a non-empty directory we did not create (the sweep deletes unknown files)."""
    if not out.exists():
        return
    if not out.is_dir():
        raise SystemExit(f'--out {out} exists and is not a directory')
    if (out / '_build').is_dir() or not any(out.iterdir()):
        return
    if adopt:
        return
    raise SystemExit(f'--out {out} is not empty and has no _build/ marker; pass --adopt to take it over '
                     f'(files that are not XML2 base files will be DELETED)')


HOOK_OWNER = 'testhooks'
# content options: option -> (the module whose output depends on it, default). A carried-over module output
# built with a different value is stale, so that module is re-run (plan_content_opts).
CONTENT_OPTS = {'blackbird': ('scripts', 'menu'), 'npc_scaling': ('characters', 'off'), 'tiles': ('zones', 'used'),
                'hero_roster': ('heroes', '21'), 'hero_icons': ('heroes', 'xml1'), 'hero_bleed': ('heroes', 'on'),
                'newgame': ('scripts', 'keepteam'),
                # SPEC 19: scripts emits the blocks; zones imports the dialogs / conversations rewrite_data_tree patches
                'forced_teams': (('scripts', 'zones'), 'seat'),
                # SPEC 21: scripts (intro, main_back_main, imageViewer literals), zones (menu/main_back, zoneinfo
                # loading, arena nosave, DR reward items), media (menu music), frontend (menus + data tables)
                'frontend': (('scripts', 'zones', 'media', 'frontend'), C.FRONTEND_DEFAULT),
                # SPEC 23.1: zones (the XP pickup items / entities), frontend (Danger Room rewardxp)
                'xp_curve': (('zones', 'frontend'), C.XP_CURVE_DEFAULT)}
# what a build made before an option existed (no key in its report.json) effectively used
LEGACY_OPT_VALUES = {'tiles': 'folder',          # zone packages listed whole tile folders before SPEC 13
                     'forced_teams': 'menu',     # no xml2-fix calls before SPEC 19
                     'frontend': 'xml2',         # XML2's front end before SPEC 21
                     'xp_curve': 'xml2'}         # XML2-scaled Danger Room / XP pickup amounts before SPEC 23.1


def _prev_build(out: Path):
    try:
        return json.loads((out / '_build' / 'report.json').read_text(encoding='utf-8'))['build']
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _prev_hook_opts(out: Path):
    """(start_zone, tour, start_party, start_skinset) of the previous build in <out> (from _build/report.json), or
    None if unknown."""
    b = _prev_build(out)
    if b is None:
        return None
    try:
        return (b.get('start_zone'), b.get('tour'), b.get('start_party'), b.get('start_skinset'))
    except AttributeError:
        return None


def plan_content_opts(out: Path, args, selected):
    """modules whose carried-over output was built with other CONTENT_OPTS values (they must re-run)."""
    prev = _prev_build(out)
    if not isinstance(prev, dict):
        return []
    rerun = []
    for opt, (mods, default) in CONTENT_OPTS.items():
        was = prev.get(opt, LEGACY_OPT_VALUES.get(opt, default))
        now = getattr(args, opt, default)
        for mod in ((mods,) if isinstance(mods, str) else mods):
            if was != now and mod not in selected and mod not in rerun:
                rerun.append(mod)
                print(f'[build] re-running {mod}: --{opt.replace("_", "-")} changed ({was} -> {now})')
    return rerun


def hook_content_owner(entry):
    """The content module whose file testhooks overrode: the last content module in the entry's history, else
    (history lost, e.g. a registry written before carry-over handled hooks) the SPEC owner of the path:
    Scripts/** -> scripts, Maps/** and Packages/generated/maps/** -> zones. None for the files testhooks creates
    itself (Scripts/x1/tour/**, _tour.json)."""
    content = [h for h in entry.get('history', []) if h in C.MODULE_ORDER]
    if content:
        return content[-1]
    n = C.norm(entry['rel'])
    if n == '_tour.json' or n.startswith('scripts/x1/tour/'):
        return None
    if n.startswith('scripts/'):
        return 'scripts'
    if n.startswith(('maps/', 'packages/generated/maps/')):
        return 'zones'
    return None


def plan_carry(prev, selected, out: Path, same_hooks: bool):
    """Which files of the previous build are carried over, and which extra modules must re-run.

    Content-module outputs of modules that are not selected are carried. Files testhooks overrode (owner
    'testhooks'; content owner per hook_content_owner, e.g. zones for a tour stop's Maps/<zone>.XMLB, scripts
    for menus/new_game.py) hold HOOKED content:
      * if their content module is selected they are not carried (it rewrites them, testhooks re-hooks them);
      * else, with the same --start-zone/--tour as the previous build, they are carried and testhooks re-applies
        its (idempotent) patches;
      * otherwise their content module must re-run, else sync_base would restore XML2's new_game.py and the
        sweep would delete the tour-stop zone files. That module is added to the selection.
    Files testhooks creates itself (Scripts/x1/tour/**, _tour.json) are never carried: testhooks rewrites them
    whenever hooks are given, and without hooks they are stale. A carried hooked entry gets its content owner
    back into 'history' if that was lost (validate V6 reads it).
    Returns (carry {norm rel: entry}, list of modules added)."""
    selected = list(selected)
    added = []
    while True:
        carry, rerun = {}, set()
        for k, e in prev.entries.items():
            if not (out / e['rel']).is_file():
                continue
            owner = e['owner']
            if owner in C.MODULE_ORDER:
                if owner not in selected:
                    carry[k] = e
                continue
            if owner != HOOK_OWNER:
                continue                                    # 'build' files (alchemy.ini, ...) are re-applied
            orig = hook_content_owner(e)
            if orig is None or orig in selected:
                continue            # testhooks' own files are rewritten whenever hooks are given; else swept
            if same_hooks:
                hist = list(e.get('history', []))
                if orig not in hist:
                    hist.append(orig)
                carry[k] = dict(e, history=hist)            # testhooks runs again with the same options
            else:
                rerun.add(orig)
        if not rerun:
            return carry, added
        for m in C.MODULE_ORDER:
            if m in rerun and m not in selected:
                selected.append(m)
                added.append(m)


def apply_test_ini(ctx):
    rel = ctx.out_index.get('alchemy.ini')
    if rel:
        text = (ctx.out / rel).read_text(encoding='latin-1')
        text = text.replace('fullScreen = true', 'fullScreen = false')
        text = text.replace('defaultReportLevel = kNone', 'defaultReportLevel = kInfo')
        ctx.write_bytes(rel, text.encode('latin-1'))
    manifest = {'name': 'xml1-on-xml2', 'engine': 'generic',
                'launch': {'cmd': (ctx.out / 'XMen2.exe').as_posix(), 'args': []},
                'log': {'stdout': True}, 'window': 'X-Men Legends 2', 'sourceRoots': [C.TOOLS.as_posix()]}
    ctx.write_bytes('.codegpt-game.json', json.dumps(manifest, indent=2).encode('utf-8'))


def make_sources(args, base: Path):
    """the build's Sources: developer mode, or the prepare stages' cache (runs P1-P5 where their cached output is
    missing or stale). Raises prepare.PrepareError when the image / cache is not usable, prepare.StageFailed when a
    stage cannot make a correct output."""
    if args.sources != 'prepared':
        return C.Sources.developer(base)
    from xml1build import prepare
    return prepare.prepared_sources(Path(args.cache), base, iso=Path(args.iso) if args.iso else None,
                                    jobs=args.jobs, movies=not args.no_movies, log=print)


def main(argv=None):
    args = parse_args(argv)
    out = Path(args.out).resolve()
    base = Path(args.base).resolve()
    if not (base / 'XMen2.exe').is_file():
        print(f'--base {base} does not look like an XML2 install (no XMen2.exe)', file=sys.stderr)
        return 2
    protected = None
    if args.sources == 'prepared':
        protected = (C.X1_LOOSE, C.X1_ASSETS, C.X1_XBOX, C.RESEARCH, C.TOOLS, Path(args.cache).resolve())
    try:
        C._check_out_safe(out, base, protected)
        check_out_dir(out, args.adopt)
    except (ValueError, SystemExit) as e:
        print(f'refused: {e}', file=sys.stderr)
        return 2
    t0 = time.time()
    try:
        sources = make_sources(args, base)
    except Exception as e:  # noqa: BLE001 - prepare.PrepareError (input not usable) or an I/O error on the image
        from xml1build import prepare
        if isinstance(e, prepare.StageFailed):
            print(f'prepare failed: {e}', file=sys.stderr)
            return 1
        if not isinstance(e, (prepare.PrepareError, OSError)):
            raise
        print(f'input not usable: {e}', file=sys.stderr)
        return 3
    out.mkdir(parents=True, exist_ok=True)
    (out / '_build').mkdir(exist_ok=True)
    sources_meta = out / '_build' / 'sources.json'
    if sources.mode == 'developer':
        sources_meta.unlink(missing_ok=True)        # a developer build records nothing (standalone tools: developer)
    else:
        sources_meta.write_text(json.dumps(sources.describe(), indent=1), encoding='utf-8')

    selected = list(args.only) if args.only else list(C.MODULE_ORDER)
    opt_rerun = plan_content_opts(out, args, selected)
    if opt_rerun:
        selected = [m for m in C.MODULE_ORDER if m in selected or m in opt_rerun]
    prev = C.Registry.load(out / '_build' / 'registry.json')
    hooks_now = (args.start_zone, args.tour, args.start_party, args.start_skinset)
    same_hooks = bool(args.start_zone or args.tour) and _prev_hook_opts(out) == hooks_now
    carry, forced = plan_carry(prev, selected, out, same_hooks)
    if forced:
        selected = [m for m in C.MODULE_ORDER if m in selected or m in forced]
        print(f'[build] re-running {forced}: the previous build hooked their files with other '
              f'--start-zone/--tour options (prev={_prev_hook_opts(out)}, now={hooks_now})')
    if carry:
        print(f'[build] carrying over {len(carry)} files from previous build of '
              f'{sorted({e["owner"] for e in carry.values()})}')

    C.sync_base(base, out, skip_sfd=args.no_movies, keep=set(carry))
    ctx = C.BuildContext(out, base, args=args, registry=C.Registry(carry), sources=sources)
    ctx.shared['selected_modules'] = selected
    if args.test_ini:
        apply_test_ini(ctx)

    ok = True
    for name in C.MODULE_ORDER:
        if name not in selected:
            ctx.report.mod(name)['status'] = 'skipped' if name not in {e['owner'] for e in carry.values()} else 'carried'
            continue
        try:
            mod = importlib.import_module(f'xml1build.{name}')
        except ModuleNotFoundError as e:
            if e.name == f'xml1build.{name}':
                ctx.report.mod(name)['status'] = 'missing'
                ctx.report.add(name, 'errors', f'module tools/xml1build/{name}.py not implemented')
                ok = False
                continue
            raise
        ok &= C.run_step(ctx, name, mod.run)

    if args.start_zone or args.tour:
        from xml1build import testhooks
        ok &= C.run_step(ctx, 'testhooks', testhooks.run)
    if not args.tour and (out / '_tour.json').is_file():
        (out / '_tour.json').unlink()           # metadata is never swept; drop a stale tour list explicitly

    C.sweep_stale(out, ctx.base_index, ctx.registry, skip_sfd=args.no_movies)
    ctx.out_index.scan()
    (out / '_build' / 'registry.json').write_text(json.dumps(ctx.registry.to_json(), indent=0), encoding='utf-8')

    if not args.no_validate:
        try:
            validate = importlib.import_module('xml1build.validate')
            ok &= C.run_step(ctx, 'validate', validate.run)
        except ModuleNotFoundError as e:
            if e.name != 'xml1build.validate':
                raise
            ctx.report.mod('validate')['status'] = 'missing'
            ctx.report.add('validate', 'errors', 'module tools/xml1build/validate.py not implemented')
            ok = False
        # the hero roster's own checks (V-H1..V-H12, SPEC_heroes.md) read <out> after the sweep like validate
        try:
            heroes = importlib.import_module('xml1build.heroes')
            ok &= C.run_step(ctx, 'heroes_validate', heroes.validate_out)
        except ModuleNotFoundError as e:
            if e.name != 'xml1build.heroes':
                raise

    rep = ctx.report.to_json()
    rep['build'] = {'out': out.as_posix(), 'base': base.as_posix(), 'selected': selected,
                    'forced_rerun': list(forced) + list(opt_rerun),
                    'start_zone': args.start_zone, 'tour': args.tour, 'no_movies': args.no_movies,
                    'blackbird': args.blackbird, 'npc_scaling': args.npc_scaling, 'tiles': args.tiles,
                    'hero_roster': args.hero_roster, 'hero_icons': args.hero_icons, 'hero_bleed': args.hero_bleed,
                    'newgame': args.newgame, 'forced_teams': args.forced_teams, 'frontend': args.frontend,
                    'xp_curve': args.xp_curve,
                    'start_party': args.start_party, 'start_skinset': args.start_skinset,
                    'files_registered': len(ctx.registry.entries), 'seconds': round(time.time() - t0, 1),
                    'shared_keys': sorted(ctx.shared)}
    (out / '_build' / 'report.json').write_text(json.dumps(rep, indent=1, default=str), encoding='utf-8')
    ctx.report.print_summary()
    errors = ctx.report.error_total()
    print(f'[build] {out}: {len(ctx.registry.entries)} files written/registered, {errors} errors, '
          f'{time.time() - t0:.0f}s -> {"OK" if ok and not errors else "FAILED"}')
    return 0 if ok and not errors else 1


if __name__ == '__main__':
    sys.exit(main())
