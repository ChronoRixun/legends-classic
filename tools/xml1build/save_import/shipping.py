"""Compile a private, evidence-backed import ledger against owned build inputs.

No stock ledger is invented here. Native byte IDs, checkpoint recipes, final
script storage and progression policies must be supplied with source receipts.
Only names, indices and hashes are extracted; source files are never written.
"""
from __future__ import annotations

import copy
import json
import re

from lcsave import convert, keys, typed_registry

from .errors import ImportRefusal
from .identities import item_rows, talent_rows
from .source import bounded_read, digest, safe_path, TITLE_ID
from .tables import (build_files, ImportTable, installed_catalogue, MAX_TABLE, read_json, TABLE_REL,
                     validate_source_profile, validate_target_defaults)


def _require(ok, reason):
    if not ok:
        raise ImportRefusal('BUILD', reason)


def _source_file(ctx, name):
    _require(isinstance(name, str) and name == name.lower() and '\\' not in name and ':' not in name
             and not name.startswith('/') and all(p not in ('', '.', '..') for p in name.split('/')),
             'Invalid source receipt path.')
    path = (ctx.sources.x1_xbox / 'default.xbe') if name == 'default.xbe' else ctx.x1_path(name)
    _require(path is not None, 'A source receipt file is absent: ' + name)
    return safe_path(path)


def _indices(rows, maximum):
    _require(isinstance(rows, dict) and all(isinstance(k, str) and re.fullmatch(r'0|[1-9][0-9]{0,2}', k)
             and int(k) <= maximum for k in rows), 'Source index ledgers require unique canonical decimal keys.')
    return {int(k): v for k, v in rows.items()}


