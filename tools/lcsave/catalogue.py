"""The master catalogue (SPEC-new-save 3.3): one permanent 32-bit id per save-bound thing, keyed by the SHA-256
of its canonical key. data/catalogue.json holds hashes only (decision D3); plain keys exist only on the player's
machine, read from the build's data (binds.Binds).

  {"revision": r, "content_version": cv, "domains": {TAG: {"next": n, "entries": [{"serial": s, "hash": h,
   "aliases": [...], "retired": false, "successor": 0, "attributes": a}, ...]}}}

Invariants (tests/unit/test_lcsave_catalogue.py): a serial never disappears or changes its hash, `next` never
goes down, a hash belongs to one serial per domain. `update(tables)` appends what is new and refuses when keys
disappeared and appeared in one domain without a migration record (decision D8) - the migration records
themselves are the later P2 piece; this module carries the data model and the lookups the converter needs.
"""
from __future__ import annotations

import json
import os

from .keys import DOMAIN_NUMBER, DOMAINS, make_id, id_domain, id_serial

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
CATALOGUE_FILE = os.path.join(DATA_DIR, 'catalogue.json')


class CatalogueError(ValueError):
    pass


class Catalogue:
    def __init__(self, data=None):
        self.data = data or {'revision': 0, 'content_version': 0, 'domains': {}}
        self._by_hash = {}
        self._by_id = {}
        for tag, dom in self.data['domains'].items():
            for e in dom['entries']:
                self._index(tag, e)

    def _index(self, tag, e):
        self._by_hash.setdefault(tag, {})[e['hash']] = e
        for a in e.get('aliases', []):
            self._by_hash[tag][a] = e
        self._by_id[make_id(DOMAIN_NUMBER[tag], e['serial'])] = (tag, e)

    @classmethod
    def load(cls, path=CATALOGUE_FILE):
        with open(path, 'r', encoding='utf-8') as f:
            return cls(json.load(f))

    def save(self, path=CATALOGUE_FILE):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(self.data, f, indent=1, sort_keys=True)
            f.write('\n')

    @property
    def revision(self):
        return self.data['revision']

    def lookup(self, tag, key_hash_hex):
        """-> catalogue id of the key hash in the domain (through an alias too), or None"""
        e = self._by_hash.get(tag, {}).get(key_hash_hex)
        if e is None:
            return None
        if e.get('retired') and e.get('successor'):
            return e['successor']
        return make_id(DOMAIN_NUMBER[tag], e['serial'])

    def entry_of(self, value):
        """-> (domain tag, entry) of a catalogue id, or None"""
        return self._by_id.get(value)

    def domain_of(self, value):
        d = id_domain(value)
        return DOMAINS.get(d)

    def add(self, tag, key_hash_hex, attributes=0):
        dom = self.data['domains'].setdefault(tag, {'next': 1, 'entries': []})
        if key_hash_hex in self._by_hash.get(tag, {}):
            return self.lookup(tag, key_hash_hex)
        e = {'serial': dom['next'], 'hash': key_hash_hex, 'aliases': [], 'retired': False, 'successor': 0,
             'attributes': attributes}
        dom['next'] += 1
        dom['entries'].append(e)
        self._index(tag, e)
        return make_id(DOMAIN_NUMBER[tag], e['serial'])

    def update(self, tables, content_version):
        """append every hash of `tables` ({domain tag: [hash, ...]}) that is new. Refuses (CatalogueError) when a
        domain both lost and gained keys: a rename cannot be told from a removal plus an addition (D8)."""
        for tag, hashes in tables.items():
            present = {h for h in hashes if h}
            known = {e['hash'] for e in self.data['domains'].get(tag, {'entries': []})['entries'] if not e.get('retired')}
            gone, new = known - present, present - known
            if gone and new:
                raise CatalogueError(f'{tag}: {len(gone)} keys disappeared and {len(new)} appeared; record a migration '
                                     f'(rename / retire) before updating')
            for h in hashes:
                if h and h not in self._by_hash.get(tag, {}):
                    self.add(tag, h)
        self.data['revision'] = self.data.get('revision', 0) + 1
        self.data['content_version'] = content_version

    def check_invariants(self, previous):
        """-> [problem] against an earlier Catalogue (serials kept, hashes kept, next never down)"""
        problems = []
        for tag, dom in previous.data['domains'].items():
            cur = self.data['domains'].get(tag)
            if cur is None:
                problems.append(f'{tag}: domain disappeared'); continue
            if cur['next'] < dom['next']:
                problems.append(f'{tag}: next serial went down')
            by_serial = {e['serial']: e for e in cur['entries']}
            for e in dom['entries']:
                c = by_serial.get(e['serial'])
                if c is None:
                    problems.append(f'{tag}: serial {e["serial"]} disappeared')
                elif c['hash'] != e['hash'] and e['hash'] not in c.get('aliases', []):
                    problems.append(f'{tag}: serial {e["serial"]} lost its key hash')
        for tag, dom in self.data['domains'].items():
            seen = {}
            for e in dom['entries']:
                for h in [e['hash']] + e.get('aliases', []):
                    if h in seen and seen[h] != e['serial']:
                        problems.append(f'{tag}: hash shared by serials {seen[h]} and {e["serial"]}')
                    seen[h] = e['serial']
        return problems

    def counts(self):
        return {tag: len(d['entries']) for tag, d in self.data['domains'].items()}


def tables_from_hashes(T):
    """flatten binds.Binds.hash_tables() (or an era's tables) into {domain tag: [hash]} for update()"""
    out = {
        'STAT': [h for h in T['STAT'] if h], 'ITEM': T['ITEM'], 'ENHC': T['ENHC'], 'NAMA': T['NAMA'],
        'NAMB': [h for lst in T['NAMB'].values() for h in lst], 'TRIT': T['TRIT'],
        'TALN': T['TALN_shared'] + [h for lst in T['TALN_hero'].values() for h in lst],
        'COST': [h for d in T['COST'].values() for h in d.values()], 'MSNF': T['MSNF'], 'OBJV': T['OBJV'],
        'DRCS': T['DRCS'], 'DRGR': T['DRGR'], 'REVW': list(T['REVW'].values()), 'XPNT': T['XPNT'],
        'TRIV': list(T['TRIV'].values()), 'ZONE': T['ZONE'],
    }
    return out


def serial_of(value):
    return id_serial(value)
