"""Versioned, local import tables bound to the installed save data and scripts.

No guessed talent ledger, mission ordinal or checkpoint recipe ships in R1.
The table constructor is read-only; integration can write its result later.
"""
from __future__ import annotations

import configparser
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re

from lcsave import catalogue, convert, keys, lcfiles, typed_registry

from .errors import ImportRefusal
from .source import bounded_read, digest, safe_path, TITLE_ID

TABLE_REL = 'Data/lcsave/xml1-import.json'
MAX_TABLE = 4 << 20


def read_json(data):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError('Duplicate JSON key: ' + key)
            out[key] = value
        return out
    return json.loads(data, object_pairs_hook=unique, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def relative_file(build, name):
    p = PurePosixPath(name)
    if not name or '\\' in name or ':' in name or p.is_absolute() or any(x in ('.', '..') for x in p.parts):
        raise ImportRefusal('BUILD', 'Invalid import-table relative filename.')
    result = safe_path(build.joinpath(*p.parts))
    if not result.is_relative_to(build):
        raise ImportRefusal('BUILD', 'Import table escaped the selected build.')
    return result


def build_files(build):
    """Hash all Data and Scripts inputs read by Binds and checkpoint mappings.

    Assets outside these trees are not read by the converter. Native/package
    acceptance remains a separate release gate, not implied by this digest.
    """
    build = safe_path(build, directory=True)
    paths = []
    for tree in ('Data', 'Scripts'):
        folder = safe_path(build / tree, directory=True)
        for path in folder.rglob('*'):
            safe_path(path)
            if path.is_file() and path != build / TABLE_REL:
                paths.append(path)
            if len(paths) > 16384:
                raise ImportRefusal('BUILD', 'Too many build data files.')
    paths += [build / 'xml2-fix.ini', build / '_build/report.json']
    result, folded = {}, set()
    for p in sorted(paths):
        rel = p.relative_to(build).as_posix()
        if rel.lower() in folded:
            raise ImportRefusal('BUILD', 'Case-insensitive build filenames are ambiguous.')
        folded.add(rel.lower())
        result[rel] = digest(bounded_read(p, 64 << 20))
    return result


def bind_table(build, source_profile, **mappings):
    """Return a version-1 table, with no admission claim or implicit recipes.

    Source ledgers and final narrowed variable metadata must be supplied by the
    integration stage after sample verification, not derived from file order.
    """
    return dict(schema=1, source=source_profile, target_files=build_files(build),
                release_ready=False, acceptance=[], **mappings)


def installed_catalogue(raw):
    parsed = lcfiles.read_catalogue_lcc(raw)
    data = dict(revision=parsed['revision'], content_version=parsed['content_version'], domains={})
    seen_ids = set()
    for tag, entries in parsed['domains'].items():
        rows, hashes = [], set()
        for e in entries:
            value = e['id']
            if keys.id_domain(value) != keys.DOMAIN_NUMBER[tag] or not keys.id_serial(value) or value in seen_ids:
                raise ImportRefusal('BUILD', 'Invalid catalogue identity.')
            seen_ids.add(value)
            # Empty retired keys are not resolvable names; keep their serials inert.
            key_hash = hashlib.sha256(e['key'] or b'\xff' + value.to_bytes(4, 'little')).hexdigest()
            aliases = [hashlib.sha256(a).hexdigest() for a in e['aliases']]
            if len({key_hash, *aliases}) != len(aliases) + 1 or hashes.intersection([key_hash, *aliases]):
                raise ImportRefusal('BUILD', 'Ambiguous catalogue keys.')
            hashes.update([key_hash, *aliases])
            rows.append(dict(serial=keys.id_serial(value), hash=key_hash, aliases=aliases,
                             attributes=e['attributes'], retired=bool(e['flags'] & 1), successor=e['successor']))
        data['domains'][tag] = dict(next=max((r['serial'] for r in rows), default=0) + 1, entries=rows)
    return catalogue.Catalogue(data)


class ImportTable:
    def __init__(self, build, path=None):
        self.build = safe_path(build, directory=True)
        self.path = safe_path(path or self.build / TABLE_REL)
        if not self.path.is_file():
            raise ImportRefusal('BUILD', 'The installation has no verified XML1 import table.')
        try:
            raw = bounded_read(self.path, MAX_TABLE)
            self.data = read_json(raw)
            self.sha256 = digest(raw)
            self._load()
        except ImportRefusal:
            raise
        except (ValueError, KeyError, TypeError, IndexError, AttributeError, configparser.Error, OSError) as e:
            raise ImportRefusal('BUILD', 'Invalid import table: ' + str(e)) from e

    def _load(self):
        d = self.data
        if d['schema'] != 1 or d['source']['title_id'].lower() != TITLE_ID:
            raise ImportRefusal('VERSION', 'Unrecognized source profile or import table schema.')
        self.source = d['source']
        names = self.source['hero_names']
        if len(names) != 16 or len(set(n.lower() for n in names)) != 16:
            raise ImportRefusal('VERSION', 'The retail source roster must have sixteen unique definitions.')
        if not self.source.get('id') or not re.fullmatch('[0-9a-f]{64}', self.source.get('xbe_sha256', '')):
            raise ImportRefusal('VERSION', 'The source profile must identify its original executable.')
        expected = d['target_files']
        if not isinstance(expected, dict) or not expected:
            raise ImportRefusal('BUILD', 'The import table has no target hashes.')
        for name in expected:
            relative_file(self.build, name)
        self.files = build_files(self.build)
        if expected != self.files:
            raise ImportRefusal('BUILD', 'The import table does not match this installation.')
        report = read_json(bounded_read(self.build / '_build/report.json', 16 << 20))['build']
        if any(str(report.get(k, '')).lower() != v for k, v in (('save_layout', 'w2'), ('loot', 'xml1'), ('xp_curve', 'xml1'))):
            raise ImportRefusal('BUILD', 'The recorded build settings do not support XML1 imports.')
        ini = configparser.ConfigParser(interpolation=None, strict=True)
        ini.read_string(bounded_read(self.build / 'xml2-fix.ini', 1 << 20).decode('utf-8-sig'))
        for section, option, want in (('Limits', 'SaveLayout', 'w2'), ('Limits', 'EntityCapacity', '1'),
                                      ('Save', 'Format', 'lc'), ('Game', 'Xml1Economy', '1'), ('Game', 'XPCurve', 'xml1'),
                                      ('Game', 'LevelSkillPoints', 'xml1'), ('Game', 'LevelStatPoints', 'xml1')):
            if ini.get(section, option, fallback='').strip().lower() != want:
                raise ImportRefusal('BUILD', 'The active game settings do not support XML1 imports.', setting=section + '/' + option)
        if ini.get('Limits', 'ItemEnhancements', fallback='4096').strip() != '4096':
            raise ImportRefusal('BUILD', 'W2 needs 4096 item enhancements.')
        from .. import loot
        economy, _, _ = loot.parse_sidecar(bounded_read(self.build / 'Data/x1economy.txt', 1 << 20))
        self.economy = {r['name'].lower(): r for r in economy}
        cat = installed_catalogue(bounded_read(self.build / 'Data/lcsave/catalogue.lcc', 16 << 20))
        self.env = convert.Environment(str(self.build), catalogue=cat)
        # Recompute the bindings through the existing writer to detect omitted
        # bind files and unsupported rules as well as stale individual hashes.
        expected_binds, problems = lcfiles.bind_files(str(self.build), cat)
        if problems:
            raise ImportRefusal('BUILD', 'The build cannot produce coherent save bindings.')
        for name, want in expected_binds.items():
            p = self.build / name
            if not p.is_file() or bounded_read(p, 16 << 20) != want:
                raise ImportRefusal('BUILD', 'A required save binding is missing or stale.', file=name)
        # All installed bind keys must agree with the installed catalogue and data.
        for name in self.files:
            if not name.lower().endswith('.lcbind'):
                continue
            p = self.build / name
            bind = lcfiles.read_lcbind(bounded_read(p, 16 << 20))
            base = str(p)[:-7]
            candidates = [Path(base + ext) for ext in ('.engb', '.xmlb', '.XMLB')]
            if not any(c.is_file() and hashlib.sha1(bounded_read(c, 64 << 20)).digest() == bind['sha1'] for c in candidates):
                raise ImportRefusal('BUILD', 'A save binding has stale data.', file=name)
            for tag, _, rows in bind['lists']:
                for _, _, ident, key in rows:
                    if ident and (not key or cat.lookup(tag, hashlib.sha256(key).hexdigest()) != ident):
                        raise ImportRefusal('BUILD', 'A save binding disagrees with the catalogue.', file=name)
        # Every identity used by the live build must resolve, including extras.
        from lcsave.catalogue import tables_from_hashes
        for tag, hashes in tables_from_hashes(self.env.binds.hash_tables(include_conversation_digest=False)).items():
            if any(h and not cat.lookup(tag, h) for h in hashes):
                raise ImportRefusal('BUILD', 'The catalogue cannot name the installed ' + tag + ' data.')
        self.registry = typed_registry.load_registry(bounded_read(self.build / 'Data/lcsave/typed-entity-ids.txt', 4 << 20))
        ok, reason = typed_registry.verify_registry(self.registry, str(self.build / 'Scripts'))
        if not ok:
            raise ImportRefusal('BUILD', reason)
        self._validate_mapping()
        self.fingerprint = digest(json.dumps(self.files, sort_keys=True, separators=(',', ':')).encode('utf-8'))

    def _validate_mapping(self):
        """Reject malformed local tables as input errors, before indexing records."""
        d = self.data
        def require(value, reason):
            if not value:
                raise ImportRefusal('BUILD', reason)
        def integer(value, lo, hi):
            return type(value) is int and lo <= value <= hi
        def ident(value):
            return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_]+', value) is not None
        def zone(value):
            return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_/-]+', value) is not None and '..' not in value.split('/')
        def pose(value):
            return isinstance(value, list) and len(value) == 6 and all(type(v) in (float, int) and math.isfinite(v) for v in value)
        names = self.source['hero_names']
        require(all(ident(n) for n in names), 'Invalid source hero names.')
        thresholds = d['xp_thresholds']
        require(isinstance(thresholds, list) and 1 <= len(thresholds) <= 255 and thresholds[0] == 0 and
                all(integer(v, 0, 0xffffffff) for v in thresholds) and
                all(a < b for a, b in zip(thresholds, thresholds[1:])), 'XP thresholds must start at zero and strictly increase.')
        require(isinstance(d['heroes'], dict) and set(d['heroes']) == set(names), 'The source hero table is incomplete.')
        targets = []
        for row in d['heroes'].values():
            require(ident(row['target']), 'Invalid target hero name.')
            targets.append(row['target'].lower())
            powers = row['powers']
            require(isinstance(powers, list) and len(powers) <= 4 and len({p['button'] for p in powers}) == len(powers),
                    'Invalid target default power slots.')
            for power in powers:
                require(integer(power['button'], 0, 3) and integer(power['flags'], 0, 255) and
                        power['name'] in ('', 'power1', 'power2', 'power3', 'power9'), 'Invalid target default power slot.')
            for key, val in row.get('skins', {}).items():
                require(key.isdigit() and 0 <= int(key) <= 255 and ident(val), 'Invalid source skin-byte mapping.')
            growth = row.get('stat_reconstruction')
            if growth:
                require(growth.get('confirmed') is True, 'Stat reconstruction requires sample-confirmed metadata.')
                for field in ('source_base', 'target_base'):
                    require(len(growth[field]) == 4 and all(integer(v, 0, 65535) for v in growth[field]), 'Invalid authored trait metadata.')
                for field in ('source_growth', 'target_growth'):
                    require(len(growth[field]) == len(thresholds) and all(len(a) == 4 and all(integer(v, 0, 65535) for v in a)
                            for a in growth[field]), 'Invalid cumulative class-growth metadata.')
        require(len(targets) == len(set(targets)), 'Source heroes must map to distinct target heroes.')
        for hero, ledger in d.get('talents', {}).items():
            require(hero in names and isinstance(ledger, dict), 'Invalid native talent ledger owner.')
            for tid, fields in ledger.items():
                require(re.fullmatch(r'0|[1-9][0-9]{0,2}', tid) is not None and int(tid) <= 255 and
                        isinstance(fields, list) and len(fields) == 2 and all(ident(v) for v in fields), 'Invalid native talent ledger.')
        indices = set()
        health_routes = set()
        for row in d['items']:
            index = row['source_index']
            require(integer(index, 0, 159) and index not in indices and integer(row['maximum'], 0, 255), 'Invalid source item ledger.')
            indices.add(index)
            require(ident(row['target']) and row['route'] in ('equipment', 'health', 'energy', 'key', 'effect'), 'Invalid item routing policy.')
            if row['route'] in ('health', 'energy'):
                require(row['route'] not in health_routes and integer(row['target_maximum'], 0, 255), 'Duplicate or invalid pack counter route.')
                health_routes.add(row['route'])
            if row['route'] == 'equipment':
                economy = self.economy.get(row['target'].lower())
                require(economy is not None and economy['flags'] & 0x40 and economy['source'] == index,
                        'Source equipment mapping disagrees with the installed XML1 economy.')
        for row in d.get('variables', []):
            require(row['family'] in ('mission', 'game') and ident(row['name']) and isinstance(row['scope'], str) and
                    row['scope'] and row['kind'] in ('pack', 'flag', 'transient'), 'Invalid scoped source variable mapping.')
            if row['kind'] == 'transient':
                continue
            require(ident(row['target']) and len(row['target']) < 12 and
                    integer(row['width'], 1, 32) and integer(row.get('first_bit', 1), 1, 33 - row['width']),
                    'Invalid final variable storage width or name.')
            require(('game', row['target']) not in self.registry['keys'],
                    'A persistent source integer cannot be copied into a target entity-handle variable.')
        for recipe in d.get('checkpoints', []):
            require(integer(recipe['mission_id'], 0, 254) and zone(recipe['source_zone']) and zone(recipe['target_zone']) and
                    integer(recipe['act'], 1, 9) and recipe['name'] and recipe['scope'], 'Invalid checkpoint identity.')
            require(len(recipe['seat_poses']) == 4 and all(pose(p) for p in recipe['seat_poses']) and pose(recipe['anchor_pose']),
                    'Invalid checkpoint spawn poses.')
            require(all(n in names for n in recipe['allowed_party']), 'Unknown checkpoint party definition.')
            for index, fields in recipe['objectives'].items():
                require(index.isdigit() and 0 <= int(index) < 16 and len(fields) == 2 and all(ident(v) for v in fields),
                        'Invalid checkpoint objective identity.')
        for row in d.get('profile_unlock_bits', []):
            require(row.get('confirmed') is True and row['field'] in ('characters', 'review', 'flags') and
                    integer(row['offset'], 0, 0x193) and integer(row['mask'], 1, 255), 'Invalid source profile unlock bit.')
            if row['field'] == 'flags':
                require(integer(row['target_mask'], 1, 255), 'Invalid target profile completion flag.')
            else:
                fields = row['target']
                require(isinstance(fields, list) and len(fields) == (1 if row['field'] == 'characters' else 2) and
                        all(ident(x) for x in fields), 'Invalid named profile unlock identity.')

    def recheck(self):
        if digest(bounded_read(self.path, MAX_TABLE)) != self.sha256 or build_files(self.build) != self.files:
            raise ImportRefusal('CHANGED', 'The installation or import table changed.')

    def resolve(self, domain, *fields):
        value = self.env.id_of(domain, keys.key_hash(*fields))
        if not value:
            raise ImportRefusal('IDENTITY', 'No unique destination identity.', domain=domain, key=list(fields))
        return value
