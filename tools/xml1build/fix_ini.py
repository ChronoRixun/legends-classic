"""xml1build.fix_ini - the port's keys in xml2-fix.ini (BUILDER_DESIGN.md 3.5).

The xml2-fix DLL (dinput.dll) reads <game>/xml2-fix.ini. Two writers share that file and neither removes the other's
keys:

  the port (this module)  the content requirements of a build - [Game] NewGameTeam / ResetUnlocks / SaveFolder /
                          ForcedTeams / PostgameScript / WindowTitle / EndHeroUnlock / MainMenuItems / NewGamePlus /
                          ReviewStats / XPCurve, [Limits] ActorSlots / ResourceNames, [Online] GameVersion. They are
                          functions of the build's content (the menus it wrote, its report.json, its scripts), so the
                          builder (tools/xml1builder) writes them after a build, and tools/harness.py takes its
                          [Game] / [Limits] / [Online] lines from here too (the harness and the shipped build cannot
                          drift);
  the launcher            the player's preferences - [Display], [Discord], [Online] LocalIP / Server, [Input] ... -
                          written key by key with WritePrivateProfileStringW.

merge_ini() therefore has WritePrivateProfileString semantics: it replaces or adds exactly the given keys (sections and
keys matched case-insensitively, the first matching section wins), deletes only the keys it is told to drop, and keeps
every other section, key, comment, blank line, the line endings and the file's encoding (UTF-16 with a BOM stays
UTF-16; anything else is kept byte for byte). The file is replaced atomically.

port_keys(out) is what a play build needs (the values tools/harness.py install --no-pipe --limits writes, for an
xml2-fix >= 1.2.0: MainMenuItems names the 8th mouse slot, Play Online). PORT_OWNED lists every key the port may write:
a key it owns but does not need for this build is dropped, so an update that stops needing a key removes it."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

# The port's own save folder (xml2-fix [Game] SaveFolder): saves and settings.dat - the profile that keeps hero
# unlocks from game to game, by herostat index - would otherwise be XML2's (Documents\Activision\X-Men Legends 2),
# so the real XML2's unlocks came up as XML1 heroes in the port's team menu. Test runs (tools/harness.py) get a folder
# of their own so tours and pipe tests never unlock heroes in the owner's play profile.
PLAY_SAVE_FOLDER = 'X-Men Legends'
TEST_SAVE_FOLDER = 'X-Men Legends (port tests)'

# xml2-fix [Game] PostgameScript (SPEC 21 D.1): XMen2.exe's endgame credits then run 'runscript <this>' instead of
# loadZone('act5/egypt/egypt6','') (an XML2 zone whose NPCs XML1 mode dropped). The build writes the script
# (scripts.POSTGAME_REF: r505, then the main menu); the key is written only when the build has it.
POSTGAME_SCRIPT = 'x1/menus/postgame'

# xml2-fix [Game] MainMenuItems (SPEC 21.2): XMen2.exe's MAIN_MENU finds its mouse items and its Quit item by XML2's
# names (label_option04..09, debug_text); the XML1 front end's main menu is XML1's, with its text on buttonN
# (xml1build.frontend.MAIN_MENU_ITEMS, the same list; frontend_selftest U2 compares them). The DLL points those name
# operands at ours in this order: label_option04..09's mouse slots, then debug_text (Quit). Without it the keys and
# the pad still work (every button has its usecmd), the mouse and Quit do not. The value is read off the build's
# menu (menu_items_for): its first 6 shown buttons with a usecmd, then the one without (Quit) - button1..7 in builds
# before Play Online (SPEC 21.2.4), button1..6 + button8 since (Play Online, button7, is keys / pad only: XMen2.exe
# clamps the mouse slots after the sixth to Quit, 0x5c944b).
MAIN_MENU_ITEMS = 'button1,button2,button3,button4,button5,button6,button8'
MAIN_MENU_MOUSE_SLOTS = 6
# xml2-fix a3b8567+ (in v1.2.0) takes an 8th name (after Quit): the mouse slot for a 7th usecmd item (Play Online,
# button7), the mouse clamp at 0x5c944b raised from 6 to 8. An older DLL quits when that slot is clicked, so the 8th
# name is only written for a DLL that has the feature (the harness: dll_has(MAIN_MENU_8TH_MARKER); the builder: its
# builds require xml2-fix >= REQUIRED_XML2FIX, which has it).
MAIN_MENU_8TH_MARKER = b'EndHeroUnlock'
MAIN_MENU_FILE = ('UI', 'menus', 'main.XMLB')

# The port's own identity in xml2-fix (a3b8567+), written for XML1 builds (the ones with PostgameScript): the window
# title (the exe says X-Men Legends 2), no XML2 hero unlock + popup after the credits (Deadpool, 0x5b1d4a), and a
# GameSpy game version of its own so port and XML2 lobbies never mix (research/online/port_online_test.md).
PORT_WINDOW_TITLE = 'X-Men Legends'
PORT_END_HERO_UNLOCK = '0'
PORT_GAME_VERSION = 'X1.0'

# xml2-fix [Game] NewGamePlus (SPEC 21.2.2): the XML1 front end's Begin Story runs XMen2.exe's New Game without the
# difficulty prompt (resetgame + setDifficultyLevel(1), xml1build.frontend.BEGIN_STORY_CMD), but once a win on Normal
# has unlocked Hard (the end credits, 0x5b1d44) setDifficultyLevel offers XML2's New Game+ choice (default or saved
# statistics, 0x4a099e) instead of starting. XML1 had none: '0' makes it start with the default statistics, as before
# Hard is unlocked. Written with MainMenuItems (the XML1 front end); --frontend xml2 builds keep XML2's New Game.
NEW_GAME_PLUS = '0'

# xml2-fix [Game] ReviewStats (SPEC 21.4.3): the XML1 front end's Review menu is XML2's without the Stats tab (XML1's
# Review had Screens / Cinematics / Comics / Concepts; XML2's Stats page lists its acts 1-5 from exe code); XMen2.exe's
# tab change (left / right, pad, mouse) wraps at 5, and ReviewStats=0 makes it wrap at 4 so the hidden tab can't be
# reached. Written when the build's UI/menus/review.XMLB is a REVIEW_PATHS_MENU without the Stats tab's label
# (xml1build.frontend.REVIEW_STATS_ITEMS); --frontend xml2 builds keep XML2's menu and get no key.
REVIEW_STATS = '0'
REVIEW_MENU_FILE = ('UI', 'menus', 'review.XMLB')
REVIEW_STATS_LABEL = 'option05_text'

# xml2-fix [Game] XPCurve (SPEC 23, research/heroes/levels.md): the build's objectives, scripts and npcstat carry XML1's
# XP amounts (act 9's crystal objectives 2,000,000, asteroid_m's setXP 1,125,000), which on XMen2.exe's curve take a
# level-1 hero to 40; with XPCurve=xml1 the DLL uses XML1's level table (cap 45) and kill XP (half of each kill to
# every hero, the bench included). Written for every build_xml1.py build (its _build/report.json) - unless the build
# was made with --xp-curve xml2 (SPEC 23.1: XMen2.exe's own curve with the XML2-scaled amounts), which gets no key.
XP_CURVE = 'xml1'
BUILD_REPORT = ('_build', 'report.json')

# xml2-fix [Limits] (29938a0): actor table 40 -> 127, resource name table 450 -> 1024 (research/limits/);
# 1.3.0: the item manager's enhancement record pool 375 -> 512 (SPEC 32.1 / 32.3: XML2's own table uses 374, so the
# port's 19 Danger Room rewards with their 54 enhancements never loaded; saves store record numbers, so the pool can
# only grow). zones.ITEM_ENHANCEMENT_POOL reads this value: what the shipped ini asks the fix for is the pool the
# build is checked against.
LIMITS = {'ActorSlots': '127', 'ResourceNames': '1024', 'ItemEnhancements': '512'}

# xml2-fix [Game] ForcedTeams (SPEC 19): '1' = the scripts of a --forced-teams seat build seat XML1's parties
# (xml2-fix forced_teams module), '0' = the functions exist but report off (team menu), 'off' = no key (nothing
# patched). Every xml2-fix call sits behind xml2fixFeature("forcedteams") (validate V14b), so with ForcedTeams=0, a
# missing key, an xml2-fix build without the module or no DLL at all, the same scripts open the team menu.
FORCED_TEAMS_VALUES = ('1', '0', 'off')

# the xml2-fix release a builder-made play build needs (every key above is in v1.2.0; v1.3.0: the SKILL pickup's
# addSkillPoints, the conversation hooks [Game] AutoAdvance / ReplyVoices / ReplyCursor - SPEC 32, 34)
# Planned companion release: ObjectiveDescriptions (SPEC 47). Do not release against 1.3.0.
REQUIRED_XML2FIX = '1.3.2'

# every key the port may write (the builder drops the ones a build does not need); the launcher owns the rest
PORT_OWNED = {'Game': ('NewGameTeam', 'ResetUnlocks', 'SaveFolder', 'ForcedTeams', 'PostgameScript', 'WindowTitle',
                       'EndHeroUnlock', 'MainMenuItems', 'NewGamePlus', 'ReviewStats', 'XPCurve', 'ObjectiveDescriptions'),
              'Limits': ('ActorSlots', 'ResourceNames', 'ItemEnhancements'),
              'Online': ('GameVersion',)}


# ------------------------------------------------------------------------------------------------ reading the build
def _xmlb_decode(data):
    import xmlb                                       # tools/xmlb.py (tools/ is on sys.path with this package)
    return xmlb.decode(data)


def _read_menu(out, parts):
    p = Path(out).joinpath(*parts)
    if not p.is_file():
        return None
    try:
        return _xmlb_decode(p.read_bytes())
    except (ValueError, OSError, IndexError):
        return None


def menu_items_for(root, eighth=False):
    """The MainMenuItems value when the menu tree `root` is the XML1 front end's main menu (a MAIN_MENU whose shown
    text items are buttonN: the first MAIN_MENU_MOUSE_SLOTS with a usecmd, then the one without, Quit; with `eighth`
    (a DLL that takes 8 names) a 7th usecmd item follows Quit), else None."""
    if root is None or root.get('type') != 'MAIN_MENU':
        return None
    shown = [it for it in root.iter('item') if it.get('text') and not it.get('type')
             and (it.get('hide') or '').lower() != 'true' and (it.get('enabled') or '').lower() != 'false']
    if not shown or any(not re.fullmatch(r'button\d+', it.get('name') or '') for it in shown):
        return None
    mouse = [it.get('name') for it in shown if it.get('usecmd')][:MAIN_MENU_MOUSE_SLOTS]
    quit_ = [it.get('name') for it in shown if not it.get('usecmd')]
    if len(mouse) != MAIN_MENU_MOUSE_SLOTS or len(quit_) != 1:
        return None
    extra = [it.get('name') for it in shown if it.get('usecmd')][MAIN_MENU_MOUSE_SLOTS:MAIN_MENU_MOUSE_SLOTS + 1]
    return ','.join(mouse + quit_ + (extra if eighth else []))


def build_menu_items(out, eighth=False):
    """MainMenuItems when the build's UI/menus/main.XMLB is the XML1 front end's main menu (--frontend xml1), else
    None (--frontend xml2 keeps XML2's menu, whose names XMen2.exe already knows)."""
    return menu_items_for(_read_menu(out, MAIN_MENU_FILE), eighth)


def review_stats_for(root):
    """REVIEW_STATS when the menu tree `root` is a REVIEW_PATHS_MENU without the Stats tab's label (the XML1 front
    end's review menu), else None (XML2's menu, or no review menu)."""
    if root is None or root.get('type') != 'REVIEW_PATHS_MENU':
        return None
    names = {it.get('name') for it in root.iter('item')}
    return REVIEW_STATS if REVIEW_STATS_LABEL not in names and 'option01_text' in names else None


def build_review_stats(out):
    """REVIEW_STATS when the build's UI/menus/review.XMLB is the XML1 front end's (no Stats tab), else None."""
    return review_stats_for(_read_menu(out, REVIEW_MENU_FILE))


def build_record(out) -> dict | None:
    """the 'build' block of <out>/_build/report.json, or None when <out> is no build_xml1 / builder build."""
    p = Path(out).joinpath(*BUILD_REPORT)
    if not p.is_file():
        return None
    try:
        b = json.loads(p.read_text(encoding='utf-8')).get('build')
    except (OSError, ValueError, AttributeError):
        return {}
    return b if isinstance(b, dict) else {}


def build_xp_curve(out):
    """XP_CURVE when <out> is a build_xml1.py build (XML1's XP amounts) made for it (report.json build.xp_curve 'xml1';
    a build from before the option carried no key and XML1's objective XP: XP_CURVE too), else None."""
    b = build_record(out)
    if b is None:
        return None
    chosen = str(b.get('xp_curve') or XP_CURVE).lower()
    return XP_CURVE if chosen == XP_CURVE else None


def build_postgame(out):
    """POSTGAME_SCRIPT when the build wrote XML1's postgame script (an XML1 build), else None."""
    return POSTGAME_SCRIPT if Path(out, 'Scripts', *POSTGAME_SCRIPT.split('/')).with_suffix('.py').is_file() else None


def build_forced_teams(out):
    """'1' for a --forced-teams seat build (the default; a build without the report counts as one), None for menu."""
    b = build_record(out) or {}
    return '1' if str(b.get('forced_teams') or 'seat').lower() == 'seat' else None


def game_keys(*, xml1_opening=True, save_folder=None, forced_teams='1', add_hero=False, join_hero=True, postgame=None,
              port_identity=False, main_menu_items=None, new_game_plus=None, review_stats=None, xp_curve=None) -> dict:
    """the [Game] keys, in the order tools/harness.py always wrote them (a dict: insertion order)."""
    game = {'ObjectiveDescriptions': '1'}
    if xml1_opening:
        # XML1's opening: startFirstMission seats Wolverine alone, resetgame unlocks nobody (xml2-fix new_game.cpp;
        # the build's New Game hook uses loadMapKeepTeam - build_xml1.py --newgame keepteam, the default)
        game.update(NewGameTeam='wolverine', ResetUnlocks='0')
        if save_folder:
            game['SaveFolder'] = save_folder
    if forced_teams in ('0', '1'):
        game['ForcedTeams'] = forced_teams
    if add_hero:
        # xml2-fix addHero (the dormant 0x46c9f0) for the XML1 joins; experimental - T7 (team menu) stays the fallback
        game['AddHero'] = '1'
    if not join_hero:
        # xml2-fix joinHero (the joins' reload with the hero added, no team menu) is on with ForcedTeams=1 unless 0:
        # JoinHero=0 makes the joins fall back to the T7 team menu (SPEC 19.7)
        game['JoinHero'] = '0'
    if postgame:
        game['PostgameScript'] = postgame
    if port_identity:
        game.update(WindowTitle=PORT_WINDOW_TITLE, EndHeroUnlock=PORT_END_HERO_UNLOCK)
    if main_menu_items:
        game['MainMenuItems'] = main_menu_items
    if new_game_plus is not None:
        game['NewGamePlus'] = new_game_plus
    if review_stats is not None:
        game['ReviewStats'] = review_stats
    if xp_curve:
        game['XPCurve'] = xp_curve
    return game


def online_keys(*, port_identity=False) -> dict:
    """the port's [Online] keys: its own GameSpy game version (port lobbies apart from XML2's)."""
    return {'GameVersion': PORT_GAME_VERSION} if port_identity else {}


def port_keys(out, *, save_folder=PLAY_SAVE_FOLDER, eighth=True) -> dict:
    """{section: {key: value}} a play build in <out> needs (= harness.py install --no-pipe --limits for an xml2-fix
    that takes the 8th menu name). Read off the finished build: its menus, report.json and scripts."""
    postgame = build_postgame(out)
    menu = build_menu_items(out, eighth)
    game = game_keys(xml1_opening=True, save_folder=save_folder, forced_teams=build_forced_teams(out) or 'off',
                     postgame=postgame, port_identity=bool(postgame), main_menu_items=menu,
                     new_game_plus=NEW_GAME_PLUS if menu else None, review_stats=build_review_stats(out),
                     xp_curve=build_xp_curve(out))
    keys = {'Game': game, 'Limits': dict(LIMITS)}
    online = online_keys(port_identity=bool(postgame))
    if online:
        keys['Online'] = online
    return keys


def dropped_keys(keys: dict) -> dict:
    """{section: [key, ...]}: the PORT_OWNED keys `keys` does not set (merge_ini's drop for a port write)."""
    out = {}
    for section, owned in PORT_OWNED.items():
        have = {k.lower() for k in keys.get(section, {})}
        gone = [k for k in owned if k.lower() not in have]
        if gone:
            out[section] = gone
    return out


# ------------------------------------------------------------------------------------------------ the ini file
def _decode(raw: bytes):
    """(text, encoding tag) keeping every byte: UTF-16 LE with a BOM (what WritePrivateProfileStringW keeps), else
    latin-1 (a byte-for-byte round trip of any 8-bit or UTF-8 file; the port's values are ASCII)."""
    if raw.startswith(b'\xff\xfe'):
        return raw[2:].decode('utf-16-le'), 'utf-16'
    return raw.decode('latin-1'), 'latin-1'


def _encode(text: str, enc: str) -> bytes:
    return b'\xff\xfe' + text.encode('utf-16-le') if enc == 'utf-16' else text.encode('latin-1')


def _section_name(line: str):
    s = line.strip()
    if s.startswith('[') and ']' in s:
        return s[1:s.index(']')].strip()
    return None


def _key_of(line: str):
    s = line.strip()
    if not s or s[0] in ';#[' or '=' not in s:
        return None
    return s.split('=', 1)[0].strip()


def parse_ini(text: str) -> dict:
    """{section: {key: value}} as GetPrivateProfileString sees it (the first section / key of a name wins; names keep
    their spelling, lookups should use lower())."""
    out, by_lower, cur = {}, {}, None
    for line in text.splitlines():
        name = _section_name(line)
        if name is not None:
            if name.lower() not in by_lower:
                by_lower[name.lower()] = out[name] = {}
            cur = by_lower[name.lower()]
            continue
        key = _key_of(line)
        if cur is not None and key is not None and key.lower() not in {k.lower() for k in cur}:
            cur[key] = line.split('=', 1)[1].strip()
    return out


def read_ini(path) -> dict:
    """parse_ini of a file ({} when it does not exist)."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return {}
    return parse_ini(_decode(raw)[0])


def merge_text(text: str, sections: dict, drop: dict | None = None, newline: str = '\r\n') -> str:
    """text with sections {section: {key: value}} set and drop {section: [key, ...]} removed (see merge_ini)."""
    lines = text.splitlines()
    ends_with_newline = text.endswith(('\n', '\r'))

    def find_section(name):
        return next((i for i, line in enumerate(lines) if (_section_name(line) or '').lower() == name.lower()), None)

    def section_end(start):
        return next((i for i in range(start + 1, len(lines)) if _section_name(lines[i]) is not None), len(lines))

    for section, keys in (drop or {}).items():
        start = find_section(section)
        if start is None:
            continue
        wanted = {k.lower() for k in keys}
        end = section_end(start)
        lines[start + 1:end] = [ln for ln in lines[start + 1:end] if (_key_of(ln) or '').lower() not in wanted]
    for section, keys in sections.items():
        if not keys:
            continue
        start = find_section(section)
        if start is None:
            if lines and lines[-1].strip():
                lines.append('')
            lines.append(f'[{section}]')
            lines += [f'{k}={v}' for k, v in keys.items()]
            continue
        for key, value in keys.items():
            end = section_end(start)
            index = next((i for i in range(start + 1, end) if (_key_of(lines[i]) or '').lower() == key.lower()), None)
            if index is None:
                insert = end
                while insert > start + 1 and not lines[insert - 1].strip():
                    insert -= 1
                lines.insert(insert, f'{key}={value}')
            else:
                lines[index] = f'{lines[index].split("=", 1)[0]}={value}'
    if not lines:
        return ''
    return newline.join(lines) + (newline if ends_with_newline or not text else '')


def merge_ini(path, sections: dict, drop: dict | None = None) -> bool:
    """Set exactly `sections` ({section: {key: value}}) in the ini file at `path` and remove `drop` ({section:
    [key, ...]}), with WritePrivateProfileString semantics (module docstring); creates the file (CRLF, ANSI) when
    missing. Returns True when the file changed."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raw = None
    text, enc = _decode(raw) if raw else ('', 'latin-1')
    newline = '\r\n' if (raw is None or b'\r\n' in raw or b'\r\x00\n\x00' in raw or not text) else '\n'
    merged = merge_text(text, sections, drop, newline)
    data = _encode(merged, enc)
    if raw is not None and data == raw:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'{path.name}.tmp{os.getpid()}')
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return True


def write_port_keys(out, keys: dict | None = None) -> dict:
    """merge the port's keys (default: port_keys(out)) into <out>/xml2-fix.ini, dropping the PORT_OWNED keys it does
    not need; the launcher's keys stay. Returns the keys written."""
    keys = port_keys(out) if keys is None else keys
    merge_ini(Path(out) / 'xml2-fix.ini', keys, dropped_keys(keys))
    return keys
