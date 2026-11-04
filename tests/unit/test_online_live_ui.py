"""Contracts for the b2c live UI findings, with synthetic menu definitions."""
from xml1build import online_menus as O, online_native_skins as N
from test_online_native_skins import native


def test_editor_key_backgrounds_are_individually_hideable():
    screen=N.layout('text_entry',native())
    tree=N.menu_tree('text_entry',native(),screen)
    items={e['name']:e for e in screen['items']}
    for i,key in enumerate(N.KEYS,1):
        background=items[f'lc_text_key_bg{i:02}']
        assert background['rect']==items[key]['rect']
        assert background['hidden'] and not background['intent']
        node=tree.find(f"item[@name='lc_text_key_bg{i:02}']")
        assert node.get('type')=='MENU_ITEM_MODEL' and node.get('hide')=='true'
        assert node.get('model')==O.variant_resource(screen,background)
        # The static backdrop must contain no cells that survive hiding keys.
        assert not any(shape['rect']==items[key]['rect'] for shape in screen['shapes'])
    assert len(tree.findall('.//onfocus'))==42


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
