"""xml1build.prepare.tables - prepare stage P2 `tables` (BUILDER_DESIGN.md 1.5; SPEC.md 27.4).

Regenerates the research tables the build (and P3/P4) read from P1's XML1 trees + the XML2 install, with the logic
of the research generators they replace (those run at import with hard-coded D:/ paths; ported here as functions):

  output (cache)          research copy it replaces            generator                          inputs
  mission_plan.json       scripts/mission_plan.json            scripts/mission_plan.py            assets data/missions, loose+assets refs
  missions/*.xml          scripts/out/data/missions/*.xml      scripts/mission_plan.py            (P3 compiles them to XMLB/engb)
  collisions.json         characters/collisions.json           characters/collisions.py           loose vs the XML2 install
  x2_stats_refs.json      characters/x2_stats_refs.json        characters/x2_unref.py             the XML2 install (+ XMen2.exe)
  names_xml1.json         sound/names_xml1.json                sound/resolve.py + soundrefs.py    loose+assets, default.xbe, sounds/zsds

The research generators ran on Windows in text mode: every file is written with CRLF line ends so the outputs are
byte-identical to the research copies on Owen's PC (the build reads them with json.load / ET, where it makes no
difference). Two deliberate differences from the generators, both for determinism:
  * names_xml1: the generator walked a Python set of candidate names, so when two candidates hash to the same bank
    key the name it kept depended on PYTHONHASHSEED; P2 takes candidates in sorted order (last one wins, as in the
    loop). prepare_equiv reports every key where that choice exists.
  * the XML2 install is indexed like the build's base index: the xml2-fix proxy (dinput.dll, mods/, xml2-fix.*) is
    not part of it (the generators walked everything; no table entry comes from those files).

Cache: <cache>/<disc_id>/prepared/tables-v<VERSION>-<key[:12]>/; key = VERSION + P1's key + the XML2 install's
listing (rel, size, mtime) digest."""
from __future__ import annotations

import collections
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from . import check_cancel, digest, publish, read_stage, rmtree
from . import disc as P1
from .. import common as C

STAGE = 'tables'
VERSION = 4            # 2: SPEC 37 (issue #8) - required="false" -> major="false"; updatedescription counted
                       # 4: issue #49 - names_xml1 also tries character/<voice folder>/<event> (XML1's voice lines);
                       #    skips 3, which PR #41 uses: a shared number would let one branch reuse the other's cache
NEWLINE = '\r\n'
# research-relative path -> file name in the stage directory (Sources.prepared overrides these)
OUTPUTS = {'scripts/mission_plan.json': 'mission_plan.json', 'characters/collisions.json': 'collisions.json',
           'characters/x2_stats_refs.json': 'x2_stats_refs.json', 'sound/names_xml1.json': 'names_xml1.json'}
MISSIONS_DIR = 'missions'                  # the planned XML2 mission text files (scripts/out/data/missions/*.xml)


# ============================================================================================== helpers
def _write_text(path: Path, text: str, encoding='latin-1'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace('\r\n', '\n').replace('\n', NEWLINE).encode(encoding))


def xml2_index(xml2) -> dict:
    """lower rel -> absolute path of every XML2 install file, minus the xml2-fix proxy (common.PROXY_PATTERNS)."""
    root = Path(xml2)
    idx = {}
    for d, dn, fn in os.walk(root):
        rel_d = os.path.relpath(d, root).replace(os.sep, '/')
        if rel_d == '.':
            rel_d = ''
            dn[:] = [x for x in dn if not C.is_proxy_name(x)]
            fn = [x for x in fn if not C.is_proxy_name(x)]
        for f in fn:
            rel = f'{rel_d}/{f}' if rel_d else f
            idx[rel.lower()] = os.path.join(d, f)
    return idx


def xml2_digest(idx: dict) -> str:
    rows = []
    for rel in sorted(idx):
        st = os.stat(idx[rel])
        rows.append((rel, st.st_size, st.st_mtime_ns))
    return digest(rows)


def _tree_files(root: Path, skip=()):
    """lower rel -> path of every file under root (os.walk; skip = lower rels)."""
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            rel = os.path.relpath(p, root).replace(os.sep, '/')
            if rel.lower() in skip:
                continue
            out[rel.lower()] = p
    return out


def load_xmlb(path):
    return C.xmlb.decode(open(path, 'rb').read())


