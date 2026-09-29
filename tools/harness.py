"""Install / remove the xml2-fix test harness in a finished build (never in the real XML2 install).

usage:
  harness.py install <out> [--mode windowed|borderless|fullscreen] [--width 1280] [--height 720]
                           [--no-pipe] [--dll PATH] [--stock-opening] [--save-folder NAME] [--limits]
                           [--forced-teams [1|0|off]] [--add-hero] [--no-join-hero]
  harness.py remove  <out>
  harness.py status  <out>

Why: the game runs exclusive fullscreen and switches the desktop's display mode, and the old harness forced the
game window to the foreground (gameinput.focus) - both lock the owner out of the PC during long runs. The xml2-fix
dinput.dll (branch `display`) adds [Display] Mode/Width/Height/RunInBackground and a [Test] InputPipe keyboard
channel, so a build can run in a small background window and be driven without focus (tools/fixinput.py).

tools/build_xml1.py never ships proxy files (validator V1 errors on dinput.dll / xml2-fix.* in <out>, and the sweep
removes them), so this is a post-build step: re-run it after every build_xml1.py run. It refuses to touch the
real XML2 install. (Builds made by the builder, tools/xml1builder, keep the proxy files and merge the port's keys -
xml1build/fix_ini.py, the same keys this writes - into the player's xml2-fix.ini.)
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# default: a Release build of an xml2-fix checkout next to this repository ($XML2FIX_DLL overrides it)
sys.path.insert(0, HERE)
import local_paths  # noqa: E402  $XML2FIX_DLL / $XML2_DIR, else local_paths.json
DEFAULT_DLL = local_paths.xml2fix_dll(os.path.normpath(
    os.path.join(HERE, '..', '..', 'xml2-fix', 'build', 'bin', 'Release', 'dinput.dll')))
REAL_INSTALL = os.path.normcase(os.path.abspath(local_paths.xml2_dir()))
MARKER = '; written by xml1-port tools/harness.py - remove with: harness.py remove <out>'


def _check_out(out):
    out = os.path.abspath(out)
    if os.path.normcase(out) == REAL_INSTALL:
        sys.exit('refusing to touch the real XML2 install')
    if not os.path.isfile(os.path.join(out, 'XMen2.exe')):
        sys.exit(f'{out}: no XMen2.exe (not a build directory)')
    return out


# The port's keys (and how they are read off a build) live in xml1build/fix_ini.py, shared with the builder
# (tools/xml1builder), so the harness and the shipped build cannot drift (BUILDER_DESIGN.md 3.5). The names below are
# kept for the tools that import them from here (frontend_selftest U2, ...).
sys.path.insert(0, HERE)
from xml1build import fix_ini as FI  # noqa: E402

PLAY_SAVE_FOLDER, TEST_SAVE_FOLDER = FI.PLAY_SAVE_FOLDER, FI.TEST_SAVE_FOLDER
FORCED_TEAMS_VALUES = FI.FORCED_TEAMS_VALUES
POSTGAME_SCRIPT = FI.POSTGAME_SCRIPT
MAIN_MENU_ITEMS, MAIN_MENU_MOUSE_SLOTS = FI.MAIN_MENU_ITEMS, FI.MAIN_MENU_MOUSE_SLOTS
MAIN_MENU_8TH_MARKER = FI.MAIN_MENU_8TH_MARKER
PORT_WINDOW_TITLE, PORT_END_HERO_UNLOCK = FI.PORT_WINDOW_TITLE, FI.PORT_END_HERO_UNLOCK
PORT_GAME_VERSION = FI.PORT_GAME_VERSION
MAIN_MENU_FILE, NEW_GAME_PLUS = FI.MAIN_MENU_FILE, FI.NEW_GAME_PLUS
REVIEW_STATS, REVIEW_MENU_FILE, REVIEW_STATS_LABEL = FI.REVIEW_STATS, FI.REVIEW_MENU_FILE, FI.REVIEW_STATS_LABEL
XP_CURVE, BUILD_REPORT = FI.XP_CURVE, FI.BUILD_REPORT
build_xp_curve, menu_items_for, build_menu_items = FI.build_xp_curve, FI.menu_items_for, FI.build_menu_items
review_stats_for, build_review_stats = FI.review_stats_for, FI.build_review_stats


def dll_has(dll, marker):
    """True when the xml2-fix DLL file contains `marker` (a key name only newer builds read)."""
    try:
        with open(dll, 'rb') as f:
            return marker in f.read()
    except OSError:
        return False


def ini_text(mode, width, height, pipe, xml1_opening=True, save_folder=None, limits=False, forced_teams='1',
             add_hero=False, postgame=None, main_menu_items=None, xp_curve=None, join_hero=True, pipe_name=None,
             online_server=None, log_network=False, new_game_plus=None, discord=None, port_identity=False,
             review_stats=None):
    """a whole test xml2-fix.ini: the harness's own [Display] / [Test] / [Discord] / [Debug] test settings around the
    port's [Game] / [Limits] / [Online] keys (fix_ini)."""
    lines = [MARKER, '[Display]', f'Mode={mode}', f'Width={width}', f'Height={height}', 'Topmost=0',
             'RunInBackground=1', '', '[Test]', f'InputPipe={1 if pipe else 0}']
    if pipe_name:
        # a second game instance serves its own pipe; tools/fixinput.py reaches it with XML2FIX_PIPE=<name>, and the
        # build-driven tools (tour_runner / campaign_walk / power_sweep) read it from here (fixinput.use_build)
        lines.append(f'PipeName={pipe_name}')
    lines.append('')
    online = []
    if online_server:
        # every GameSpy host the game looks up resolves to this address (a local OpenSpy stack for online tests)
        online.append(f'Server={online_server}')
    online += [f'{k}={v}' for k, v in FI.online_keys(port_identity=port_identity).items()]
    if online:
        lines += ['[Online]'] + online + ['']
    game = FI.game_keys(xml1_opening=xml1_opening, save_folder=save_folder, forced_teams=forced_teams,
                        add_hero=add_hero, join_hero=join_hero, postgame=postgame, port_identity=port_identity,
                        main_menu_items=main_menu_items, new_game_plus=new_game_plus, review_stats=review_stats,
                        xp_curve=xp_curve)
    if game:
        lines += ['[Game]'] + [f'{k}={v}' for k, v in game.items()] + ['']
    if limits:
        lines += ['[Limits]'] + [f'{k}={v}' for k, v in FI.LIMITS.items()] + ['']
    if discord is not None:
        # xml2-fix Discord Rich Presence is on by default (the launcher's toggle writes this key); harness test games
        # leave Owen's Discord status alone unless --discord asks for it
        lines += ['[Discord]', f'Enabled={1 if discord else 0}', '']
    lines += ['[Debug]', 'LogFiles=0'] + (['LogNetwork=1'] if log_network else []) + ['']
    return '\r\n'.join(lines)


