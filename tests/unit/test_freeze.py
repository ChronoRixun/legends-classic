"""Packaging (BUILDER_DESIGN.md 3.2, 5.2, 6.1): the research tables the frozen builder carries, their packaging without
game text, the mission-text fallback that packaging relies on, and the release manifest the launcher parses."""
import json
import re
import tempfile
import zipfile
from pathlib import Path

import synth  # noqa: F401  (puts tools/ on sys.path)
import freeze_builder as FB
from xml1build import scripts as S
from xml1builder import CONTENT_VERSION, VERSION
from xml1builder import resources as R

REPO = Path(__file__).resolve().parents[2]


def _keys(obj, acc):
    if isinstance(obj, dict):
        for k, v in obj.items():
            acc.add(k)
            _keys(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _keys(v, acc)
    return acc


def test_research_data_exists_and_packages_without_text():
    assert R.PACKAGED_MARK == S.PACKAGED_MARK
    for rel in R.RESEARCH_DATA:
        assert (REPO / 'research' / rel).is_file(), rel
    assert set(R.PACKAGED_STRIP) | set(R.PACKAGED_KEEP) <= set(R.RESEARCH_DATA)
    with tempfile.TemporaryDirectory() as td:
        sizes = FB.package_research(Path(td))
        assert set(sizes) == set(R.RESEARCH_DATA)
        for rel, fields in R.PACKAGED_STRIP.items():
            src = json.loads((REPO / 'research' / rel).read_text(encoding='utf-8'))
            out = json.loads((Path(td) / rel).read_text(encoding='utf-8'))
            assert R.PACKAGED_MARK in out and not (_keys(out, set()) & set(fields)), rel
            assert [k for k in out if k != R.PACKAGED_MARK] == [k for k in src if k != R.PACKAGED_MARK], rel
            # every other key, same order (the public repo ships the source packaged already: idempotent)
            assert set(out['missions']) == set(src['missions'])
        for rel, fields in R.PACKAGED_KEEP.items():
            src = json.loads((REPO / 'research' / rel).read_text(encoding='utf-8'))
            out = json.loads((Path(td) / rel).read_text(encoding='utf-8'))
            assert list(out) == list(src), rel                                    # same zones, same order
            for z, info in out.items():
                assert set(info) <= set(fields)
                for f in fields:
                    assert info.get(f) == src[z].get(f), (rel, z, f)
        for rel in set(R.RESEARCH_DATA) - set(R.PACKAGED_STRIP) - set(R.PACKAGED_KEEP):
            assert (Path(td) / rel).read_bytes() == (REPO / 'research' / rel).read_bytes(), rel


class _Ctx:
    def __init__(self, graph, plan):
        self.graph, self._plan = graph, plan

    def research_json(self, rel):
        assert rel == 'scripts/mission_plan.json'
        return self._plan


def test_mission_texts_from_the_plan_when_packaged():
    plan = {'missions': {'sewers': {'attrs': {'descname': 'Sewer run', 'description': 'Find the hero'}}}}
    full = {'missions': {'sewers': {'descname': 'Graph name', 'description': 'Graph text'}, 'other': {}}}
    ctx = _Ctx(full, plan)
    assert S._mission_texts(ctx, full['missions'], 'sewers') == ('Graph text', 'Graph name')
    assert S._mission_texts(ctx, full['missions'], 'other') == ('', '')         # unpackaged: as before
    packaged = {S.PACKAGED_MARK: 'x', 'missions': {'sewers': {}, 'gone': {}}}
    ctx = _Ctx(packaged, plan)
    assert S._mission_texts(ctx, packaged['missions'], 'sewers') == ('Find the hero', 'Sewer run')
    assert S._mission_texts(ctx, packaged['missions'], 'gone') == ('', '')
    assert S._mission_texts(ctx, packaged['missions'], 'absent') == ('', '')


def test_release_manifest_matches_the_launcher_parser():
    """ultimate-legends tool_install::parse_manifest: version (safe folder name), content_version (int), zip (a plain
    file name), size (uint64 > 0), sha256 (64 lower-case hex), min_launcher / requires_xml2fix (strings)."""
    with tempfile.TemporaryDirectory() as td:
        dist = Path(td)
        archive = dist / FB.zip_name()
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('xml1-builder.exe', b'MZ stand-in')
            z.writestr('_internal/xml1builder/data/build-info.json', b'{}')
        m = FB.write_manifest(dist, archive, '0.0.0')
        on_disk = json.loads((dist / 'xml1-builder.json').read_text(encoding='utf-8'))
        assert on_disk == m
        assert m['version'] == VERSION and re.fullmatch(r'[A-Za-z0-9.+_-]{1,64}', m['version'])
        assert '..' not in m['version'] and not m['version'].startswith('.')
        assert isinstance(m['content_version'], int) and m['content_version'] == CONTENT_VERSION
        assert m['zip'] == archive.name and not re.search(r'[/\\:*?"<>|]', m['zip'])
        assert m['zip'] == f'xml1-builder-{VERSION}-win64.zip'
        assert isinstance(m['size'], int) and m['size'] == archive.stat().st_size > 0
        assert re.fullmatch(r'[0-9a-f]{64}', m['sha256']) and m['sha256'] == FB.sha256_file(archive)
        assert isinstance(m['min_launcher'], str) and m['requires_xml2fix'].startswith('>=')
        with zipfile.ZipFile(archive) as z:                       # the exe at the top (tool_install::content_root)
            assert 'xml1-builder.exe' in z.namelist()


def test_frozen_data_root_must_be_the_bundle():
    from xml1build.sources import REPO_ROOT
    from xml1builder.errors import BuilderError
    saved = R.frozen, R.bundle_root
    try:
        R.frozen = lambda: True
        R.bundle_root = lambda: Path(REPO_ROOT)                      # the data root is the bundle: fine
        R.check_root()
        R.bundle_root = lambda: Path(REPO_ROOT) / 'dist' / 'xml1-builder' / '_internal'
        try:
            R.check_root()
            raise AssertionError('a data root outside the bundle was accepted')
        except BuilderError as e:
            assert e.code == 'E_INTERNAL' and e.exit_code == 70
    finally:
        R.frozen, R.bundle_root = saved