# ============================================================================================== collisions
TEXT_MAP = {'.xml': ['.xmlb'], '.eng': ['.engb', '.xmlb'], '.chr': ['.chrb'], '.nav': ['.navb']}


def parse_x1_text_plain(path):
    """research/characters/common.parse_x1_text (the collisions generator's parser: stray '&' fixed, several roots
    wrapped; NOT sweeplib's robust parser - a file it cannot parse is 'x1_parse_error')."""
    raw = open(path, 'rb').read()
    raw = re.sub(rb'<\?xml[^>]*\?>', b'', raw)
    raw = re.sub(rb'&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)', b'&amp;', raw)
    mr = C.xmlb.MULTI_ROOT.encode()
    w = ET.fromstring(b'<?xml version="1.0" encoding="latin-1"?><%s>%s</%s>' % (mr, raw, mr))
    return w[0] if len(w) == 1 else w


def canon(el):
    return (el.tag.lower(), tuple(sorted((k.lower(), v) for k, v in el.attrib.items())),
            tuple(canon(c) for c in el))


def _category(rel):
    parts = rel.split('/')
    top = parts[0]
    name = parts[-1]
    if top == 'actors':
        stem = os.path.splitext(name)[0]
        if re.fullmatch(r'\d+', stem):
            return 'actors/skin(numeric)'
        if re.fullmatch(r'\d+_.*', stem):
            return 'actors/animdb(NN_name)'
        return 'actors/other(' + ('fightstyle' if stem.startswith(('fightstyle', 'moveset')) else 'misc') + ')'
    if top == 'hud':
        return 'hud/hud_head' if name.startswith('hud_head_') else 'hud/other'
    if top == 'ui' and len(parts) > 2 and parts[1] in ('hud', 'models') and parts[2] == 'characters':
        return f'ui/{parts[1]}/characters'
    if top in ('data',) and len(parts) > 2:
        return 'data/' + parts[1]
    if top == 'data':
        return 'data/' + os.path.splitext(name)[0]
    if top in ('models', 'effects', 'textures', 'maps', 'scripts') and len(parts) > 2:
        return top + '/' + parts[1]
    return top


def _sha1(path):
    import hashlib
    return hashlib.sha1(open(path, 'rb').read()).hexdigest()


def _compare(rel, src, idx):
    stem, ext = os.path.splitext(rel)
    if ext in ('.fre', '.ger'):
        return 'skip', None
    if ext in TEXT_MAP:
        for e in TEXT_MAP[ext]:
            dst = idx.get(stem + e)
            if dst:
                try:
                    a = canon(parse_x1_text_plain(src))
                except Exception:  # noqa: BLE001 - the generator's rule: any parse failure is a status
                    return 'x1_parse_error', dst
                b = canon(load_xmlb(dst))
                return ('identical' if a == b else 'collision'), dst
        return 'x1_only', None
    dst = idx.get(rel)
    if not dst:
        return 'x1_only', None
    if ext == '.py':
        a = open(src, 'rb').read().replace(b'\r\n', b'\n')
        b = open(dst, 'rb').read().replace(b'\r\n', b'\n')
        return ('identical' if a == b else 'collision'), dst
    return ('identical' if _sha1(src) == _sha1(dst) else 'collision'), dst


def collisions(loose: Path, idx: dict, cancel=None) -> dict:
    """characters/collisions.py: every XML1 loose file vs the XML2 file the engine would load for its path."""
    files = _tree_files(loose, skip={P1.MANIFEST})
    res = collections.defaultdict(lambda: collections.defaultdict(list))
    for i, (rel, src) in enumerate(sorted(files.items())):
        if i % 500 == 0:
            check_cancel(cancel)
        status, _ = _compare(rel, src, idx)
        if status == 'skip':
            continue
        res[_category(rel)][status].append(rel)
    return res


# ============================================================================================== x2_stats_refs
_PKG_RE = re.compile(r'packages/generated/characters/(.+?)_(\d{4,5}|xml)(_nc)?\.pkgb$')


