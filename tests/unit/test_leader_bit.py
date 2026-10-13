"""Issue #15: the xml2-fix leader sidecar (xml1build.characters helpers) - invented names, no game data.

The sidecar lists the stats entries whose leader="true" convert_stats drops; xml2-fix
([Game] X1Leader) restores the two engine behaviours (leader deaths always roll drops with the
forced HEALTH_ITEM/ENERGY_ITEM/XTREME_PIP slots; heroes do not flinch vs a leader-owned
projectile) for those actors, since XMen2.exe has no stats field to carry the bit.
"""
from xml1build.characters import LEADER_SIDECAR_REL, leader_sidecar_text, parse_leader_sidecar

ROSTER = {'x1_sgt_red', 'x1_cpl_blue', 'x1_pvt_green'}   # invented officer squad


def test_sidecar_lists_names_sorted_one_per_line():
    text = leader_sidecar_text(ROSTER)
    body = [l for l in text.splitlines() if not l.startswith('#')]
    assert body == sorted(ROSTER)              # deterministic order for the build hash
    assert all(l and l == l.strip() for l in body)
    assert text.endswith('\r\n') and leader_sidecar_text(ROSTER) == text


def test_sidecar_roundtrip_casefolds_and_skips_noise():
    text = leader_sidecar_text(ROSTER | {'X1_SGT_RED'})   # duplicate differing only by case
    parsed = parse_leader_sidecar(text)
    assert parsed == {n.lower() for n in ROSTER}          # 'x1_sgt_red' collapsed
    noisy = '# comment\r\n\r\n  x1_sgt_red  \r\n;x-style\r\n\tx1_cpl_blue\n'
    assert parse_leader_sidecar(noisy) == {'x1_sgt_red', 'x1_cpl_blue'}


def test_sidecar_path_and_latin1_contract():
    assert LEADER_SIDECAR_REL.lower() == 'data/x1leader.txt'
    leader_sidecar_text(ROSTER).encode('latin-1')         # the writer's encoding must not raise