def install(a):
    out = _check_out(a.out)
    dll = os.path.abspath(a.dll)
    if not os.path.isfile(dll):
        sys.exit(f'{dll} not found - build xml2-fix branch display first (cmake --build build --config Release)')
    shutil.copy2(dll, os.path.join(out, 'dinput.dll'))
    postgame = None if a.stock_opening else FI.build_postgame(out)   # an XML1 build: the campaign ends with XML1's
    # the XML1 front end's main menu: the mouse and Quit through xml2-fix (Play Online's mouse slot with a DLL for it)
    main_menu_items = build_menu_items(out, dll_has(dll, MAIN_MENU_8TH_MARKER))
    new_game_plus = NEW_GAME_PLUS if main_menu_items else None   # ... and its New Game: no New Game+ choice (XML1)
    xp_curve = build_xp_curve(out)             # XML1's XP amounts: XML1's levels and kill XP through xml2-fix
    review_stats = build_review_stats(out)     # XML1's review menu (no Stats tab): the tab change wraps at 4
    with open(os.path.join(out, 'xml2-fix.ini'), 'w', encoding='utf-8', newline='') as f:
        save_folder = a.save_folder or (PLAY_SAVE_FOLDER if a.no_pipe else TEST_SAVE_FOLDER)
        f.write(ini_text(a.mode, a.width, a.height, not a.no_pipe, not a.stock_opening, save_folder, a.limits,
                         a.forced_teams, a.add_hero, postgame, main_menu_items, xp_curve, not a.no_join_hero,
                         a.pipe_name, a.online_server, a.log_network, new_game_plus,
                         # a test install (pipe on): presence off unless --discord; the play build (--no-pipe) keeps
                         # the default (on) unless --no-discord
                         True if a.discord else (False if (a.no_discord or not a.no_pipe) else None),
                         bool(postgame),        # an XML1 build: the port's title, ending and online version
                         review_stats))
    if a.add_hero and a.forced_teams != '1':
        print('note: AddHero only acts with ForcedTeams=1 (xml2fixFeature("addhero") reports 0 otherwise)')
    print(f'harness installed in {out}: dinput.dll from {dll}; Mode={a.mode} {a.width}x{a.height} '
          f'RunInBackground=1 InputPipe={0 if a.no_pipe else 1} ForcedTeams={a.forced_teams} '
          f'AddHero={1 if a.add_hero else 0} JoinHero={0 if a.no_join_hero else "(default 1)"} '
          f'PostgameScript={postgame or "(none)"} '
          f'MainMenuItems={main_menu_items or "(none)"} NewGamePlus={new_game_plus or "(none)"} '
          f'XPCurve={xp_curve or "(none)"} ReviewStats={review_stats or "(none)"}')


