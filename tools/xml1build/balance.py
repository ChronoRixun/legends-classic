"""xml1build.balance - the first game's combat balance: what the build has to carry so that xml2-fix's [Balance]
section can restore it (issue #14; SPEC.md section 69).

Most of the difference between the two games is engine formulas on the same data (health per body point, the stat
bonus on a hit, the melee hit chance, the talent might), which xml2-fix changes from the ini. Two things the engine
cannot be told from the ini, because they are properties of the attack data:

  1. Power attacks. XML1 gives an attack flagged PowerAttack="true" no strength / mind bonus and never rolls it to
     hit (default.xbe 0x5cca0, 0x5c3c0). XMen2.exe does not read the attribute; its own switch is DamageScale: the
     stat bonus and a counted miss are for `normal` only (0x453b54, 0x45333f), `none` is XML1's power attack. The
     build writes damagescale="x1power" on every XML1 style <event> / <trigger> whose XML1 PowerAttack is true and
     whose built chain resolves to `normal`. XMen2.exe's parser (0x44ec00) reads an unknown name as `normal`, so
     the marker changes nothing by itself; xml2-fix [Balance] PowerAttacks=xml1 reads it as `none`.
  2. The basic attacks. The build ships XML2's data/shared_combat_events (SPEC 4.4); SPEC 33 writes XML1's values
     onto XML1 styles only, so the XML2 fighting styles XML1's characters use (fightstyle_villain, _hero, _baton,
     ...) still punch with XML2's numbers. The seven basic melee events get XML1's values in the shared file itself.

X1_BALANCE is the one switch for all of it - the two data changes, the [Balance] keys and the balance builds'
[Online] GameVersion in fix_ini. It is ON since builder 0.2.0 (SPEC 69): every build is a balance build. Before the
release it was off, with $XML1BUILD_X1_BALANCE=1 for a test build; the release set X1_BALANCE to True, dropped the
environment override, bumped CONTENT_VERSION and raised fix_ini.REQUIRED_XML2FIX to the xml2-fix release that has
[Balance] (1.4).

Pure except for validate(): no file I/O.
"""
from __future__ import annotations

import collections

from . import combat_events as CE

X1_BALANCE = True


def enabled() -> bool:
    """the switch (a constant since 0.2.0; a function so a test can flip the module attribute)."""
    return bool(X1_BALANCE)


# ------------------------------------------------------------------------------------------ the ini side
# xml2-fix [Balance] for a balance build: the first game's numbers (default.xbe: health 10 per body point 0x44f1fc;
# the stat bonus 0.1 per point 0x3c8240; might 1.05 / 1.10 / 1.15 by rank 0x5cd82; the hit chance formula 0x5c40c;
# both bonuses of a hit worked out on its roll and rounded down, 0x5cdb6 / 0x5ce02).
# HeroStatScale is heroes.STAT_SCALE (what the build multiplied the heroes' stats by) and NativeStatHeroes the
# herostat entries it did not scale; fix_ini.balance_keys fills both from the caller's values.
BALANCE_KEYS = {'EnemyHealthPerBody': '10', 'HeroHealthPerBody': '2.5', 'HeroStatScale': None, 'NativeStatHeroes': None, 'StrengthBonus': '0.1',
                'MindBonus': '0.1', 'MightBonus': '0.05', 'PowerAttacks': 'xml1', 'HitChance': 'xml1', 'Rounding': 'xml1',
                'DamageRolls': 'xml1', 'ReceiveRounding': 'xml1', 'DamageCap': 'xml1'}
# ReceiveRounding / DamageCap (xml2-fix 1.9.0-beta.1, gameplay rule 41, its docs/balance.md): the receive side converts a
# hit to a whole number after the defense and after the scale as default.xbe 0x45517..0x45558 does, and a hit is
# capped at XML1's 32,000 (0x5ce0d) instead of XMen2.exe's 1,000,000.
# tuning keys xml2-fix also reads; the port owns them (a build that does not set one drops it) HeroHealthPerBody ships as 2.5
TUNING_KEYS = ('HitChanceBase', 'HitChancePerPoint', 'HeroStrengthBonus', 'HeroMindBonus', 'HeroHealthPerBody',
               'MeleeWeapons')
# every build since 0.2.0 is a balance build, so one GameSpy game version separates the whole release from the
# port's without [Balance] (fix_ini.PORT_GAME_VERSION; every peer computes health and damage from its own ini)
REPORT_KEY = 'balance'           # <out>/_build/report.json build.balance: 'xml1' for a build made with the switch on
REPORT_ON = 'xml1'

# ------------------------------------------------------------------------------------------ 1. power attacks
POWER_ATTACK_SCALE = 'x1power'   # not a name of XMen2.exe's table 0x6d6dec (none / normal / difficulty / ""): normal
NORMAL_SCALE = 'normal'
X1POWER_KIND = 'x1_power_attack'


