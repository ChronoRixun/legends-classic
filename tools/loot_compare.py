"""G8 comparator: the port's drop roller against the original's (loot + Forge, DESIGN 8.4 "S6" and "G8").

    python tools/loot_compare.py --s6 s6_run1.log s6_run2.log s6_run3.log --port port_run1.log port_run2.log port_run3.log
           [--tolerance 0.20] [--min-runs 3] [--json OUT.json] [--minutes-s6 A,B,C] [--minutes-port A,B,C]

Exit code 0 = PASS, 1 = FAIL, 2 = an input could not be read. Pure Python, offline, no game data: it reads the two
text logs the live tasks write and does arithmetic on them.

What it measures. A run is one play of the same level. From each run it takes

  rolls          the drop roller's calls (one per kill that rolls; calls with no drop count)
  drops          pickups spawned (a money drop spawns 2-4 pickups; a leader drops up to 4)
  drop events    (roll, class) pairs: all pickups of one class within one roll count once, so a money drop is
                 ONE event whatever its split. Classes: gear, pack, money, xtreme, other (see classify())
  enemy-minutes  the run's denominator (below)

and prints, per run and pooled over the runs of each side: rolls, drops, drop events, drop events per enemy-minute,
drops per roll, and the class mix (share of drop events). PASS needs, pooled over >= --min-runs runs per side, the port's
drop-event rate per enemy-minute AND each of the four mix shares (gear, pack, money, xtreme) within +/- --tolerance
(default 0.20, relative to the original's value) of the original's. A side with fewer runs than --min-runs FAILs. The
"other" class (king pips, keys, ...) is reported, never gated.

Enemy-minute. The denominator is supplied, not guessed: a `run ... enemy_minutes=<float>` header in the log, or
--minutes-s6 / --minutes-port (a comma list, one value per run in file order, which override the header). If neither is given it is
derived as (time of the last roll - time of the first roll) / 60 from the `t=` field (S6) or the log timestamp (port) and
the result is marked `derived`; a run with no times and no minutes is an input error. The recommended definition for both
sides: the minutes of the zone timer between the run's first and last roll of the level segment being compared. The
report warns when the two sides used different sources. Drops per roll (pace independent) is printed next to it as the
cross-check: a rate gate that fails while drops-per-roll agrees points at play pace, not at the roller.

Statistics. The +/-20 percent gate is the brief's. Gear is about 7 percent of drops, so a short run decides it by chance;
every gated row therefore also carries its event count, a z score (Poisson for the rate, two-proportion for a share) and
a note `UNDERPOWERED` when either side has fewer than 20 events behind it. A verdict that rests on an UNDERPOWERED row
says so; the gate itself stays the strict one.

LOG FORMATS (the S6 format is the one task-loot-impl-s6.md writes; the port format is the DLL's own roll log).

Original game (S6), one file per run, lines in time order, ASCII, any other line is ignored:

    run id=<name> zone=<zone> enemy_minutes=<float>              header, optional, first line of a run
    roll t=<seconds> cat=<0..5> lead=<0|1> [n=<serial>]          one per entry to the roller (XBE 0x70fb0)
    spawn t=<seconds> def=<NAME> amt=<integer> [n=<serial>] [cls=<class>]     one per spawn call (XBE 0x7154d)

`roll` carries the actor's category (field +0x2a8) and the leader flag; a `spawn` belongs to the most recent `roll`, or to
the roll whose `n` it names. A roll without a spawn is a roll that dropped nothing (failed outer gate, empty pool is not
possible: it falls back to money / Xtreme). `t` is the zone timer in seconds. `def` is the definition's name as the game
spells it (MONEY1, XTREME_PIP, HEALTH_ITEM, ENERGY_ITEM, or an equipment name); `cls` overrides the name classification.
Several runs may share a file: each `run` header starts a new run.

Port, the DLL's roll log (xml2-fix `x1_roll`, one line per pickup; `def=-` / `amt=0` is a roll that dropped nothing), as
it appears in the fix log or in the test pipe's `economy rolls` (16 most recent lines, no timestamps):

    [HH:MM:SS.mmm] roll n=<serial> cat=3 lead=0 G=1 bucket=3 def=<name> amt=1 draws=5

The port lines carry an explicit roll serial, `n=<serial>` (the DLL numbers every roll; every pickup line of a roll, and
the single `def=-` line of a roll that dropped nothing, carries the same value). With it, grouping is exact: all lines with
one `n` are one roll, whatever their timestamps and however close the next roll is, and pipe output (no timestamps) is
exact too. A line without `n` (a log written by a DLL before the serial existed) falls back to the old time window:
consecutive lines with the same cat, lead, G, bucket and draws, logged within 20 ms of each other, where a line with a
non-money definition of a non-leader roll is always a roll of its own. That fallback cannot see where one roll ends and an
equal one starts, so every group it forms that could be several rolls is reported as a WARNING (also in `warnings` in the
JSON): pickups merged without timestamps; a merged group of more than 4 pickups (a roll spawns at most 4, so it is at least
two rolls); a serial reused for a different header or after a gap of more than 1 s (a restarted counter); a run mixing
lines with and without a serial. The counts of a run with warnings are lower bounds for rolls.
A `run ... enemy_minutes=` header line
(same as above) may precede a run in a port file too. Auto-detection: a `roll` line with `def=` is a port line, a
`roll` line without it is an S6 roll header.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass, field

CLASSES = ('gear', 'pack', 'money', 'xtreme', 'other')
GATED_MIX = ('gear', 'pack', 'money', 'xtreme')
UNDERPOWERED_EVENTS = 20
SAME_ROLL_SECONDS = 0.020
SERIAL_GAP_SECONDS = 1.0                 # one roll's pickups are logged together; a longer gap on one serial = a reused serial
MAX_PICKUPS_PER_ROLL = 4                 # a money drop spawns 2-4, a leader up to 4

PACKS = {'health_item', 'energy_item'}
OTHER_NAMES = {'skirmish_king_pip', 'xp', 'skill', 'stat'}
_KEY = re.compile(r'^key(card)?\d*$')
_MONEY = re.compile(r'^money\d*$')


def classify(name: str) -> str:
    """class of a dropped definition by name: money (MONEY1-3), xtreme (XTREME_PIP), pack (HEALTH_ITEM, ENERGY_ITEM),
    other (king pip, keys, XP / skill / stat pickups), gear (everything else, i.e. equipment)"""
    low = (name or '').strip().lower()
    if _MONEY.match(low):
        return 'money'
    if low == 'xtreme_pip':
        return 'xtreme'
    if low in PACKS:
        return 'pack'
    if low in OTHER_NAMES or _KEY.match(low):
        return 'other'
    return 'gear'


class LogError(ValueError):
    pass


# ---------------------------------------------------------------------------------------------------- parsing
_TS = re.compile(r'^\s*\[(\d\d):(\d\d):(\d\d)(?:\.(\d{1,3}))?\]\s*')
_KV = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)=(\S*)')


def _seconds(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + (int(ms.ljust(3, '0')) / 1000.0 if ms else 0.0)


@dataclass
class Roll:
    t: float | None
    cat: int | None
    lead: int
    drops: list = field(default_factory=list)          # [(name, amount, class)]
    n: str | None = None
    ts_merged: bool = False                              # port: pickups merged without a time to tell rolls apart
    window_merged: bool = False                          # port: grouped by the time window (no serial), more than one line
    last_t: float | None = None                          # port, serial grouping: time of the roll's latest line
    header: tuple | None = None                          # port, serial grouping: (cat, lead, G, bucket, draws)


@dataclass
class Run:
    id: str
    side: str                                            # 's6' or 'port'
    rolls: list = field(default_factory=list)
    zone: str = ''
    minutes: float | None = None
    minutes_source: str = ''
    ambiguous_merges: int = 0
    warnings: list = field(default_factory=list)
    serial_lines: int = 0
    unserialed_lines: int = 0
    source: str = ''

    def finish(self, override=None):
        if override is not None:
            self.minutes, self.minutes_source = float(override), 'cli'
        elif self.minutes is not None:
            self.minutes_source = 'header'
        else:
            ts = [r.t for r in self.rolls if r.t is not None]
            if len(ts) >= 2 and max(ts) > min(ts):
                self.minutes, self.minutes_source = (max(ts) - min(ts)) / 60.0, 'derived'
        if self.minutes is None or not self.minutes > 0:
            raise LogError(f'{self.source}: run {self.id!r} has no enemy-minutes (give a `run ... enemy_minutes=` header, '
                           f'--minutes-{self.side}, or times on at least two rolls)')
        return self


def _cat(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse_lines(lines, side_hint=None, source=''):
    """-> [Run]. side_hint 's6' / 'port' forces the dialect of `roll` lines; None auto-detects per line."""
    runs = []
    cur = None
    day_offset = 0.0
    last_wall = None
    port_open = None                  # (header tuple, roll) of the port roll still collecting pickups
    last_s6_roll = None
    by_serial = {}
    port_serial = {}                  # port roll serial -> its Roll

    def start(rid='', side='', zone='', minutes=None):
        nonlocal cur, port_open, last_s6_roll, by_serial, port_serial, day_offset, last_wall
        cur = Run(id=rid or f'{source or "run"}#{len(runs) + 1}', side=side, zone=zone, minutes=minutes, source=source)
        runs.append(cur)
        port_open = last_s6_roll = None
        by_serial = {}
        port_serial = {}
        day_offset, last_wall = 0.0, None
        return cur

    for lineno, raw in enumerate(lines, 1):
        line = raw.rstrip('\r\n')
        wall = None
        m = _TS.match(line)
        if m:
            wall = _seconds(*m.groups())
            line = line[m.end():]
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        word, _, rest = line.partition(' ')
        kv = dict(_KV.findall(rest))
        if word == 'run':
            start(kv.get('id', ''), kv.get('game', ''), kv.get('zone', ''),
                  float(kv['enemy_minutes']) if kv.get('enemy_minutes') not in (None, '') else None)
            continue
        if word not in ('roll', 'spawn'):
            continue
        if cur is None:
            start()
        if wall is not None:                                   # a wall clock that wraps past midnight keeps climbing
            if last_wall is not None and wall + day_offset < last_wall - 1.0:
                day_offset += 86400.0
            wall += day_offset
            last_wall = wall
        port_line = word == 'roll' and 'def' in kv
        if side_hint == 'port':
            port_line = word == 'roll'
        if side_hint == 's6':
            port_line = False
        if word == 'roll' and not port_line:                    # S6 roll header
            cur.side = cur.side or 's6'
            t = float(kv['t']) if kv.get('t') not in (None, '') else wall
            r = Roll(t=t, cat=_cat(kv.get('cat')), lead=1 if kv.get('lead') in ('1', 'true') else 0, n=kv.get('n'))
            cur.rolls.append(r)
            last_s6_roll = r
            if r.n is not None:
                by_serial[r.n] = r
            port_open = None
            continue
        if word == 'spawn':
            cur.side = cur.side or 's6'
            target = by_serial.get(kv.get('n')) if kv.get('n') is not None else last_s6_roll
            if target is None:
                raise LogError(f'{source}:{lineno}: a spawn line before any roll line')
            name = kv.get('def', '')
            if not name or name == '-':
                continue
            target.drops.append((name, int(kv.get('amt', '1') or 1), kv.get('cls') or classify(name)))
            continue
        # port line
        cur.side = cur.side or 'port'
        t = wall
        header = (kv.get('cat'), kv.get('lead'), kv.get('G'), kv.get('bucket'), kv.get('draws'))
        name = kv.get('def', '-')
        amount = int(kv.get('amt', '0') or 0)
        lead = 1 if kv.get('lead') in ('1', 'true') else 0
        none = name in ('-', '')
        serial = kv.get('n')
        if serial is not None:                                  # explicit roll serial: exact grouping
            cur.serial_lines += 1
            r = port_serial.get(serial)
            if r is not None and (r.header != header or (t is not None and r.last_t is not None
                                                         and t - r.last_t > SERIAL_GAP_SECONDS)):
                cur.warnings.append(f'{source}:{lineno}: roll serial n={serial} reused for another roll '
                                    f'(different header or more than {SERIAL_GAP_SECONDS:g} s later): counted as a new roll')
                r = None
            if r is None:
                r = Roll(t=t, cat=_cat(kv.get('cat')), lead=lead, n=serial, header=header)
                cur.rolls.append(r)
                port_serial[serial] = r
            if not none:
                r.drops.append((name, amount, kv.get('cls') or classify(name)))
            r.last_t = t
            port_open = None
            continue
        cur.unserialed_lines += 1
        merge = False
        if port_open is not None and not none:
            h0, r0, t0, last_t = port_open
            near = t is None or last_t is None or abs(t - last_t) <= SAME_ROLL_SECONDS
            # a roll holds several pickups only when it is a leader roll, or a money drop (one MONEYd, split 2-4)
            more = bool(lead) or (classify(name) == 'money' and name == r0.drops[0][0])
            merge = h0 == header and near and more
        if merge:
            r0.drops.append((name, amount, kv.get('cls') or classify(name)))
            r0.window_merged = True
            if t is None or last_t is None:
                r0.ts_merged = True
            port_open = (h0, r0, t0, t)
            continue
        r = Roll(t=t, cat=_cat(kv.get('cat')), lead=lead)
        if not none:
            r.drops.append((name, amount, kv.get('cls') or classify(name)))
        cur.rolls.append(r)
        port_open = (header, r, t, t) if not none else None
    for run in runs:
        run.ambiguous_merges = sum(1 for r in run.rolls if r.ts_merged and len(r.drops) > 1)
        if run.ambiguous_merges:
            run.warnings.append(f'{run.source or run.id}: run {run.id!r}: {run.ambiguous_merges} roll(s) merged pickups '
                                f'without timestamps or serials (equal rolls cannot be told apart)')
        big = sum(1 for r in run.rolls if r.window_merged and len(r.drops) > MAX_PICKUPS_PER_ROLL)
        if big:
            run.warnings.append(f'{run.source or run.id}: run {run.id!r}: {big} time-window group(s) of more than '
                                f'{MAX_PICKUPS_PER_ROLL} pickups (one roll spawns at most {MAX_PICKUPS_PER_ROLL}: several '
                                f'rolls were merged; add n=<serial> to the roll log)')
        if run.serial_lines and run.unserialed_lines:
            run.warnings.append(f'{run.source or run.id}: run {run.id!r}: {run.serial_lines} line(s) with a roll serial '
                                f'and {run.unserialed_lines} without (a log from two DLL builds?)')
    return runs


def load(paths, side_hint=None):
    runs = []
    for p in paths:
        try:
            with open(p, 'r', encoding='utf-8', errors='replace') as f:
                found = parse_lines(f, side_hint, source=str(p))
        except OSError as e:
            raise LogError(f'{p}: {e}') from e
        if not found or not any(r.rolls for r in found):
            raise LogError(f'{p}: no roll lines')
        runs.extend(r for r in found if r.rolls)
    return runs


# ---------------------------------------------------------------------------------------------------- metrics
def run_metrics(run):
    events = {c: 0 for c in CLASSES}
    pickups = {c: 0 for c in CLASSES}
    dropping = 0
    for r in run.rolls:
        seen = set()
        for name, amount, cls in r.drops:
            pickups[cls] = pickups.get(cls, 0) + 1
            seen.add(cls)
        for cls in seen:
            events[cls] = events.get(cls, 0) + 1
        dropping += bool(r.drops)
    return _summary(len(run.rolls), dropping, events, pickups, run.minutes)


def _summary(rolls, dropping, events, pickups, minutes):
    ev_total = sum(events.values())
    drops = sum(pickups.values())
    return {'rolls': rolls, 'rolls_with_drop': dropping, 'drops': drops, 'drop_events': ev_total,
            'events': dict(events), 'pickups': dict(pickups), 'enemy_minutes': minutes,
            'rolls_per_min': rolls / minutes, 'drop_events_per_min': ev_total / minutes,
            'drops_per_roll': (drops / rolls) if rolls else 0.0,
            'events_per_roll': (ev_total / rolls) if rolls else 0.0,
            'mix': {c: (events.get(c, 0) / ev_total if ev_total else 0.0) for c in CLASSES}}


def pooled(runs):
    events = {c: 0 for c in CLASSES}
    pickups = {c: 0 for c in CLASSES}
    rolls = dropping = 0
    minutes = 0.0
    for run in runs:
        m = run_metrics(run)
        rolls += m['rolls']
        dropping += m['rolls_with_drop']
        minutes += m['enemy_minutes']
        for c in CLASSES:
            events[c] += m['events'][c]
            pickups[c] += m['pickups'][c]
    return _summary(rolls, dropping, events, pickups, minutes)


# ---------------------------------------------------------------------------------------------------- the gate
def _rel(port, s6):
    if s6 == 0:
        return 0.0 if port == 0 else math.inf
    return (port - s6) / s6


def _z_rate(cp, mp, cs, ms):
    var = (cp / (mp * mp) if mp else 0.0) + (cs / (ms * ms) if ms else 0.0)
    if var == 0:
        return 0.0 if cp / mp == cs / ms else math.inf
    return (cp / mp - cs / ms) / math.sqrt(var)


def _z_share(cp, np_, cs, ns):
    if not np_ or not ns:
        return math.inf
    p = (cp + cs) / (np_ + ns)
    se = math.sqrt(p * (1 - p) * (1 / np_ + 1 / ns))
    return 0.0 if se == 0 and cp / np_ == cs / ns else ((cp / np_ - cs / ns) / se if se else math.inf)


def _row(name, port, s6, tol, z, ev_port, ev_s6, unit):
    rel = _rel(port, s6)
    ok = abs(rel) <= tol
    return {'metric': name, 'unit': unit, 'port': port, 'original': s6, 'relative': rel, 'tolerance': tol,
            'pass': ok, 'events_port': ev_port, 'events_original': ev_s6, 'z': z,
            'within_2_sigma': abs(z) <= 2.0,
            'underpowered': min(ev_port, ev_s6) < UNDERPOWERED_EVENTS}


def compare_pooled(port, s6, tol):
    rows = [_row('drop events per enemy-minute', port['drop_events_per_min'], s6['drop_events_per_min'], tol,
                 _z_rate(port['drop_events'], port['enemy_minutes'], s6['drop_events'], s6['enemy_minutes']),
                 port['drop_events'], s6['drop_events'], 'per enemy-minute')]
    for c in GATED_MIX:
        rows.append(_row(f'mix: {c}', port['mix'][c], s6['mix'][c], tol,
                         _z_share(port['events'][c], port['drop_events'], s6['events'][c], s6['drop_events']),
                         port['events'][c], s6['events'][c], 'share of drop events'))
    return rows


def run_compare(s6_runs, port_runs, tolerance=0.20, min_runs=3):
    out = {'tolerance': tolerance, 'min_runs': min_runs, 'notes': [], 'runs': {'original': [], 'port': []}}
    for label, runs in (('original', s6_runs), ('port', port_runs)):
        for r in runs:
            m = run_metrics(r)
            m.update(id=r.id, minutes_source=r.minutes_source, ambiguous_merges=r.ambiguous_merges, warnings=list(r.warnings), source=r.source)
            out['runs'][label].append(m)
    out['pooled'] = {'original': pooled(s6_runs), 'port': pooled(port_runs)}
    problems = []
    for label, runs in (('original', s6_runs), ('port', port_runs)):
        if len(runs) < min_runs:
            problems.append(f'{label}: {len(runs)} run(s), {min_runs} needed')
    srcs = {label: {r.minutes_source for r in runs} for label, runs in (('original', s6_runs), ('port', port_runs))}
    if srcs['original'] != srcs['port']:
        out['notes'].append(f'enemy-minutes sources differ (original {sorted(srcs["original"])}, port {sorted(srcs["port"])}): '
                            f'compare drops per roll as well')
    amb = sum(r.ambiguous_merges for r in port_runs)
    if amb:
        out['notes'].append(f'{amb} port roll(s) merged pickups without timestamps (counts are lower bounds for rolls)')
    out['warnings'] = [w for r in port_runs for w in r.warnings]
    windowed = sum(1 for r in port_runs for x in r.rolls if x.window_merged)
    if windowed:
        out['warnings'].append(f'{windowed} port roll(s) were grouped by the 20 ms time window because their lines carry '
                               f'no n=<serial>: back-to-back equal rolls may be merged')
    out['rows'] = compare_pooled(out['pooled']['port'], out['pooled']['original'], tolerance)
    per_run = []
    base = out['pooled']['original']
    for m in out['runs']['port']:
        rows = compare_pooled(m, base, tolerance)
        per_run.append({'id': m['id'], 'pass': all(r['pass'] for r in rows),
                        'failing': [r['metric'] for r in rows if not r['pass']]})
    out['port_runs_vs_original_pool'] = per_run
    # the pace-independent cross-check
    out['drops_per_roll'] = {'port': out['pooled']['port']['events_per_roll'],
                             'original': out['pooled']['original']['events_per_roll'],
                             'relative': _rel(out['pooled']['port']['events_per_roll'],
                                              out['pooled']['original']['events_per_roll'])}
    failing = [r['metric'] for r in out['rows'] if not r['pass']]
    weak = [r['metric'] for r in out['rows'] if r['underpowered']]
    out['verdict'] = 'PASS' if not failing and not problems else 'FAIL'
    out['failing'] = failing
    out['problems'] = problems
    out['underpowered'] = weak
    return out


def _pct(x):
    return 'inf' if x in (math.inf, -math.inf) else f'{x * 100:+.1f}%'


def render(res):
    L = []
    for label in ('original', 'port'):
        L.append(f'{label.upper()} runs')
        L.append(f'  {"run":<28}{"rolls":>7}{"drops":>7}{"events":>8}{"minutes":>9}{"ev/min":>8}{"ev/roll":>8}  '
                 f'{"gear":>6}{"pack":>6}{"money":>6}{"xtreme":>7}{"other":>6}')
        for m in res['runs'][label] + [dict(res['pooled'][label], id='POOLED', minutes_source='')]:
            mix = m['mix']
            L.append(f'  {m["id"][:27]:<28}{m["rolls"]:>7}{m["drops"]:>7}{m["drop_events"]:>8}{m["enemy_minutes"]:>9.2f}'
                     f'{m["drop_events_per_min"]:>8.2f}{m["events_per_roll"]:>8.3f}  '
                     + ''.join(f'{mix[c] * 100:>{7 if c == "xtreme" else 6}.1f}%'[1:] for c in CLASSES))
        L.append('')
    L.append(f'GATE (pooled, +/-{res["tolerance"] * 100:.0f}% of the original)')
    L.append(f'  {"metric":<30}{"port":>10}{"original":>10}{"diff":>9}{"events p/o":>13}{"z":>7}  verdict')
    for r in res['rows']:
        flag = 'ok' if r['pass'] else 'FAIL'
        if r['underpowered']:
            flag += ' (UNDERPOWERED)'
        L.append(f'  {r["metric"]:<30}{r["port"]:>10.4f}{r["original"]:>10.4f}{_pct(r["relative"]):>9}'
                 f'{str(r["events_port"]) + "/" + str(r["events_original"]):>13}{r["z"]:>7.2f}  {flag}')
    d = res['drops_per_roll']
    L.append(f'  drop events per roll (pace independent): port {d["port"]:.4f}, original {d["original"]:.4f}, '
             f'{_pct(d["relative"])}')
    L.append('')
    L.append('PORT RUNS against the original pool (informational)')
    for r in res['port_runs_vs_original_pool']:
        L.append(f'  {r["id"][:40]:<42}{"ok" if r["pass"] else "FAIL: " + ", ".join(r["failing"])}')
    for n in res['notes']:
        L.append('note: ' + n)
    for w in res.get('warnings', []):
        L.append('WARNING: ' + w)
    for p in res['problems']:
        L.append('problem: ' + p)
    if res['underpowered']:
        L.append('UNDERPOWERED rows (< %d events on a side): %s' % (UNDERPOWERED_EVENTS, ', '.join(res['underpowered'])))
    L.append('')
    L.append(f'G8 VERDICT: {res["verdict"]}' + (f' (failing: {", ".join(res["failing"])})' if res['failing'] else '')
             + (f' ({"; ".join(res["problems"])})' if res['problems'] else ''))
    return '\n'.join(L) + '\n'


def _clean(x):
    """JSON-safe copy: infinities (a share against a zero original) become null"""
    if isinstance(x, float) and (math.isinf(x) or math.isnan(x)):
        return None
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    return x


def _floats(text, n, what):
    if not text:
        return [None] * n
    vals = [float(x) for x in text.split(',') if x.strip()]
    if len(vals) != n:
        raise LogError(f'--minutes-{what} gives {len(vals)} values for {n} run(s)')
    return vals


def main(argv=None):
    ap = argparse.ArgumentParser(description='G8: the port\'s drop roller against the original\'s (see the module docstring)')
    ap.add_argument('--s6', nargs='+', required=True, metavar='LOG', help='the original game\'s logs (S6 format)')
    ap.add_argument('--port', nargs='+', required=True, metavar='LOG', help='the port\'s roll logs')
    ap.add_argument('--tolerance', type=float, default=0.20)
    ap.add_argument('--min-runs', type=int, default=3)
    ap.add_argument('--minutes-s6', help='comma list, one enemy-minutes value per S6 run (file order)')
    ap.add_argument('--minutes-port', help='comma list, one enemy-minutes value per port run (file order)')
    ap.add_argument('--json', help='also write the result as JSON')
    a = ap.parse_args(argv)
    try:
        s6 = load(a.s6, 's6')
        port = load(a.port, 'port')
        for runs, text, what in ((s6, a.minutes_s6, 's6'), (port, a.minutes_port, 'port')):
            for run, override in zip(runs, _floats(text, len(runs), what)):
                run.finish(override)
    except (LogError, ValueError) as e:
        print(f'loot_compare: {e}', file=sys.stderr)
        return 2
    res = run_compare(s6, port, a.tolerance, a.min_runs)
    sys.stdout.write(render(res))
    if a.json:
        with open(a.json, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(_clean(res), f, indent=1)
            f.write('\n')
    return 0 if res['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