def x2_stats_refs(idx: dict, cancel=None) -> list:
    """characters/x2_unref.py: which XML2 herostat/npcstat names anything else in XML2 references."""
    names = {}
    for f in ('herostat', 'npcstat'):
        for st in load_xmlb(idx[f'data/{f}.xmlb']).iter('stats'):
            names[st.get('name').lower()] = f
    refs = collections.defaultdict(set)
    skip = ('data/herostat.xmlb', 'data/herostat.engb', 'data/npcstat.xmlb', 'data/npcstat.engb')
    for i, (rel, p) in enumerate(idx.items()):
        if i % 500 == 0:
            check_cancel(cancel)
        ext = os.path.splitext(rel)[1]
        if rel in skip:
            continue
        if ext in C.XMLB_FAMILY:
            root = load_xmlb(p)
            for el in root.iter():
                for v in el.attrib.values():
                    lv = v.lower()
                    if lv in names:
                        refs[lv].add(rel.split('/')[0] + ':' + ext)
        elif ext == '.py':
            with open(p, encoding='latin-1') as fh:
                text = fh.read()
            for m in re.finditer(r'["\']([^"\'\r\n]{1,40})["\']', text):
                lv = m.group(1).lower()
                if lv in names:
                    refs[lv].add('scripts:.py')
    pk = collections.Counter(_PKG_RE.match(r).group(1) for r in idx if _PKG_RE.match(r))
    exe = open(idx['xmen2.exe'], 'rb').read().lower()
    out = []
    for n, f in sorted(names.items()):
        inexe = (b'\0' + n.encode() + b'\0') in exe
        out.append({'name': n, 'file': f, 'refs': sorted(refs.get(n, [])), 'has_package': pk.get(n, 0),
                    'in_exe': inexe})
    return out


# ============================================================================================== mission plan
_MISSION_REF = re.compile(r"(beginMission|beginSideMission|beginMissionHack|mission)\s*\(\s*['\"]([^'\"]+)['\"]")
_WORLD_MISSION = re.compile(r'<entity name="world"[^>]*\bmission="([^"]+)"')


def _load_mission(mdir: Path, name):
    for ext in ('.eng', '.xml'):
        p = mdir / (name + ext)
        if p.exists():
            with open(p, encoding='latin-1') as fh:
                t = fh.read()
            t = re.sub(r'&(?!(amp|lt|gt|quot|apos|#\d+);)', '&amp;', t)
            try:
                return ET.fromstring(t), p
            except ET.ParseError as e:
                return None, f'{p.as_posix()}: {e}'
    return None, None


