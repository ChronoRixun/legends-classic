"""lcsave command line.

  python -m lcsave convert  <old.save> <out.lcsave> --build DIR [--slot N] [--report out.json]
  python -m lcsave dump     <file> [--build DIR] [--out dump.json]        old or new save -> canonical JSON
  python -m lcsave verify   <old.save> --build DIR [--out DIR]            convert, re-read, reverse check, report
  python -m lcsave eras     --reference DIR --era CV=DIR [...] [--out legacy_eras.json]      (developer)
  python -m lcsave catalogue --build DIR [--previous catalogue.json] [--out catalogue.json]  (developer)
  python -m lcsave corpus   <folder> --build DIR --out DIR                every *.save under folder (developer)
  python -m lcsave savefiles --build DIR [--check] [--content-version N]  write the build's save-format data
      files (catalogue.lcc, legacy.lcm, the .lcbind files; SPEC-new-save 3.4/5.3), or with --check verify that
      the files in DIR are exactly the set its data produces (what the build's V39 runs)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(HERE))          # tools/ (xmlb, the package itself)

from lcsave import binds, catalogue as catmod, convert, dump as dumpmod, legacy, container  # noqa: E402


def cmd_eras(a):
    ref = binds.Binds(a.reference)
    ref_tables = ref.hash_tables()
    from .conversations import build_tables
    if os.path.isdir(os.path.join(ref.build, 'Packages', 'generated', 'maps')):
        ref_tables['conversation_bits'] = build_tables(ref.build, ref.all_zone_files())
    ref_tables['content_version'] = a.content_version
    model = {'reference': ref_tables, 'reference_release': a.reference_release, 'eras': {}}
    for spec in a.era:
        cv, path = spec.split('=', 1)
        b = binds.Binds(path)
        model['eras'][cv] = legacy.build_era_entry(b, ref_tables, ref)
        print(f'era {cv}: ' + ', '.join(f'{d}={"same" if v == "same" else "own"}' for d, v in model['eras'][cv].items()
                                       if d in legacy.LIST_DOMAINS + legacy.DICT_DOMAINS and v != 'same')
              + f'; zones differing {len(model["eras"][cv]["zones"])}')
    out = a.out or legacy.ERAS_FILE
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(model, f, indent=0, sort_keys=True)
        f.write('\n')
    print('wrote', out)


def cmd_catalogue(a):
    cat = catmod.Catalogue.load(a.previous) if a.previous else catmod.Catalogue()
    b = binds.Binds(a.build)
    tables = catmod.tables_from_hashes(b.hash_tables())
    if a.eras:
        model = legacy.load_eras(a.eras)
        for era in legacy.eras_of(model):
            for tag, hashes in catmod.tables_from_hashes(era.tables).items():
                for h in hashes:
                    tables.setdefault(tag, []).append(h)
    cat.update(tables, a.content_version)
    out = a.out or catmod.CATALOGUE_FILE
    cat.save(out)
    print('wrote', out, cat.counts())


def cmd_convert(a):
    env = convert.Environment(a.build)
    old = open(a.old, 'rb').read()
    res = convert.convert_slot(old, os.path.basename(a.old), env, slot=a.slot)
    if res.refused:
        print('REFUSED:', res.refused)
        return 2
    with open(a.out, 'wb') as f:
        f.write(res.file_bytes)
    print(f'wrote {a.out}: {len(res.file_bytes)} bytes;', res.summary())
    if a.report:
        json.dump(res.report(), open(a.report, 'w'), indent=1)
    return 0


def cmd_dump(a):
    buf = open(a.file, 'rb').read()
    env = convert.Environment(a.build) if a.build else None
    d = dumpmod.dump_any(buf, env)
    text = json.dumps(d, indent=1, sort_keys=True)
    if a.out:
        open(a.out, 'w', encoding='utf-8').write(text)
    else:
        print(text)
    return 0


def cmd_verify(a):
    env = convert.Environment(a.build)
    rep = convert.verify_file(a.old, env, out_dir=a.out)
    print(json.dumps(rep, indent=1))
    return 0 if rep['ok'] else 1


def cmd_corpus(a):
    env = convert.Environment(a.build)
    results = convert.verify_corpus(a.folder, env, a.out)
    print(json.dumps({k: v['status'] for k, v in results.items()}, indent=1))
    return 0


def cmd_savefiles(a):
    from lcsave import lcfiles
    cv = a.content_version
    if cv is None:
        try:
            from xml1builder import CONTENT_VERSION
            cv = CONTENT_VERSION
        except ImportError:
            cv = 0
    if a.check:
        want, problems = lcfiles.write_build_files(a.build, cv)
        bad = list(problems)
        for rel, blob in sorted(want.items()):
            p = os.path.join(a.build, rel.replace('/', os.sep))
            if not os.path.isfile(p):
                bad.append(f'{rel}: missing')
            elif open(p, 'rb').read() != blob:
                bad.append(f'{rel}: differs from the computed set')
            else:
                try:
                    (lcfiles.read_lcbind if rel.endswith('.lcbind')
                     else lcfiles.read_catalogue_lcc if rel.endswith('.lcc')
                     else lcfiles.read_conversation_lcm if rel.endswith('/conversation.lcm')
                     else lcfiles.read_legacy_lcm)(blob)
                except lcfiles.LCFileError as e:
                    bad.append(f'{rel}: {e}')
        import glob as g
        have = {os.path.relpath(p, a.build).replace(os.sep, '/')
                for p in g.glob(os.path.join(a.build, 'Data', '**', '*.lcbind'), recursive=True)}
        bad += [f'{rel}: no data file of this build owns it' for rel in sorted(have - set(want))]
        if bad:
            print('savefiles check FAILED:')
            for b in bad:
                print(' -', b)
            return 1
        print(f'savefiles check OK: {len(want)} files; content fingerprint',
              lcfiles.content_fingerprint(a.build))
        return 0
    files, problems = lcfiles.write_build_files(a.build, cv)
    for prob in problems:
        print('catalogue problem:', prob)
    for rel, blob in sorted(files.items()):
        p = os.path.join(a.build, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(blob)
    print(f'wrote {len(files)} save files under {a.build}; content fingerprint',
          lcfiles.content_fingerprint(a.build))
    return 1 if problems else 0


def main(argv=None):
    p = argparse.ArgumentParser(prog='lcsave')
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('eras'); s.add_argument('--reference', required=True); s.add_argument('--reference-release', default='0.1.10')
    s.add_argument('--content-version', type=int, default=13)
    s.add_argument('--era', action='append', default=[]); s.add_argument('--out'); s.set_defaults(fn=cmd_eras)
    s = sub.add_parser('catalogue'); s.add_argument('--build', required=True); s.add_argument('--previous')
    s.add_argument('--eras'); s.add_argument('--content-version', type=int, default=13); s.add_argument('--out'); s.set_defaults(fn=cmd_catalogue)
    s = sub.add_parser('convert'); s.add_argument('old'); s.add_argument('out'); s.add_argument('--build', required=True)
    s.add_argument('--slot', type=int, default=0); s.add_argument('--report'); s.set_defaults(fn=cmd_convert)
    s = sub.add_parser('dump'); s.add_argument('file'); s.add_argument('--build'); s.add_argument('--out'); s.set_defaults(fn=cmd_dump)
    s = sub.add_parser('verify'); s.add_argument('old'); s.add_argument('--build', required=True); s.add_argument('--out'); s.set_defaults(fn=cmd_verify)
    s = sub.add_parser('corpus'); s.add_argument('folder'); s.add_argument('--build', required=True); s.add_argument('--out', required=True); s.set_defaults(fn=cmd_corpus)
    s = sub.add_parser('savefiles'); s.add_argument('--build', required=True); s.add_argument('--check', action='store_true')
    s.add_argument('--content-version', type=int, default=None); s.set_defaults(fn=cmd_savefiles)
    a = p.parse_args(argv)
    return a.fn(a) or 0


if __name__ == '__main__':
    sys.exit(main())
