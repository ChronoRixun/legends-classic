"""Seeded-save tool (tools/loot_seed_saves.py): levels and XP, money, the held reward, the unlocks, untouched sections,
the folder guard. Runs on an invented build and an invented converted save: no game data."""
import json
import os
import tempfile

from test_lcsave import _era_model, make_build, make_old_save
from lcsave import binds, catalogue as CAT, container, convert, dump, legacy, oldsave
import loot_seed_saves as LS


def invented(d):
    ref = make_build(os.path.join(d, 'ref'))
    rb = binds.Binds(ref)
    model = _era_model(rb, rb)
    cat = CAT.Catalogue()
    for cv in ('13', '5'):
        cat.update(CAT.tables_from_hashes(legacy.Era(model, cv).tables), 13)
    ep = os.path.join(d, 'eras.json')
    with open(ep, 'w') as f:
        json.dump(model, f)
    env = convert.Environment(ref, eras_path=ep, catalogue=cat)
    res = convert.convert_slot(oldsave.write_slot(make_old_save(def_count=len(rb.item))), 'base.save', env, now=0)
    assert res.refused is None, res.refused
    return env, res.file_bytes


def seed(env, base, **kw):
    # hero_b stands in for the xpexempt guests; belt_x for the held reward; npc_a / npc_b for the Healer and the Forge
    args = dict(reward='belt_x', reward_records=2, unlock=('npc_a', 'npc_b'), exempt=('hero_b',))
    args.update(kw)
    return LS.make_seed(base, env, 'T', 20, {'hero_a': 5}, 777, 'SEED T L20', **args)


def test_xp_totals_are_the_first_games_curve_and_the_tier_follows_the_highest_level():
    assert [LS.xp_for_level(n) for n in (1, 2, 5, 10, 20, 30, 40)] == [0, 100, 830, 6880, 220650, 5510355, 125847705]
    assert LS.xp_for_level(45) > LS.xp_for_level(44) > 0
    for bad in (0, 46):
        try:
            LS.xp_for_level(bad)
            raise AssertionError('a level outside 1-45 was accepted')
        except ValueError:
            pass
    assert [LS.tier(n) for n in (1, 9, 10, 19, 20, 29, 30, 39, 40, 45)] == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
    assert [(s[1], s[2]) for s in LS.SEEDS] == [('G1', 1), ('G2', 10), ('G3', 20), ('G4', 30), ('G5', 40), ('ADJ', 30)]
    assert [LS.tier(s[2]) for s in LS.SEEDS] == [1, 2, 3, 4, 5, 4]


def test_a_seed_changes_levels_money_the_held_reward_and_the_unlocks_only():
    with tempfile.TemporaryDirectory() as d:
        env, base = invented(d)
        data, info = seed(env, base)
        before, after = container.read_file(base), container.read_file(data)
        assert after['order'] == before['order']
        changed = {t for t in after['order'] if after['sections'][t]['payload'] != before['sections'][t]['payload']}
        assert changed == {'META', 'KEYS', 'ITEM', 'HERO', 'ULCK'}, changed
        assert after['header']['campaign_serial'] != before['header']['campaign_serial']
        assert after['header']['required_features'] == before['header']['required_features']
        for tag in set(after['order']) - changed:                                   # raw payload, entry counts as they were
            assert after['sections'][tag]['entry']['records'] == before['sections'][tag]['entry']['records']
        old, new = dump.dump_any(base, env), dump.dump_any(data, env)
        h = {x['hero']: x for x in new['heroes']}
        assert (h['hero_a']['level'], h['hero_a']['experience']) == (5, 830)                # the exception
        assert (h['hero_b']['level'], h['hero_b']['experience']) == (1, 0)                  # the exempt guest is untouched
        assert new['items']['tech_bits'] == 777 and old['items']['tech_bits'] == 55
        held = [c for c in new['items']['carried'] if c['definition'] == 'belt_x' and c['location'] == 2]
        assert held
        assert len(new['items']['carried']) == len(old['items']['carried']) + 1
        assert any(len(c['own']) == 2 and c['prefixes'] == [] and c['suffixes'] == [] for c in held)
        assert new['items']['def_state']['belt_x'][1] == 1
        assert {'npc_a', 'npc_b'} <= set(new['unlocked']) and set(old['unlocked']) <= set(new['unlocked'])
        assert new['description'] == 'SEED T L20' and old['description'] != new['description']
        assert info['highest_level'] == 5 and info['tier_G'] == 1 and info['money'] == 777
        assert info['held_reward']['own_records'] == ['i/belt_x/e1', 'i/belt_x/e2']
        # everything else in the dumps is the base's
        for key in ('game', 'mission', 'zones', 'script_vars', 'danger_room', 'review'):
            assert new[key] == old[key], key
        # KEYS documents the ids the edit added
        ids = {k['id'] for k in after['sections']['KEYS']['data']['keys']}
        assert {env.catalogue.lookup('ITEM', LS.key_hash('belt_x')), env.catalogue.lookup('STAT', LS.key_hash('npc_a'))} <= ids


def test_seeds_are_deterministic_and_each_has_its_own_campaign_serial():
    with tempfile.TemporaryDirectory() as d:
        env, base = invented(d)
        a, _ = seed(env, base)
        b, _ = seed(env, base)
        assert a == b
        c, _ = LS.make_seed(base, env, 'U', 20, {}, 777, 'SEED U', reward='belt_x', reward_records=2,
                            unlock=('npc_a',), exempt=('hero_b',))
        serial = lambda blob: container.read_file(blob)['header']['campaign_serial']                # noqa: E731
        assert serial(a) != serial(c)


def test_an_unknown_reward_money_over_the_cap_or_a_second_unlock_are_handled():
    with tempfile.TemporaryDirectory() as d:
        env, base = invented(d)
        for bad in (dict(reward='no_such_item'), dict(unlock=('no_such_hero',))):
            try:
                seed(env, base, **bad)
                raise AssertionError(f'{bad} was accepted')
            except ValueError as e:
                assert 'not in the catalogue' in str(e)
        try:
            LS.make_seed(base, env, 'T', 20, {}, 1_000_000, 'x', reward='belt_x', reward_records=1, unlock=(), exempt=())
            raise AssertionError('money over the cap was accepted')
        except ValueError as e:
            assert 'money' in str(e)
        # an unlock the campaign already has is not added twice
        once, info = seed(env, base)
        again = LS.Save(once)
        assert LS.ensure_unlocked(again, env, ('npc_a',)) == []


def test_never_into_a_game_or_documents_folder():
    with tempfile.TemporaryDirectory() as d:
        game = os.path.join(d, 'game')
        os.makedirs(game)
        open(os.path.join(game, 'XMen2.exe'), 'wb').close()
        for bad in (game, os.path.join(game, 'sub', 'seeds'), os.path.join(d, 'Documents', 'Activision', 'X-Men Legends'),
                    'C:\\Games\\steamapps\\common\\Game\\out'):
            try:
                LS.refuse_out_dir(bad)
                raise AssertionError(f'{bad} was accepted')
            except ValueError as e:
                assert 'refusing' in str(e)
        LS.refuse_out_dir(os.path.join(d, 'seeded'))                                  # a dedicated folder is fine