def remove(a):
    out = _check_out(a.out)
    for name in ('dinput.dll', 'xml2-fix.ini', 'xml2-fix.log'):
        p = os.path.join(out, name)
        if os.path.exists(p):
            os.remove(p)
            print('removed', p)


def status(a):
    out = _check_out(a.out)
    for name in ('dinput.dll', 'xml2-fix.ini', 'xml2-fix.log'):
        p = os.path.join(out, name)
        print(f'{name}: {"present" if os.path.exists(p) else "absent"}')
    ini = os.path.join(out, 'xml2-fix.ini')
    if os.path.isfile(ini):
        print(open(ini, encoding='utf-8').read())


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    i = sub.add_parser('install')
    i.add_argument('out')
    i.add_argument('--mode', choices=('windowed', 'borderless', 'fullscreen'), default='windowed')
    i.add_argument('--width', type=int, default=1280)
    i.add_argument('--height', type=int, default=720)
    i.add_argument('--no-pipe', action='store_true')
    i.add_argument('--dll', default=DEFAULT_DLL)
    i.add_argument('--limits', action='store_true', help='xml2-fix [Limits]: actor table 127, resource names 1024')
    i.add_argument('--stock-opening', action='store_true',
                   help='leave New Game as XML2 has it (no NewGameTeam / ResetUnlocks / SaveFolder)')
    i.add_argument('--forced-teams', dest='forced_teams', nargs='?', const='1', default='1',
                   choices=FORCED_TEAMS_VALUES,
                   help='[Game] ForcedTeams (SPEC 19): 1 = the XML1 forced parties (default; the bare flag is 1 too), '
                        '0 = the functions report off (team menu), off = no key (nothing patched)')
    i.add_argument('--add-hero', dest='add_hero', action='store_true',
                   help='[Game] AddHero=1: the XML1 joins seat the hero mid-zone through xml2-fix addHero '
                        '(experimental; default off = the T7 team menu)')
    i.add_argument('--no-join-hero', dest='no_join_hero', action='store_true',
                   help='[Game] JoinHero=0: the XML1 joins open the T7 team menu instead of xml2-fix joinHero '
                        '(the reload with the hero added; on by default with ForcedTeams=1)')
    i.add_argument('--save-folder', help=f'Documents/Activision/<name> for saves + profile (default: "{PLAY_SAVE_FOLDER}" '
                                          f'with --no-pipe, the play build; "{TEST_SAVE_FOLDER}" otherwise)')
    i.add_argument('--pipe-name', help='[Test] PipeName: this instance\'s test pipe (a second game window; '
                                       'fixinput.py reaches it with XML2FIX_PIPE=<name>; tour_runner.py, '
                                       'campaign_walk.py and power_sweep.py take it from the build)')
    i.add_argument('--online-server', help='[Online] Server: resolve every GameSpy host to this IPv4 '
                                           '(a local OpenSpy stack, e.g. 127.0.0.1)')
    i.add_argument('--log-network', action='store_true', help='[Debug] LogNetwork=1: log the game\'s GameSpy traffic')
    i.add_argument('--discord', action='store_true', help='[Discord] Enabled=1: Rich Presence on in a test install '
                                                          '(test installs write Enabled=0 by default)')
    i.add_argument('--no-discord', action='store_true', help='[Discord] Enabled=0 even in the play build')
    i.set_defaults(fn=install)
    for name, fn in (('remove', remove), ('status', status)):
        s = sub.add_parser(name)
        s.add_argument('out')
        s.set_defaults(fn=fn)
    a = ap.parse_args()
    a.fn(a)


if __name__ == '__main__':
    main()
