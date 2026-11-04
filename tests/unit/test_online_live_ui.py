"""Contracts for the b2c live UI findings, with synthetic menu definitions."""
from xml1build import online_menus as O, online_native_skins as N
from test_online_native_skins import native


def test_waiting_sentence_has_one_contiguous_field_and_localized_template():
    for role in ('host','join'):
        screen=O.lobby_layout(role,members=4,fixture=True)
        items={e['name']:e for e in screen['items']}
        assert items['lc_ready_waiting']['text']=='Waiting for %s to get ready.'
        assert items['lc_ready_waiting']['hidden']
        assert items['lc_waiting_name']['rect']==(125,365,400,17)
        assert items['lc_waiting_name']['text'].startswith('Waiting for ')
        assert items['lc_waiting_name']['text'].endswith(' to get ready.')
        assert not items['lc_ready_waiting'].get('parts')


def test_code_back_and_delete_have_separate_keys_and_commands():
    tree=O.menu_tree(O.runtime_layout('lc_code'))
    back=tree.find("item[@name='desctext2']")
    delete=tree.find("item[@name='desctext5']")
    assert back.get('text').endswith('$MENU_BACK Back')
    assert back.get('usecmd')=='runscript lcOnlineIntent(6)'
    assert delete.get('text').endswith('Del Delete')
    assert delete.get('usecmd')=='runscript lcOnlineIntent(11)'
    state=O.Fixture();state.menu='lc_code';state.code='ABCD'
    state.dispatch('delete');assert state.menu=='lc_code' and state.code=='ABC'
    state.dispatch('back');assert state.menu=='lc_online' and state.code=='ABC'