def from_owned_inputs(ctx):
    """Read-only constructor; savefiles owns the atomic registered write."""
    try:
        raw = bounded_read(safe_path(ctx.args.import_ledger), MAX_TABLE)
        ledger = read_json(raw)
        _require(ledger['schema'] == 1 and isinstance(ledger['evidence'], list)
                 and bool(ledger['evidence']) and all(isinstance(e, str) and e for e in ledger['evidence']),
                 'A private import ledger needs explicit evidence references.')
        receipts = ledger['source_files']
        _require(isinstance(receipts, dict) and 3 <= len(receipts) <= 512
                 and {'default.xbe', 'data/herostat.eng', 'data/items.eng'} <= receipts.keys(),
                 'The source ledger must pin the executable, herostat and item definitions.')
        owned, total = {}, 0
        for name, want in sorted(receipts.items()):
            _require(isinstance(want, str) and re.fullmatch('[0-9a-f]{64}', want), 'Invalid source receipt digest.')
            data = bounded_read(_source_file(ctx, name), 64 << 20)
            total += len(data)
            _require(total <= 128 << 20, 'The source ledger exceeds its input budget.')
            _require(digest(data) == want, 'The source ledger does not match the owned file: ' + name)
            owned[name] = data
        from ..prepare import xbe
        xbe.check_xml1(xbe.parse(owned['default.xbe']))
        from ..common import parse_x1_text
        herostat = parse_x1_text(owned['data/herostat.eng'])
        heroes = {e.get('name').lower(): e for e in herostat.iter()
                  if e.tag.lower() == 'stats' and e.get('name')}
        profile = copy.deepcopy(ledger['source_profile'])
        profile.update(title_id=TITLE_ID, xbe_sha256=digest(owned['default.xbe']))
        if profile.get('kind') == 'recomp':
            profile['herostat_sha256'] = digest(owned['data/herostat.eng'])
        try:
            recomp, names, _ = validate_source_profile(profile)
        except ImportRefusal as exc:
            raise ImportRefusal('BUILD', 'The private source profile is invalid.', source_error=exc.code) from exc
        _require(len(names) == len(set(n.lower() for n in names)) and all(n.lower() in heroes for n in names),
                 'The explicit source roster disagrees with the owned herostat.')
        mappings = copy.deepcopy(ledger['mappings'])
        _require(not {'schema', 'source', 'target_files', 'release_ready', 'acceptance', 'provenance'} & mappings.keys(),
                 'The ledger cannot override generated binding or admission fields.')
        _require(bool(mappings.get('checkpoints')) and bool(mappings.get('xp_thresholds'))
                 and mappings.get('quantity_policy') in ('includes_equipped', 'excludes_equipped'),
                 'The ledger needs checkpoint, XP and carried/equipped policy evidence.')
        persistent = [r for r in mappings.get('variables', []) if r.get('kind') != 'transient']
        if persistent:
            from .. import scripts
            storage = scripts._rjson(ctx, 'var_storage.json')
            narrowed = {spec.key: spec for spec in scripts._narrow_specs(ctx)}
            for row in persistent:
                _require(row['family'] in ('mission', 'game'), 'Unknown source variable family.')
                key = ('m:' if row['family'] == 'mission' else 'g:') + row['name'].lower()
                final = storage.get(key)
                _require(final is not None and final['kind'] in ('pack', 'flag'),
                         'A persistent variable has no final campaign-lifetime storage: ' + key)
                width = narrowed[key].k if key in narrowed else int(final['nbits'])
                row.update(kind=final['kind'], target=final['gamevar'], first_bit=int(final['first_bit']),
                           width=width, signed=bool(final['signed']))
        from .. import loot
        economy, _, _ = loot.parse_sidecar(bounded_read(ctx.out / 'Data/x1economy.txt', 1 << 20))
        items = parse_x1_text(owned['data/items.eng'])
        declarations = [e for e in items.iter() if e.tag.lower() == 'item']
        mappings['items'] = item_rows(declarations, economy,
            source_maxima=_indices(ledger['source_maxima'], 159), pack_limits=ledger['pack_limits'])
        catalogue = installed_catalogue(bounded_read(ctx.out / 'Data/lcsave/catalogue.lcc', 16 << 20))
        env = convert.Environment(str(ctx.out), catalogue=catalogue)
        legal = {}
        for hero in names:
            roots = [heroes[hero.lower()]]
            for name in ledger.get('talent_files', {}).get(hero, []):
                _require(name in owned, 'Every talent declaration file needs a source receipt.')
                roots.append(parse_x1_text(owned[name]))
            legal[hero] = [e.get('name') for root in roots for e in root.iter()
                           if e.tag.lower() == 'talent' and e.get('name')]
        captured = ledger.get('native_talents', {})
        _require(recomp or bool(captured), 'Retail needs an evidence-backed native talent byte ledger.')
        mappings['talents'] = talent_rows(_indices(captured, 255), legal, env.binds)
        for row in mappings['heroes'].values():
            _require(any(n.lower() == row['target'].lower() for n in env.binds.stat[1:env.binds.hero_count + 1]),
                     'A source hero has no installed target identity.')
        registry = typed_registry.load_registry(bounded_read(ctx.out / 'Data/lcsave/typed-entity-ids.txt', 4 << 20))
        ImportTable.validate_mapping(mappings, names, recomp=recomp,
                                     economy={r['name'].lower(): r for r in economy}, registry=registry)
        validate_target_defaults(mappings, env)
        for name, row in mappings.get('target_defaults', {}).items():
            row['hero'] = env.id_of('STAT', keys.key_hash(name))

        def resolve(domain, *fields):
            _require(env.id_of(domain, keys.key_hash(*fields)),
                     'A ledger identity is absent from the installed ' + domain + ' catalogue.')

        for row in mappings['heroes'].values():
            for attribute in {'skin', *row.get('skins', {}).values()}:
                resolve('COST', row['target'], attribute)
        for recipe in mappings['checkpoints']:
            resolve('ZONE', recipe['target_zone'])
            for fields in recipe['objectives'].values():
                resolve('OBJV', *fields)
            for fields in recipe.get('xtraction', []):
                resolve('XPNT', *fields)
        # Read receipts again before returning; no mixed-source publication.
        for name, want in sorted(receipts.items()):
            _require(digest(bounded_read(_source_file(ctx, name), 64 << 20)) == want,
                     'An owned source changed during table generation.')
        _require(bounded_read(safe_path(ctx.args.import_ledger), MAX_TABLE) == raw,
                 'The private ledger changed during table generation.')
        files = build_files(ctx.out, metadata=False)
        # savefiles precedes sweep. Bind exactly the files sweep will retain;
        # held stale files still cause a safe import refusal until cleaned up.
        files = {p: h for p, h in files.items() if p in ctx.registry or
                 (p in ctx.base_index and not (getattr(ctx.args, 'no_movies', False) and p.lower().endswith('.sfd')))}
        return dict(schema=2, source=profile, target_files=files,
                    release_ready=False, acceptance=[], provenance=dict(ledger_sha256=digest(raw),
                    source_files=receipts, evidence=ledger['evidence']), **mappings)
    except ImportRefusal:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, OSError) as exc:
        raise ImportRefusal('BUILD', 'The private import ledger is incomplete or invalid.',
                            reason_type=type(exc).__name__) from exc


def run(ctx):
    if not getattr(ctx.args, 'import_ledger', None):
        return
    if not getattr(ctx.args, 'experimental_save_import', False):
        raise ImportRefusal('UNVALIDATED', 'Building an import table requires --experimental-save-import.')
    table = from_owned_inputs(ctx)
    data = (json.dumps(table, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode('ascii')
    ctx.write_bytes(TABLE_REL, data, source='lcsave: source-receipted experimental XML1 import table')
    ctx.note('Experimental import table written; real-save and native acceptance remain unproven.')