def _flag(value):
    v = (value or '').strip().lower()
    return True if v == 'true' else False if v == 'false' else None


def x1_power_events(x1_shared_root) -> dict:
    """{lower event name: True / False} of XML1's data/shared_combat_events.xml: the PowerAttack each shared event
    ends up with (its own attribute, else its `inherit` parent's; events that say nothing are not listed)."""
    table, raw = {}, {}
    if x1_shared_root is None:
        return table
    for e in x1_shared_root.iter():
        if CE._tag(e) == 'event' and CE._get(e, 'name'):
            raw.setdefault(CE._get(e, 'name').lower(), e)
    for name, e in raw.items():
        seen = set()
        while e is not None and id(e) not in seen:
            seen.add(id(e))
            own = _flag(CE._get(e, 'powerattack'))
            if own is not None:
                table[name] = own
                break
            e = raw.get((CE._get(e, 'inherit') or '').lower())
    return table


def shared_scales(shared_root) -> dict:
    """{lower event name: damagescale (lower) or None} of the shipped data/shared_combat_events: what an element
    that names the shared event and sets no damagescale itself gets (the event's own, else its parent's)."""
    raw, table = {}, {}
    if shared_root is None:
        return table
    for e in shared_root.iter():
        if CE._tag(e) == 'event' and CE._get(e, 'name'):
            raw.setdefault(CE._get(e, 'name').lower(), e)
    for name, e in raw.items():
        seen, scale = set(), None
        while e is not None and id(e) not in seen:
            seen.add(id(e))
            scale = CE._get(e, 'damagescale')
            if scale is not None:
                break
            e = raw.get((CE._get(e, 'inherit') or '').lower())
        table[name] = scale.strip().lower() if scale is not None else None
    return table


def _walk(root):
    """[(element, {lower name: element} it resolves in)] for every <event> and named <trigger> of one style tree,
    parents before children: the style's root events in document order (each sees the ones before it), then each
    FightMove's own events and triggers (which see the root events and the move's events before them)."""
    out = []
    if root is None:
        return out
    tops = list(root) if root.tag == 'xmlb_multiple_roots' else [root]
    local = {}
    moves = []
    for top in tops:
        for e in top:
            t = CE._tag(e)
            if t == 'event':
                out.append((e, dict(local)))
                if CE._get(e, 'name'):
                    local[CE._get(e, 'name').lower()] = e
            elif t == 'fightmove':
                moves.append(e)
    for m in moves:
        mev = dict(local)
        for e in m:
            if CE._tag(e) == 'event':
                out.append((e, dict(mev)))
                if CE._get(e, 'name'):
                    mev[CE._get(e, 'name').lower()] = e
        for t in m:
            if CE._tag(t) == 'trigger' and CE._get(t, 'name'):
                out.append((t, mev))
    return out


def _parent(el, table):
    """(the style element `el` takes its data from, or None; the name it looks up) - 0x501630: no parent with a
    `type`, else `inherit`, else `name`."""
    if CE._get(el, 'type'):
        return None, ''
    base = (CE._get(el, 'inherit') or CE._get(el, 'name') or '').lower()
    p = table.get(base)
    return (p if p is not el else None), base


def x1_power_elements(root, x1_power) -> dict:
    """{id(element): True / False}: XML1's PowerAttack for every <event> / named <trigger> of an XML1 style tree
    that has one - its own attribute, else the style event it takes its data from, else the XML1 shared event of
    that name (x1_power: x1_power_events). Call it BEFORE combat_events.rewrite_style, which re-points XML1-only
    shared names at XML2's."""
    flags, chain = {}, {}
    for el, table in _walk(root):
        own = _flag(CE._get(el, 'powerattack'))
        if own is None:
            p, base = _parent(el, table)
            own = chain.get(id(p)) if p is not None else x1_power.get(base)
        chain[id(el)] = own
        if own is not None:
            flags[id(el)] = own
    return flags


def mark_power_attacks(root, power, shared_scale) -> collections.Counter:
    """Write damagescale="x1power" on every element of `power` (x1_power_elements, taken before the rewrite) that
    is an XML1 power attack and whose built chain resolves to `normal`, in place and idempotent; a child of a marked
    event inherits the marker (XMen2.exe copies the parent's attack data, 0x4dce80) and is not written again. An
    element XML1 flags PowerAttack="false" under a marked parent gets `normal` back. shared_scale: shared_scales()
    of the shipped shared events. A chain that sets no damagescale at all is left alone: the marker must read
    exactly as before without xml2-fix's key, and only `normal` is known to. Returns a Counter."""
    c = collections.Counter()
    scales = {}
    for el, table in _walk(root):
        own = CE._get(el, 'damagescale')
        if own is not None:
            scale = own.strip().lower()
        else:
            p, base = _parent(el, table)
            scale = scales.get(id(p)) if p is not None else shared_scale.get(base)
        flag = power.get(id(el))
        if flag is True and scale == NORMAL_SCALE:
            CE._set(el, 'damagescale', POWER_ATTACK_SCALE)
            scale = POWER_ATTACK_SCALE
            c[f'{X1POWER_KIND}:{CE._tag(el)}'] += 1
        elif flag is False and scale == POWER_ATTACK_SCALE:
            CE._set(el, 'damagescale', NORMAL_SCALE)
            scale = NORMAL_SCALE
            c[f'{X1POWER_KIND}:cleared'] += 1
        scales[id(el)] = scale
    return c


