"""Synthetic contracts for the 060u live follow-up; no owned inputs needed."""
from xml1build import online_menus as O


def test_hub_select_description_allows_native_hover_color():
    screen = O.runtime_layout('lc_online')
    tree = O.menu_tree(screen, {i:str(80+i) for i in range(8)})
    # Native prompt hover retains row focus. Both localized source variants must
    # therefore carry explicit palette colors, independent of text style focus.
    for suffix, color in [('normal',84), ('hover',80)]:
        node = tree.find(f"item[@name='lc_hub_select_{suffix}']")
        assert node is not None
        assert node.get('text') == f'~{color}$MENU_ACCEPT Select'
        assert node.get('hide') == 'true' and node.get('neverfocus') == 'true'
        assert node.get('usecmd') is None


def test_back_footer_palette_sources_cover_expanded_keyboard_and_pad_labels():
    for name, label in [('lc_code', '$MENU_BACK Back'), ('lc_browse', '$MENU_BACK Back')]:
        tree = O.menu_tree(O.runtime_layout(name), {i:str(80+i) for i in range(8)})
        for suffix, color in [('normal', 84), ('hover', 80)]:
            node = tree.find(f"item[@name='lc_footer_back_{suffix}']")
            assert node is not None
            assert node.get('text') == f'~{color}{label}'
            assert node.get('hide') == 'true' and node.get('neverfocus') == 'true'
            assert node.get('usecmd') is None
