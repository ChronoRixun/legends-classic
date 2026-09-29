"""Step 3: every XML1 path that also exists in XML2 (after XML1->XML2 extension mapping), identical vs different.

Sources: xml1_loose (all .fb contents) + loose non-bundle files in xml1_assets (data/missions, data/personal,
scripts/menus, scripts/missions, textures/*, ui/fonts, ...). .fre/.ger are skipped (XML2 PC ships English only)
but counted.
Comparison:
  .igb / binary     byte-identical?
  text XML          XML1 parsed (robust normaliser, attrs lowercased+sorted) vs XML2 XMLB decoded, compared
                    canonically (tags case-folded, attrs lowercased+sorted, values exact, child order kept);
                    'same_semantics_diff_bytes' = canonical equal
  .py               compared after CRLF/trailing-whitespace normalisation
Writes collisions.json.
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import collections, hashlib, json, os, sys

sys.path.insert(0, _REPO + r'/research/sweep')
from sweeplib import parse_text_xml_robust, walk_files, load_xmlb, X1, X1A, X2
import xmlb

SWEEP = _REPO + r'/research/sweep'
TEXT_MAP = {'.xml': ['.xmlb'], '.eng': ['.xmlb', '.engb'], '.chr': ['.chrb'], '.nav': ['.navb']}
GLOBAL_TABLES = {'herostat', 'npcstat', 'items', 'item_ents', 'common_ents', 'talents', 'shared_talents',
                 'stat_rules', 'colors', 'shared_nodes', 'shared_anims', 'shared_sounds', 'shared_combat_events',
                 'shared_powerups', 'values', 'zoneinfo', 'strings', 'codex', 'dangerroom', 'trivia', 'credits',
                 'review_paths', 'boltonactoranims', 'autospend', 'team_bonus', 'styles', 'xtraction_points',
                 'loadpoint_list'}


def canon(el):
    return (el.tag.lower(), tuple(sorted((k.lower(), v) for k, v in el.attrib.items())),
            tuple(canon(c) for c in el))


def canon_diff(a, b, path='', out=None, limit=8):
    """collect a few human-readable differences"""
    if out is None:
        out = []
    if len(out) >= limit:
        return out
    if a[0] != b[0]:
        out.append('%s: tag %s != %s' % (path, a[0], b[0]))
        return out
    da, db = dict(a[1]), dict(b[1])
    for k in sorted(set(da) | set(db)):
        if da.get(k) != db.get(k):
            out.append('%s/%s[@%s]: xml1=%r xml2=%r' % (path, a[0], k, da.get(k), db.get(k)))
            if len(out) >= limit:
                return out
    if len(a[2]) != len(b[2]):
        out.append('%s/%s: %d children vs %d' % (path, a[0], len(a[2]), len(b[2])))
    for x, y in zip(a[2], b[2]):
        canon_diff(x, y, path + '/' + a[0], out, limit)
        if len(out) >= limit:
            break
    return out


def norm_py(b):
    return b'\n'.join(l.rstrip() for l in b.replace(b'\r\n', b'\n').split(b'\n')).strip()


def category(rel):
    parts = rel.split('/')
    if parts[0] == 'data' and len(parts) > 2:
        return 'data/' + parts[1]
    if parts[0] == 'ui' and len(parts) > 2:
        return 'ui/' + parts[1]
    if parts[0] == 'textures' and len(parts) > 2:
        return 'textures/' + parts[1]
    return parts[0]


def main():
    x2 = walk_files(X2)
    x1 = walk_files(X1)
    x1.pop('_fb_manifest.json', None)
    x1a = {k: v for k, v in walk_files(X1A).items() if not k.endswith('.fb')}
    src = dict(x1a)
    src.update(x1)  # bundle copy wins where both exist
    both_sources = sorted(set(x1) & set(x1a))
    res = {}
    skipped_lang = 0
    for rel, p in sorted(src.items()):
        base, ext = os.path.splitext(rel)
        if ext in ('.fre', '.ger'):
            skipped_lang += 1
            continue
        if rel in ('on', 'off'):
            continue
        targets = [base + e for e in TEXT_MAP.get(ext, [ext])]
        hit = [t for t in targets if t in x2]
        if not hit:
            res[rel] = {'status': 'new'}
            continue
        r = {'xml2': hit}
        if ext in TEXT_MAP:
            try:
                a = canon(parse_text_xml_robust(p))
            except Exception as e:
                r['status'] = 'xml1_parse_error'
                r['err'] = str(e)
                res[rel] = r
                continue
            b = canon(load_xmlb(x2[hit[0]]))
            if a == b:
                r['status'] = 'identical'
            else:
                r['status'] = 'different'
                r['diff'] = canon_diff(a, b)
                # size signal
                r['xml1_nodes'] = sum(1 for _ in parse_text_xml_robust(p).iter())
                r['xml2_nodes'] = sum(1 for _ in load_xmlb(x2[hit[0]]).iter())
        elif ext == '.py':
            r['status'] = 'identical' if norm_py(open(p, 'rb').read()) == norm_py(open(x2[hit[0]], 'rb').read()) \
                else 'different'
        else:
            da, db = open(p, 'rb').read(), open(x2[hit[0]], 'rb').read()
            r['status'] = 'identical' if da == db else 'different'
            if da != db:
                r['size'] = [len(da), len(db)]
        res[rel] = r
    summ = collections.defaultdict(collections.Counter)
    for rel, r in res.items():
        summ[category(rel)][r['status']] += 1
    data_coll = {rel: r for rel, r in res.items() if rel.startswith('data/') and r['status'] != 'new'}
    data_tables = {}
    for rel, r in sorted(data_coll.items()):
        name = os.path.splitext(rel)[0].split('/')
        top = name[1] if len(name) == 2 else name[1] + '/*'
        data_tables[rel] = {'status': r['status'], 'global_table': len(name) == 2 and name[1] in GLOBAL_TABLES,
                            'diff_sample': r.get('diff', [])[:3]}
    out = {'summary_by_category': {k: dict(v) for k, v in sorted(summ.items())},
           'skipped_fre_ger': skipped_lang,
           'files_in_both_loose_and_assets': len(both_sources),
           'data_collisions': data_tables,
           'files': res}
    json.dump(out, open(os.path.join(SWEEP, 'collisions.json'), 'w'), indent=1, sort_keys=True)
    tot = collections.Counter(r['status'] for r in res.values())
    print('total', dict(tot), 'skipped fre/ger', skipped_lang)
    for k, v in sorted(summ.items()):
        print('  %-24s %s' % (k, dict(v)))
    print('data collisions:')
    for rel, d in data_tables.items():
        if not rel.startswith(('data/fightstyles', 'data/powerstyles', 'data/entities', 'data/aipatterns',
                               'data/weapons', 'data/talents', 'data/missions', 'data/personal')):
            print('   ', rel, d['status'], 'GLOBAL' if d['global_table'] else '', d['diff_sample'][:1])
    sub = collections.Counter((rel.split('/')[1], d['status']) for rel, d in data_tables.items() if rel.count('/') > 1)
    print('data subdir collisions:', dict(sub))


if __name__ == '__main__':
    main()