# ------------------------------------------------------------------------------------------ 2. the basic attacks
# the seven basic melee events of data/shared_combat_events and XML1's value code for each (XML1's own
# shared_combat_events.xml; combat_events.X1_SHARED_EVENT_VALUES has the same codes) - XML2 ships "2 3" for the first
# two, "3 5" for the next three and "6 9" for the last two
BASIC_ATTACK_VALUES = {'punch': 'L1', 'kick': 'L1', 'punch_heavy': 'L2', 'kick_heavy': 'L2', 'move_damage': 'L2',
                       'punch_veryheavy': 'L3', 'kick_veryheavy': 'L3'}
BASIC_KIND = 'x1_basic_attack'


def apply_basic_attack_values(shared_root, values) -> collections.Counter:
    """Write XML1's damage onto the seven basic melee events of a data/shared_combat_events tree, in place and
    idempotent (the first event of each name: the one the engine's lookup finds). values: heroes.Values of XML1's
    data/values.xml. Returns a Counter {'x1_basic_attack:<event>': 1} for each value changed."""
    c = collections.Counter()
    if shared_root is None or values is None:
        return c
    done = set()
    for e in shared_root.iter():
        name = (CE._get(e, 'name') or '').lower()
        if CE._tag(e) != 'event' or name not in BASIC_ATTACK_VALUES or name in done:
            continue
        done.add(name)
        want = values.resolve(BASIC_ATTACK_VALUES[name])
        if CE._get(e, 'damage') != want:
            CE._set(e, 'damage', want)
            c[f'{BASIC_KIND}:{name}'] += 1
    return c


def basic_attack_problems(shared_root, values) -> list:
    """[(event, found, wanted)] for each basic melee event that does not carry XML1's value."""
    out = []
    if shared_root is None or values is None:
        return out
    seen = {}
    for e in shared_root.iter():
        name = (CE._get(e, 'name') or '').lower()
        if CE._tag(e) == 'event' and name in BASIC_ATTACK_VALUES:
            seen.setdefault(name, CE._get(e, 'damage'))
    for name, code in BASIC_ATTACK_VALUES.items():
        want = values.resolve(code)
        if seen.get(name) != want:
            out.append((name, seen.get(name), want))
    return out


def count_markers(root) -> int:
    """how many elements of one style tree carry damagescale="x1power"."""
    if root is None:
        return 0
    return sum(1 for e in root.iter() if (CE._get(e, 'damagescale') or '').strip().lower() == POWER_ATTACK_SCALE)


# ------------------------------------------------------------------------------------------ the validator rule
def validate(v, ck, on=None):
    """V38 (SPEC 69): a balance build carries both data changes, any other build
    neither. on: whether <out> is a balance build (default: the switch of this run, else its report.json)."""
    from . import common as C
    if on is None:
        on = enabled() or str(C.build_options(v.ctx.out).get(REPORT_KEY) or '').lower() == REPORT_ON
    ck.set('balance_build', int(bool(on)))
    marked = files = 0
    for n, f in sorted(v.scan.files.items()):
        if not CE.is_style_rel(n):
            continue
        try:
            root = v.tree(f['rel'])
        except (KeyError, ValueError, OSError):
            continue
        k = count_markers(root)
        marked += k
        files += 1 if k else 0
    ck.set('x1power_markers', marked)
    ck.set('x1power_files', files)
    if on and not marked:
        ck.error(f'a balance build without a single damagescale="{POWER_ATTACK_SCALE}": XML1\'s power attacks keep '
                 f'the stat bonus whatever [Balance] PowerAttacks says (balance.mark_power_attacks did not run)')
    if not on and marked:
        ck.error(f'{marked} damagescale="{POWER_ATTACK_SCALE}" in {files} style files of a build made without the '
                 f'balance switch: its xml2-fix.ini has no [Balance], so the marker should not be there')
    if on:
        try:
            shared = v.tree(CE.SHARED_EVENTS_REL)
        except (KeyError, ValueError, OSError):
            shared = None
        if shared is None:
            ck.error(f'{CE.SHARED_EVENTS_REL} missing: the basic attacks cannot be checked')
        for name, found, want in basic_attack_problems(shared, v.ctx.x1_values()):
            ck.error(f'{CE.SHARED_EVENTS_REL}: {name} damage {found!r}, XML1\'s is {want!r} '
                     f'(balance.apply_basic_attack_values)')
