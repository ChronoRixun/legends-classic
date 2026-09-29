"""xml1build.scripts_selftest - standalone verification of the scripts module (private helper of scripts.py).

Run after a build that included the scripts module:

    python tools/xml1build/scripts_selftest.py --out build/_selftest_scripts

It never writes game files; it reads <out>, the registry, the base install and the research outputs, and
saves its findings to <out>/_build/scripts_selftest.json. Exit code 0 = every check passed.

Checks
  T1 install      every research/scripts/out script is in <out> byte-identical (CRLF), owned by 'scripts';
                  XML2's front end (intro_normal, main_back_main, main_back_debug) is the base file; XML1's dead
                  intro_demo / intro_e3 are absent.
  T2 lint         every Scripts/**.py the scripts module owns: CRLF only, every statement registered in
                  XMen2.exe exact-case with the right argc / literal types (droppable lines only in the known
                  dead XML1 developer scripts); no console-queue overflow outside dead code.
  T3 base         the only XML2 base scripts replaced are common/* and menus/new_game(_hard).
  T4 new game     new_game.py / new_game_hard.py = begin_alison body (+ header), lint-clean, load nyc1_1_1.
  T5 dialogs      Dialogs/x1: 92 XMLB + 92 engb, canonical XMLB, option code console-safe, every option target
                  exists; p091/p092 retargeted away from the dead Muir Island refs.
  T6 missions     Data/missions: missions.XMLB lists x1_act01..09, XMLB+engb per act, XMen2.exe caps; every
                  objective() literal in installed scripts is defined (or also undefined in XML1).
  T7 providers    zone_script_ref / zone_act / zone_package_extras / script_exists for all 210 zones, and
                  rewrite_data_tree over every XML1 text file zones feeds it (maps, conversations, dialogs,
                  data/entities, world tables): refs normalised, all 129 inline rewrites applied, no XML1-only
                  call left except XML1's own defects, inline <= 255 bytes, console attrs whitespace-free,
                  idempotent.
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import os
import re
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from xml1build import common as C                       # noqa: E402
    from xml1build import scripts as S                      # noqa: E402
    from xml1build import scripts_lint as L                 # noqa: E402
    from xml1build import scripts_transform as TR           # noqa: E402
else:
    from . import common as C
    from . import scripts as S
    from . import scripts_lint as L
    from . import scripts_transform as TR

WORLD_TABLES = ('data/common_ents.xml', 'data/item_ents.xml', 'data/items.eng', 'data/shared_nodes.eng')
DATA_PREFIXES = ('maps/', 'conversations/', 'dialogs/', 'data/entities/')


class T:
    def __init__(self):
        self.results = collections.OrderedDict()
        self.cur = None

    def start(self, name):
        self.cur = name
        self.results[name] = {'fail': [], 'info': {}}

    def fail(self, msg):
        self.results[self.cur]['fail'].append(str(msg))

    def info(self, k, v):
        self.results[self.cur]['info'][k] = v

    def ok(self):
        return all(not r['fail'] for r in self.results.values())


def _registry(out):
    p = Path(out) / '_build' / 'registry.json'
    return json.loads(p.read_text(encoding='utf-8'))['entries'] if p.is_file() else {}


def _out_bytes(ctx, rel):
    p = ctx.out_index.path(rel)
    return p.read_bytes() if p is not None else None


def t1_install(ctx, t, reg):
    t.start('T1 install')
    research = S._research_scripts(ctx)
    n_ok = n_transformed = 0
    for f in TR.selftest():
        t.fail(f'scripts_transform selftest: {f}')
    for ref, src in sorted(research.items()):
        rel = C.script_rel(ref)
        data = _out_bytes(ctx, rel)
        if ref in S.frontend_scripts(ctx):
            continue                                   # SPEC 21: generated instead (checked below)
        if ref in S.frontend_keep_xml2(ctx):
            base = ctx.base_index.path(rel)
            if base is None or data != base.read_bytes():
                t.fail(f'{rel}: XML2 front-end script is not the base file')
            if C.norm(rel) in reg and reg[C.norm(rel)]['owner'] == 'scripts':
                t.fail(f'{rel}: registered to scripts although the XML2 file must be kept')
            continue
        if ref in S.FRONTEND_DEAD_X1:
            if data is not None:
                t.fail(f'{rel}: XML1 dead front-end script installed')
            continue
        if data is None:
            t.fail(f'{rel}: not in <out>')
            continue
        raw = C.to_crlf(src.read_bytes().decode('latin-1')).encode('latin-1')
        want = S.script_text(ctx, ref).encode('latin-1')
        if data != want:
            t.fail(f'{rel}: differs from research/scripts/out + the scripts_transform post-passes')
        elif data != raw:
            n_transformed += 1
        e = reg.get(C.norm(rel))
        if e is None or e['owner'] != 'scripts':
            t.fail(f'{rel}: registry owner {e and e["owner"]!r}, expected scripts')
        n_ok += 1
    t.info('research_scripts', len(research))
    t.info('installed_identical', n_ok)
    t.info('installed_transformed', n_transformed)
    owned = [k for k, e in reg.items() if e['owner'] == 'scripts' and k.endswith('.py')]
    generated = S._generated_zone_scripts(ctx)
    forced_gen = S._forced_generated_scripts(ctx)                    # SPEC 19 end scripts (seat builds)
    fe_gen = S.frontend_scripts(ctx)                                 # SPEC 21 intro / postgame
    extra = sorted(k for k in owned if C.script_ref(k) not in research and C.script_ref(k) not in S.NEW_GAME_REFS
                   and C.script_ref(k) not in generated and C.script_ref(k) not in forced_gen
                   and C.script_ref(k) not in fe_gen)
    if extra:
        t.fail(f'scripts owns .py files that are neither research outputs, generated zone-entry / forced-teams '
               f'scripts nor the New Game hook: {extra[:10]}')
    for ref in sorted(forced_gen):
        data = _out_bytes(ctx, C.script_rel(ref))
        if data is None or data != S.script_text(ctx, ref).encode('latin-1'):
            t.fail(f'generated forced-teams script scripts/{ref}.py missing or differs from scripts.script_text')
    t.info('generated_forced_teams_scripts', len(forced_gen))
    for ref in sorted(fe_gen):
        data = _out_bytes(ctx, C.script_rel(ref))
        e = reg.get(C.norm(C.script_rel(ref)))
        if data is None or data != S.script_text(ctx, ref).encode('latin-1') or e is None or e['owner'] != 'scripts':
            t.fail(f'generated front-end script scripts/{ref}.py missing, not owned by scripts or differs')
    t.info('generated_frontend_scripts', len(fe_gen))
    # generated zone-entry scripts (act plan): installed as planned, setCurrentAct(<act>) is the first statement
    for ref, g in sorted(generated.items()):
        data = _out_bytes(ctx, C.script_rel(ref))
        if data is None:
            t.fail(f'generated zone-entry script scripts/{ref}.py not in <out>')
            continue
        if data != S.script_text(ctx, ref).encode('latin-1'):
            t.fail(f'scripts/{ref}.py differs from scripts.script_text')
        if TR.first_statement_act(data.decode('latin-1').split('\r\n')) != g['act']:
            t.fail(f'scripts/{ref}.py: first statement is not setCurrentAct({g["act"]})')
    t.info('generated_zone_entry_scripts', len(generated))
    t.info('scripts_owned_py', len(owned))


def t2_lint(ctx, t, reg):
    t.start('T2 lint')
    api = ctx.xml2_api
    senders = S._console_senders(ctx)
    n_files = n_stmts = 0
    allowed = []
    for k, e in sorted(reg.items()):
        if e['owner'] != 'scripts' or not k.endswith('.py'):
            continue
        data = (ctx.out / e['rel']).read_bytes()
        n_files += 1
        ref = C.script_ref(k)
        probs, info = L.lint_script_bytes(data, api)
        n_stmts += info['statements']
        text = data.decode('latin-1')
        if '\r\n' not in text and text.strip():
            t.fail(f'{k}: no CRLF')
        q = L.console_overflows(text.split('\r\n'), senders)
        for ln, kind, d in probs:
            msg = f'{k}:{ln}: {kind}: {d}'
            (allowed if ref in S.DEAD_DEV_SCRIPTS else t.results[t.cur]['fail']).append(msg)
        for ln, fn, cnt in q:
            msg = f'{k}:{ln}: console queue: {fn} is command #{cnt} without a wait'
            (allowed if ref in S.DEAD_DEV_SCRIPTS else t.results[t.cur]['fail']).append(msg)
    t.info('files', n_files)
    t.info('statements', n_stmts)
    t.info('allowlisted_dead_dev_lines', allowed)


def t3_base(ctx, t, reg):
    t.start('T3 base overwrites')
    over = sorted(C.script_ref(k) for k, e in reg.items()
                  if e['owner'] == 'scripts' and k.endswith('.py') and ctx.base_exists(e['rel']))
    bad = [r for r in over if not r.startswith('common/') and r not in S.NEW_GAME_REFS
           and r not in S.frontend_scripts_replacing_base(ctx)]          # SPEC 21 intro / main_back_main (xml1)
    if bad:
        t.fail(f'XML2 base scripts outside common/ replaced: {bad}')
    t.info('overwritten', over)


def t4_new_game(ctx, t, reg):
    t.start('T4 new game')
    src = S._script_text(ctx, S.NEW_GAME_BODY, mode='menu')[0].split('\r\n')     # the hook has no SPEC 19 block
    body = [l for l in src if l.strip() and not l.startswith('# Generated by')]
    if ctx.opt('no_movies'):
        body = [l for l in body if not re.match(r'\s*(startMovie|waitsignal)\s*\(', l)]
    if str(ctx.opt('newgame') or 'chooseteam').lower() == 'keepteam':          # scripts._new_game keepteam
        body = [re.sub(r'\bloadMapChooseTeam\s*\(', 'loadMapKeepTeam(', l) for l in body
                if not re.match(r'\s*unlockCharacter\s*\(\s*"cyclops"', l, re.I)]
    for ref in S.NEW_GAME_REFS:
        rel = C.script_rel(ref)
        data = _out_bytes(ctx, rel)
        if data is None:
            t.fail(f'{rel} missing')
            continue
        e = reg.get(C.norm(rel)) or {}
        if e.get('owner') not in ('scripts', 'testhooks'):
            t.fail(f'{rel}: owner {e.get("owner")!r}')
        text = data.decode('latin-1')
        lines = text.split('\r\n')
        probs, _ = L.lint_script_bytes(data, ctx.xml2_api)
        for p in probs:
            t.fail(f'{rel}: {p}')
        if e.get('owner') == 'testhooks':
            t.info(ref, 'overridden by testhooks')
            continue
        got = [l for l in lines if l.strip() and not l.startswith('# xml1-port') and not l.startswith('# after ')
               and not l.startswith('# body =') and not l.startswith('# no-movies') and not l.startswith('# keepteam')]
        if got != body:
            t.fail(f'{rel}: body differs from {S.NEW_GAME_BODY}: {got[:3]} vs {body[:3]}')
        if 'loadMapKeepTeam("nyc/alison/nyc1_1_1" )' not in lines and \
                'loadMapChooseTeam("nyc/alison/nyc1_1_1" )' not in lines:       # alison forces wolverine+cyclops
            t.fail(f'{rel}: does not load nyc/alison/nyc1_1_1')
        if not ctx.out_exists('Maps/nyc/alison/nyc1_1_1.XMLB') and not ctx.x1_path('maps/nyc/alison/nyc1_1_1.eng'):
            t.fail('nyc/alison/nyc1_1_1 is not an XML1 zone')
        t.info(ref, f'{len(got)} statements/comments')


def t5_dialogs(ctx, t, reg):
    t.start('T5 dialogs')
    research = S._research_dialogs(ctx)
    names = sorted(research)
    if len(names) != 92:
        t.fail(f'{len(names)} research dialogs (expected 92)')
    retarget = S._dialog_retargets(ctx)
    for name in names:
        roots = {}
        for ext in ('.XMLB', '.engb'):
            rel = f'Dialogs/x1/{name}{ext}'
            data = _out_bytes(ctx, rel)
            if data is None:
                t.fail(f'{rel} missing')
                continue
            e = reg.get(C.norm(rel)) or {}
            if e.get('owner') != 'scripts':
                t.fail(f'{rel}: owner {e.get("owner")!r}')
            root = C.decode_xmlb(data)
            if C.xmlb_attr_problems(root) or len(data) <= 8 or C.encode_xmlb(C.decode_xmlb(data)) != data:
                t.fail(f'{rel}: not canonical XMLB')
            roots[ext] = (data, root)
        if len(roots) == 2 and roots['.XMLB'][0] != roots['.engb'][0]:
            t.fail(f'Dialogs/x1/{name}: XMLB and engb differ')
        if '.XMLB' not in roots:
            continue
        for i, opt in enumerate(e for e in roots['.XMLB'][1].iter() if e.tag.lower() == 'option'):
            s = opt.get('script') or ''
            if not s:
                continue
            for p in L.console_problems(s):
                t.fail(f'Dialogs/x1/{name} option {i}: {p}')
            if '(' in s:
                probs, _ = L.lint_inline(s, ctx.xml2_api)
                for p in probs:
                    t.fail(f'Dialogs/x1/{name} option {i}: {p}')
            elif not (ctx.out_exists(C.script_rel(s)) or S.script_exists(ctx, s)):
                t.fail(f'Dialogs/x1/{name} option {i}: script {s} not in <out>')
            elif not ctx.out_exists(C.script_rel(s)):
                t.fail(f'Dialogs/x1/{name} option {i}: script {s} planned but not in <out>')
    for name in ('p091', 'p092'):
        data = _out_bytes(ctx, f'Dialogs/x1/{name}.XMLB')
        if data is None:
            continue
        opts = [e.get('script') for e in C.decode_xmlb(data).iter() if e.tag.lower() == 'option']
        if any(o and o.lower().startswith('muir_is/muir1/load') for o in opts):
            t.fail(f'Dialogs/x1/{name} still runs a dead Muir Island script: {opts}')
        t.info(name, opts)
    t.info('retargets', retarget['changes'])
    if retarget['unresolved']:
        t.fail(f'unresolved dialog targets: {retarget["unresolved"]}')


def t6_missions(ctx, t, reg):
    t.start('T6 missions')
    try:
        lst = ctx.read_out_xmlb('Data/missions/missions.XMLB')
    except KeyError:
        t.fail('Data/missions/missions.XMLB missing')
        return
    listed = [e.get('name') for e in lst if e.tag.upper() == 'MISSION']
    if listed != [f'x1_act{i:02d}' for i in range(1, 10)]:
        t.fail(f'missions.XMLB lists {listed}')
    if len(listed) > S.MAX_MISSION_FILES:
        t.fail(f'{len(listed)} mission files > {S.MAX_MISSION_FILES}')
    per_act, total, defined = collections.Counter(), 0, set()
    for m in listed:
        trees = {}
        for ext in ('.XMLB', '.engb'):
            rel = f'Data/missions/{m}{ext}'
            data = _out_bytes(ctx, rel)
            if data is None:
                t.fail(f'{rel} missing')
                continue
            if (reg.get(C.norm(rel)) or {}).get('owner') != 'scripts':
                t.fail(f'{rel} not owned by scripts')
            root = C.decode_xmlb(data)
            if C.xmlb_attr_problems(root) or C.encode_xmlb(C.decode_xmlb(data)) != data:
                t.fail(f'{rel}: not canonical XMLB')
            trees[ext] = root
        r = trees['.engb'] if '.engb' in trees else trees.get('.XMLB')
        if r is None:
            continue
        objs = [e for e in r if e.tag.upper() == 'OBJECTIVE']
        per_act[r.get('act')] += len(objs)
        total += len(objs)
        defined |= {(e.get('name') or '').lower() for e in objs}
        if '.XMLB' in trees and '.engb' in trees:
            a = [e.get('name') for e in trees['.XMLB'] if e.tag.upper() == 'OBJECTIVE']
            b = [e.get('name') for e in trees['.engb'] if e.tag.upper() == 'OBJECTIVE']
            if a != b:
                t.fail(f'{m}: XMLB and engb objective lists differ')
    for act, n in per_act.items():
        if n > S.MAX_OBJECTIVES_PER_ACT:
            t.fail(f'act {act}: {n} objectives > {S.MAX_OBJECTIVES_PER_ACT}')
    if total > S.MAX_OBJECTIVES:
        t.fail(f'{total} objectives > {S.MAX_OBJECTIVES}')
    if ctx.out_exists('Data/missions/missions.engb'):
        t.fail('Data/missions/missions.engb exists and would shadow missions.XMLB')
    # objective() literals in installed scripts; the mission manager finds objectives by name with _stricmp
    # (XMen2.exe 0x488d90 -> 0x672562), so case does not matter
    pat = re.compile(r'\bobjective\s*\(\s*"([^"]+)"')
    x1_defined = S._xml1_objective_names(ctx)
    undefined = collections.defaultdict(set)
    for k, e in reg.items():
        if e['owner'] == 'scripts' and k.endswith('.py'):
            for m in pat.finditer((ctx.out / e['rel']).read_text(encoding='latin-1')):
                if m.group(1).lower() not in defined:
                    undefined[m.group(1)].add(C.script_ref(k))
    lost = {o: sorted(r)[:3] for o, r in undefined.items() if o.lower() in x1_defined}
    if lost:
        t.fail(f'objectives defined in XML1 but in no x1_act file: {lost}')
    t.info('per_act', dict(per_act))
    t.info('objectives', total)
    t.info('undefined_in_xml1_too', {o: sorted(r)[:3] for o, r in undefined.items() if o not in lost})


def t7_providers(ctx, t, reg):
    t.start('T7 providers')
    zones = ctx.x1_zones()
    za = ctx.research_json('scripts/out/zone_acts.json')
    how = collections.Counter()
    for z in zones:
        ref = S.zone_script_ref(ctx, z)
        how[S._zone_script_choice(ctx, z)[1].split(':')[0]] += 1
        if ref is not None:
            if ref != ref.lower() or '\\' in ref or ref.endswith('.py'):
                t.fail(f'{z}: zone_script_ref {ref!r} not normalised')
            if not ctx.out_exists(C.script_rel(ref)):
                t.fail(f'{z}: zone_script_ref {ref} not in <out>')
        act = S.zone_act(ctx, z)
        if act is not None and not (isinstance(act, int) and 1 <= act <= 9):
            t.fail(f'{z}: zone_act {act!r}')
        info = za.get(z)
        prow = S.act_on_entry_plan(ctx)['zones'].get(z) or {}
        if prow.get('entry_act') is not None:
            if act != prow['entry_act']:
                t.fail(f'{z}: zone_act {act} != the act its zone script sets on entry ({prow["entry_act"]})')
        elif info and len(prow.get('acts') or ()) != 1:
            want = info.get('inject_act') or ((info.get('acts') or [None])[0])
            if want != act:
                t.fail(f'{z}: zone_act {act} != zone_acts.json {want}')
        for kind, fn in S.zone_package_extras(ctx, z):
            if fn != C.norm(fn) or fn.endswith(('.py', '.xmlb', '.engb')):
                t.fail(f'{z}: extra {kind} {fn!r} not in packagedef form')
            cands = C.package_entry_files(kind, fn)
            if cands and not any(c in ctx.out_index for c in cands):
                t.fail(f'{z}: extra {kind} {fn} resolves to nothing in <out> ({cands})')
    t.info('zones', len(zones))
    t.info('zonescript_sources', dict(how))
    # script_exists
    for ref in list(S._installable_refs(ctx))[:50] + list(S.NEW_GAME_REFS):
        for v in (ref, ref.upper(), 'Scripts\\' + ref.replace('/', '\\') + '.py', f'scripts/{ref}.py'):
            if not S.script_exists(ctx, v):
                t.fail(f'script_exists({v!r}) is False')
    for v in list(S.FRONTEND_DEAD_X1) + ['no/such/script', '', "loadZone('a','b')"]:
        if S.script_exists(ctx, v):
            t.fail(f'script_exists({v!r}) is True')
    # rewrite_data_tree over everything zones feeds it
    rw = ctx.research_json('scripts/out/inline_rewrites.json')
    inline_ends = S._inline_end_refs(ctx)          # SPEC 19.3: data endSideMission -> generated end script (seat)
    x1api = S._xml1_api(ctx)
    applied, files, changed = set(), 0, 0
    leftovers = collections.defaultdict(set)     # (kind, value) -> rels
    x1_defects = collections.defaultdict(set)
    dead_refs = collections.defaultdict(set)
    rels = [r for r in ctx.x1_rels('') if r.endswith(('.eng', '.xml')) and
            (r.startswith(DATA_PREFIXES) or r in WORLD_TABLES)]
    for rel in rels:
        try:
            root = ctx.read_x1_xml(rel)
        except Exception as e:          # noqa: BLE001
            t.fail(f'{rel}: does not parse ({e})')
            continue
        if root is None:
            continue
        files += 1
        orig = {}
        for el in root.iter():
            for k, v in el.attrib.items():
                orig[(id(el), k)] = v
        before = list(root.iter())
        n = S.rewrite_data_tree(ctx, root, rel)
        kept = {id(el) for el in root.iter()}
        for el in before:                          # SPEC 19.3: a response starting a cut mission is removed
            if id(el) not in kept:
                applied.update(v for v in el.attrib.values() if v in rw)
        changed += n
        again = copy.deepcopy(root)
        if S.rewrite_data_tree(ctx, again, rel) != 0:
            t.fail(f'{rel}: rewrite_data_tree is not idempotent')
        console_file = rel.startswith(('dialogs/', 'ui/'))
        for el in root.iter():
            for k, v in el.attrib.items():
                o = orig.get((id(el), k), v)
                if o in rw and (v == rw[o] or v == inline_ends.get(o)):
                    applied.add(o)
                kl = k.lower()
                if not v or not (S._is_script_attr(kl) or (console_file and kl in S.CONSOLE_ATTRS)):
                    continue
                if v.strip().lower() in S.BOOL_VALUES:
                    continue
                if '(' in v:
                    probs, _ = L.lint_inline(v, ctx.xml2_api)
                    if console_file and kl in S.CONSOLE_ATTRS and L.console_problems(v):
                        leftovers[('console', v)].add(rel)
                    if probs:
                        x1bad = L.lint_inline(o, x1api, forbidden=False)[0] if o == v else []
                        size = any(kind == 'size' for _, kind, _ in probs)
                        (x1_defects if (x1bad and not size) else leftovers)[
                            ('inline', v[:100] + ' :: ' + '; '.join(d for _, _, d in probs[:2]))].add(rel)
                elif L.INLINE_SEP in v:
                    continue
                else:
                    if v != v.strip().lower().replace('\\', '/') or v.endswith('.py'):
                        leftovers[('unnormalised', v)].add(rel)
                    if not S.script_exists(ctx, v):
                        dead_refs[v].add(rel)
    missing = sorted(set(rw) - applied)
    if missing:
        t.fail(f'{len(missing)} inline_rewrites.json keys never applied: {missing[:5]}')
    for (kind, v), rs in sorted(leftovers.items()):
        t.fail(f'{kind}: {v} in {sorted(rs)[:3]}')
    # dead refs must be dead on the XML1 disc as well (not a conversion loss)
    x1_scripts = {C.script_ref(r) for r in ctx.x1_rels('scripts/') if r.endswith('.py')}
    lost = {v: sorted(rs)[:2] for v, rs in dead_refs.items() if C.script_ref(v) in x1_scripts}
    if lost:
        t.fail(f'script refs that exist in XML1 but not in <out>: {lost}')
    t.info('data_files', files)
    t.info('values_changed', changed)
    t.info('inline_rewrites_applied', len(applied))
    t.info('dead_refs_xml1_too', {v: sorted(rs)[:2] for v, rs in sorted(dead_refs.items())})
    t.info('inline_xml1_defects', {k[1]: sorted(v)[:2] for k, v in sorted(x1_defects.items())})


def main(argv=None):
    ap = argparse.ArgumentParser(description='verify the scripts module outputs in a build directory')
    ap.add_argument('--out', required=True)
    ap.add_argument('--base', default=str(C.DEFAULT_BASE))
    ap.add_argument('--no-movies', dest='no_movies', action='store_true',
                    help='the build was made with --no-movies (New Game hook without the intro movie)')
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    reg = _registry(out)
    args = C.default_args(out=str(out), base=a.base, no_movies=a.no_movies)
    try:                                            # the build's content options (scripts_transform depends on them)
        b = json.loads((out / '_build' / 'report.json').read_text(encoding='utf-8'))['build']
        args.blackbird = b.get('blackbird') or 'menu'
        args.newgame = b.get('newgame') or 'chooseteam'
        args.forced_teams = b.get('forced_teams') or 'menu'       # builds before SPEC 19 emitted no xml2-fix call
        args.frontend = b.get('frontend') or 'xml2'               # builds before SPEC 21 kept XML2's front end
        # the build records --no-movies (T4 compares the New Game body without the intro movie then); without this
        # a --no-movies build failed T4 unless the flag was repeated here
        args.no_movies = bool(a.no_movies or b.get('no_movies'))
    except (OSError, ValueError, KeyError, TypeError):
        args.blackbird = 'menu'
    ctx = C.BuildContext(out, a.base, args=args)
    ctx.module = 'scripts_selftest'
    t = T()
    for fn in (t1_install, t2_lint, t3_base, t4_new_game, t5_dialogs, t6_missions, t7_providers):
        fn(ctx, t, reg)
    ok = t.ok()
    rep = {'ok': ok, 'results': t.results, 'provider_report': ctx.report.to_json()}
    (out / '_build').mkdir(exist_ok=True)
    (out / '_build' / 'scripts_selftest.json').write_text(json.dumps(rep, indent=1, default=str), encoding='utf-8')
    for name, r in t.results.items():
        print(f"{'PASS' if not r['fail'] else 'FAIL'} {name}: " +
              ', '.join(f'{k}={v if not isinstance(v, (dict, list)) else len(v)}' for k, v in r['info'].items()))
        for f in r['fail'][:20]:
            print(f'    - {f}')
        if len(r['fail']) > 20:
            print(f"    ... {len(r['fail']) - 20} more")
    print('OK' if ok else 'FAILED', '->', out / '_build' / 'scripts_selftest.json')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