def mission_plan(assets: Path, loose: Path):
    """scripts/mission_plan.py: XML1 missions -> XML2 act groups. Returns (plan, {file name: text}) - the plan
    JSON object and the XML2-shaped mission text files (x1_actNN.xml, missions.xml)."""
    mdir = Path(assets) / 'data' / 'missions'
    order = [m.get('name') for m in ET.parse(mdir / 'missions.xml').getroot()]
    order_l = [o.lower() for o in order]
    refs = collections.Counter()
    for root in (loose, assets):
        for dp, dn, fn in os.walk(root):
            for f in fn:
                if f.endswith(('.py', '.eng', '.xml')) and 'missions' not in dp.replace('\\', '/').split('/')[-1:]:
                    try:
                        with open(os.path.join(dp, f), encoding='latin-1') as fh:
                            t = fh.read()
                    except Exception:  # noqa: BLE001 - the generator skipped unreadable files
                        continue
                    for m in _MISSION_REF.finditer(t):
                        refs[m.group(2).lower()] += 1
                    for m in _WORLD_MISSION.finditer(t):
                        refs[m.group(1).lower()] += 1
    all_files = sorted({os.path.splitext(f)[0].lower() for f in os.listdir(mdir)} - {'missions'})
    campaign = list(order_l)
    extra = [m for m in all_files if m not in campaign and m in refs]
    unused = [m for m in all_files if m not in campaign and m not in refs]
    seq = campaign + extra
    missions = {}
    for m in seq:
        root, p = _load_mission(mdir, m)
        if root is None:
            missions[m] = {'file': p, 'objectives': [], 'error': p is not None}
            continue
        objs = [dict(o.attrib) for o in root.iter('OBJECTIVE')]
        missions[m] = {'file': p.name, 'attrs': dict(root.attrib), 'objectives': objs,
                       'required': [h.get('name') for h in root.iter('REQUIREDHERO')],
                       'restricted': [h.get('name') for h in root.iter('RESTRICTEDHERO')],
                       'recommended': [h.get('name') for h in root.iter('RECOMMENDEDHERO')],
                       'mustlive': [h.get('name') for h in root.iter('MUSTLIVEHERO')]}

    def sig(o):
        return (o.get('descname', ''), o.get('description', ''), o.get('count', ''))

    groups = []
    cur = {'missions': [], 'objs': {}}
    for m in seq:
        objs = missions[m]['objectives']
        names = {o['name'].lower(): o for o in objs}
        new = {n for n in names if n not in cur['objs']}
        conflict = [n for n in names if n in cur['objs'] and sig(cur['objs'][n]) != sig(names[n])]
        if cur['missions'] and (len(cur['objs']) + len(new) > 75 or conflict):
            groups.append(cur)
            cur = {'missions': [], 'objs': {}}
        cur['missions'].append(m)
        for n, o in names.items():
            cur['objs'].setdefault(n, o)
    groups.append(cur)

    total = sum(len(g['objs']) for g in groups)
    plan = {'limits': {'files': 25, 'objectives_total': 299, 'objectives_per_act': 75},
            'n_groups': len(groups), 'n_objectives_total': total,
            'unused_mission_files': unused, 'groups': [], 'missions': {}}
    texts = {}
    n_major_false = n_with_update = 0
    for i, g in enumerate(groups, 1):
        gname = f'x1_act{i:02d}'
        plan['groups'].append({'file': gname, 'act': i, 'missions': g['missions'], 'n_objectives': len(g['objs'])})
        for m in g['missions']:
            plan['missions'][m] = {**missions[m], 'act': i, 'group_file': gname}
        root = ET.Element('MISSION', {'act': str(i)})
        for n, o in g['objs'].items():
            # SPEC 37 (issue #8): XML1's required="false" (an optional objective) is the engine's major="false"
            # (the Secondary HUD list; 'Primary'/'Secondary' are XMen2.exe strings). updatedescription (XML1's
            # completion text, read by default.xbe) has no reader in XMen2.exe - both exes know only the objective commands COMPLETE /
            # DECREMENT / HIDE / INCOMPLETE / INCREMENT / SHOW - so it is never written to the XML2 text; it stays
            # in the plan JSON (objectives keep their source attrs above) for a future engine-side text verb, and
            # both attributes are counted instead of silently dropped.
            if o.get('required', '').strip().lower() == 'false':
                n_major_false += 1
            if o.get('updatedescription'):
                n_with_update += 1
            a = {'name': o['name'], 'descname': o.get('descname', o['name']),
                 'enabled': 'false',
                 'major': 'false' if o.get('required', '').strip().lower() == 'false' else 'true',
                 'type': 'normal'}
            if o.get('description'):
                a['description'] = o['description']
            if o.get('count'):
                a['count'] = o['count']
            a['xp'] = o.get('xp', '0')
            ET.SubElement(root, 'OBJECTIVE', dict(sorted(a.items())))
        ET.indent(root)
        texts[gname + '.xml'] = ET.tostring(root, encoding='unicode')
    plan['objectives_major_false'] = n_major_false
    plan['objectives_with_updatedescription'] = n_with_update
    idx = ET.Element('MISSIONS')
    for g in plan['groups']:
        ET.SubElement(idx, 'MISSION', {'name': g['file']})
    ET.indent(idx)
    texts['missions.xml'] = ET.tostring(idx, encoding='unicode')
    return plan, texts


# ============================================================================================== sound names (xml1)
TXT_EXT = ('.xml', '.eng', '.chr', '.nav', '.boy', '.pkg')
_STR_RX = re.compile(r'["\']([A-Za-z0-9_\-./\\ ]{3,80})["\']')
CHARPFX = 'character/'                     # XML1's character-sound prefix (XML2: 'char/')
RANDOM_MAX = 16


def _walk(root, exts):
    for dp, dn, fn in os.walk(root):
        dn.sort()                          # deterministic on any file system (= NTFS order for these names)
        for f in sorted(fn):
            if f.lower().endswith(exts):
                yield os.path.join(dp, f).replace('\\', '/')


def _load_tree_text(path):
    data = open(path, 'rb').read()
    try:
        txt = data.decode('latin-1')
        txt = re.sub(r'<\?xml[^>]*\?>', '', txt)
        return ET.fromstring('<__r>' + txt + '</__r>')
    except Exception:  # noqa: BLE001 - soundrefs.load_tree: an unparsable file contributes nothing
        return None


def _collect_xml1(loose, assets):
    """sound/soundrefs.collect('xml1'): every attribute of every XML1 text data file (loose wins over assets by
    rel) and every quoted string of every XML1 script -> [(file, tag, attr, value)]."""
    refs, seen = [], set()
    for root in (loose, assets):
        for p in _walk(root, TXT_EXT):
            rel = os.path.relpath(p, root).replace('\\', '/').lower()
            if rel in seen:
                continue
            seen.add(rel)
            t = _load_tree_text(p)
            if t is None:
                continue
            for el in t.iter():
                for k, v in el.attrib.items():
                    refs.append((rel, el.tag, k, v))
    scripts = []
    for r in (loose, assets):
        for p in _walk(r, ('.py',)):
            txt = open(p, 'rb').read().decode('latin-1')
            for m in _STR_RX.finditer(txt):
                scripts.append((os.path.relpath(p, r).replace('\\', '/'), 'script', 'str', m.group(1)))
    return refs, scripts


VOICE_STATS = ('data/herostat.eng', 'data/npcstat.eng')   # XML1 stats whose sounddirs name the voice folders
SHARED_SOUNDS = 'data/shared_sounds.xml'                  # XML1's SOUNDTABLE: the character event names
VOICE_BANK = 'x_voice'                                    # the global bank both games keep the voice lines in


def xml1_voice_folders(loose: Path, assets: Path):
    """(voice folders, events): every XML1 herostat / npcstat sounddir as the folder the engine looks its voice
    events up in (simlookup.voice_dir: wolver_m -> wolver_v) and every event name of XML1's shared_sounds, both
    sorted. XML1's x_voice bank names its lines 'character/<voice folder>/<event>' (issue #49); names_xml1 tries
    those names and P4 `sound` lets these folders' XML1 entries win the merge. Loose wins over assets by rel."""
    from ..lib.simlookup import voice_dir
    dirs, events = set(), set()
    for rel in VOICE_STATS + (SHARED_SOUNDS,):
        p = next((r / rel for r in (loose, assets) if (r / rel).is_file()), None)
        t = _load_tree_text(p) if p is not None else None
        if t is None:
            continue
        for el in t.iter():
            if rel == SHARED_SOUNDS:
                events.update(v.strip().lower() for v in el.attrib.values() if re.fullmatch(r'[a-z0-9_]{2,32}',
                                                                                           v.strip().lower()))
            elif el.get('sounddir', '').strip():
                dirs.add(voice_dir(el.get('sounddir')))
    return sorted(dirs), sorted(events)


def _exe_strings(path):
    d = open(path, 'rb').read()
    for m in re.finditer(rb'[\x20-\x7e]{4,}', d):
        s = m.group().decode()
        if re.fullmatch(r'[a-z0-9_]+(/[a-z0-9_%]+)+', s.lower()):
            yield s.lower()


def _elf_np(names, seeds=None):
    """zhash.elf_hash over many latin-1 names at once (numpy; the per-character loop runs over columns)."""
    import numpy as np
    enc = [n.encode('latin-1') for n in names]
    n = len(enc)
    h = np.zeros(n, dtype=np.uint64) if seeds is None else np.asarray(seeds, dtype=np.uint64).copy()
    if n == 0:
        return h
    lens = np.fromiter((len(e) for e in enc), dtype=np.int64, count=n)
    width = int(lens.max())
    buf = np.frombuffer(b''.join(e.ljust(width, b'\0') for e in enc), dtype=np.uint8).reshape(n, width)
    m32, top = np.uint64(0xFFFFFFFF), np.uint64(0xF0000000)
    for j in range(width):
        c = buf[:, j].astype(np.uint64)
        c = np.where((c >= 0x61) & (c <= 0x7A), c - np.uint64(0x20), c)
        nh = ((h << np.uint64(4)) + c) & m32
        g = nh & top
        nh = (nh ^ (g >> np.uint64(24))) & (~g & m32)
        h = np.where(lens > j, nh, h)
    return h


def _random_chain(h_arr, keys_arr):
    """for seed hashes h_arr: the resolve.py random-variant loop - variant i ('/***RANDOM***/i' chained on the
    seed) is looked at for i = 0 and 1, and for i >= 2 only while every variant 1..i-1 was a bank key.
    Returns {i: (row indices whose variant i is a key, the variant hashes)}."""
    import numpy as np
    out = {}
    alive = np.arange(len(h_arr))
    for i in range(RANDOM_MAX):
        if len(alive) == 0:
            break
        v = _elf_np([f'/***RANDOM***/{i}'] * len(alive), h_arr[alive])
        hit = np.isin(v, keys_arr)
        if hit.any():
            out[i] = (alive[hit], v[hit])
        if i > 0:
            alive = alive[hit]
    return out


def names_xml1(loose: Path, assets: Path, xbox: Path, cancel=None):
    """sound/resolve.py for XML1: bank path -> {key hex: name}, with the sorted-candidate rule (module doc).
    Returns (result, ambiguous) - ambiguous: [(bank, key hex, [every candidate name for it])] where the choice
    of name depended on candidate order."""
    import numpy as np
    from ..lib import zsnd
    from ..lib.zhash import elf_hash
    refs, scripts = _collect_xml1(loose, assets)
    pool = set()
    for f, tag, k, v in refs + scripts:
        if v and len(v) < 120 and not re.fullmatch(r'[-0-9. ]+', v):
            pool.add(v.replace('\\', '/').lower().strip())
    pool |= set(_exe_strings(Path(xbox) / 'default.xbe'))
    events = set(n for n in pool if re.fullmatch(r'[a-z0-9_]{2,32}', n))
    for n in pool:
        parts = n.split('/')
        if len(parts) >= 2:
            events.add(parts[-1])
            if len(parts) >= 3:
                events.add('/'.join(parts[2:]))
    vdirs, vevents = xml1_voice_folders(loose, assets)
    voice = {f'{CHARPFX}{d}/{e}' for d in vdirs for e in vevents}
    pool_sorted = sorted(pool)
    pool_h = _elf_np(pool_sorted)
    events_sorted = sorted(events)
    root = Path(xbox) / 'sounds' / 'zsds'
    result, ambiguous = {}, []
    for p in _walk(root, ('.zss', '.zsm')):
        check_cancel(cancel)
        b = zsnd.load(p, strict=False)
        rel = os.path.relpath(p, root).replace('\\', '/')
        base = os.path.basename(p).rsplit('.', 1)[0]
        zone = base.rsplit('_', 1)[0] if re.search(r'_[acdmv]$', base) else base
        keys = set()
        for s in b.sounds:
            keys.update(s.hashes)
        for t in b.tracks:
            keys.update(t.hashes)
        if not keys:
            continue
        keys_arr = np.fromiter(keys, dtype=np.uint64, count=len(keys))
        # the bank's candidates (resolve.py): the pool, zone-prefixed death/zone-shared names, its music name, and
        # '<character prefix><bank>/<event>' for every event word
        extra = set()
        for n in pool:
            if n.startswith('death_style') or n.startswith('zone_sh'):
                extra.add(zone + '/' + n)
        extra.add('music/' + base)
        extra.update(CHARPFX + base + '/' + e for e in events_sorted)
        # XML1's voice lines: 'character/<voice folder>/<event>' for every stats sounddir, in the global voice bank
        # only (issue #49; no other XML1 bank names one)
        if base == VOICE_BANK:
            extra.update(voice)
        extra -= pool
        extra_sorted = sorted(extra)
        cands = pool_sorted + extra_sorted
        hs = np.concatenate([pool_h, _elf_np(extra_sorted)])
        # every (key, candidate rank, sub-order, name) assignment the loop would make; sorted candidate order,
        # direct hash before the random variants: the last assignment per key wins
        order = sorted(range(len(cands)), key=cands.__getitem__)
        rank = np.empty(len(cands), dtype=np.int64)
        rank[np.asarray(order, dtype=np.int64)] = np.arange(len(cands))
        assign = collections.defaultdict(list)            # key -> [(rank, sub, name)]
        direct = np.nonzero(np.isin(hs, keys_arr))[0]
        for r in direct:
            assign[int(hs[r])].append((int(rank[r]), 0, cands[r]))
        for i, (rows, vals) in _random_chain(hs, keys_arr).items():
            for r, v in zip(rows, vals):
                assign[int(v)].append((int(rank[r]), 1 + i, cands[r] + '/***RANDOM***/%d' % i))
        names = {}
        for h, lst in assign.items():
            lst.sort()
            # a voice name wins a key it shares with another guess (ELF hash collisions: a pool string or a
            # 'character/x_voice/<word>' guess); the engine only ever looks the voice name up there
            pick = [x for x in lst if x[2].split('/***RANDOM***/')[0] in voice] if base == VOICE_BANK else []
            names[h] = (pick or lst)[-1][2]
            if len({x[2] for x in lst}) > 1:
                ambiguous.append((rel, '%08x' % h, sorted({x[2] for x in lst})))
        # sample-file-name keyed sounds (XML1 layered death-style parts)
        for f in b.files:
            fn = b.file_name(f).rsplit('.', 1)[0].lower()
            h = elf_hash(fn)
            if h in keys and h not in names:
                names[h] = fn
        result[rel] = {'%08x' % h: n for h, n in sorted(names.items())}
    return result, ambiguous


# ============================================================================================== the stage
def stage_key(disc_stage: dict, xml2_dig: str) -> str:
    return digest({'stage': STAGE, 'version': VERSION, 'disc': disc_stage.get('key'), 'xml2': xml2_dig})


def run(disc_dir, xml2, *, log=print, cancel=None, force=False) -> dict:
    """P2 from a published P1 directory + the XML2 install; reuses the published output while its key matches.
    Returns {'dir', 'stage', 'cached'}."""
    t0 = time.time()
    disc_dir = Path(disc_dir)
    dst = read_stage(disc_dir)
    if not dst or dst.get('stage') != P1.STAGE:
        raise RuntimeError(f'{disc_dir} is not a published P1 disc directory')
    idx = xml2_index(xml2)
    key = stage_key(dst, xml2_digest(idx))
    final = disc_dir.parent / 'prepared' / f'{STAGE}-v{VERSION}-{key[:12]}'
    st = read_stage(final)
    if st and st.get('key') == key and not force:
        log(f'[prepare] tables: cached ({final})')
        return {'dir': final, 'stage': st, 'cached': True}
    partial = final.with_name(final.name + '.partial')
    rmtree(partial)
    partial.mkdir(parents=True)
    loose, assets, xbox = disc_dir / P1.LOOSE, disc_dir / P1.ASSETS, disc_dir / P1.XBOX
    timings, counts = {}, {}

    t = time.time()
    plan, texts = mission_plan(assets, loose)
    _write_text(partial / 'mission_plan.json', json.dumps(plan, indent=1))
    for name, text in texts.items():
        _write_text(partial / MISSIONS_DIR / name, text)
    counts.update(mission_groups=plan['n_groups'], objectives=plan['n_objectives_total'], mission_files=len(texts),
                  objectives_major_false=plan['objectives_major_false'],
                  objectives_with_updates=plan['objectives_with_updatedescription'])
    timings['mission_plan'] = round(time.time() - t, 1)
    check_cancel(cancel)

    t = time.time()
    col = collisions(loose, idx, cancel)
    _write_text(partial / 'collisions.json', json.dumps(col, indent=1, sort_keys=True))
    counts['collision_categories'] = len(col)
    timings['collisions'] = round(time.time() - t, 1)

    t = time.time()
    refs = x2_stats_refs(idx, cancel)
    _write_text(partial / 'x2_stats_refs.json', json.dumps(refs, indent=1))
    counts['x2_stats_names'] = len(refs)
    timings['x2_stats_refs'] = round(time.time() - t, 1)

    t = time.time()
    names, ambiguous = names_xml1(loose, assets, xbox, cancel)
    _write_text(partial / 'names_xml1.json', json.dumps(names, indent=1))
    counts.update(sound_banks_named=len(names), sound_names=sum(len(v) for v in names.values()),
                  sound_keys_ambiguous=len(ambiguous))
    timings['names_xml1'] = round(time.time() - t, 1)

    stage = {'stage': STAGE, 'version': VERSION, 'key': key, 'disc_key': dst.get('key'), 'xml2': str(xml2),
             'counts': counts, 'timings': timings, 'ambiguous_sound_keys': ambiguous,
             'seconds': round(time.time() - t0, 1)}
    stage = publish(partial, final, stage)
    log(f'[prepare] tables: done in {stage["seconds"]}s: {counts}; {timings}')
    # stale P2 directories of this disc (another key) are removed once the new one is published
    for old in final.parent.glob(f'{STAGE}-v*'):
        if old != final and not old.name.endswith('.partial'):
            rmtree(old)
    return {'dir': final, 'stage': stage, 'cached': False}
