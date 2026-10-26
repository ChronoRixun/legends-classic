"""Classic Trivia panels, retaining native questions, feedback and rewards."""
from __future__ import annotations

from . import menu_conversion as M, menu_theme as T, service_shell as H

SCENE = 'lc_trivia'
FRAMES = {
    'ui/models/m_trivia_question_panel': 'ui/models/lc_trivia_question',
    'ui/models/m_trivia_answers_panel': 'ui/models/lc_trivia_answers',
    'ui/models/m_team_helpbar': 'ui/models/lc_trivia_help',
    'ui/models/m_pda_option_screen': 'ui/models/lc_trivia_title',
}
RETIRED = ('track01', 'track02', 'helpbar_hinge_left', 'helpbar_hinge_right',
           'hinge1', 'hinge2', 'hinge3', 'hinge4', 'pause_bracket_01', 'option01_light', 'option01_focus')


def tree(native):
    # Correct/incorrect lights and feedback events retain their semantic colours
    # and native models. Blue selection tint must not erase answer feedback.
    return H.tree(native, SCENE, FRAMES, RETIRED, lists=('answers',))


def write(ctx):
    from . import frontend as F
    original = ctx.x1_path('ui/hud/dialog.igb')
    native = ctx.base_index.path('UI/menus/x2m_trivia.IGB')
    if original is None or native is None:
        raise ValueError('classic Trivia input missing')
    source = original.read_bytes()
    tint = T.rgba(list(ctx.read_x1_xml('data/colors.xml'))[7].get('value'))[:3]
    report = {'frames': {}}
    for before, after in FRAMES.items():
        report['frames'][after] = H.frame(ctx, source, before, after)
    selected = ctx.base_index.path('UI/models/m_trivia_select.IGB')
    if selected is None:
        raise ValueError('native Trivia selection missing')
    ctx.write_bytes('UI/models/m_trivia_select.IGB', M.tint_vertex_colors(selected.read_bytes(), tint),
                    source='frontend:native Trivia selection with classic palette')
    layout = H.retired_layout(native.read_bytes(), RETIRED)
    ctx.write_bytes('UI/menus/' + SCENE + '.IGB', M.place_anchors(native.read_bytes(), layout),
                    source='frontend:native Trivia anchors with retired sequel ornament')
    halves = []
    for ext in ('.XMLB', '.engb'):
        before = ctx.read_base_xmlb('UI/menus/trivia' + ext)
        after = tree(before)
        errors = H.control_problems(before, after, RETIRED)
        if errors:
            raise ValueError('; '.join(errors))
        halves.append(after)
    ctx.write_xmlb_pair('UI/menus/trivia', *halves, source='frontend:classic Trivia, native questions and rewards')
    package = M.package_for(halves[0], inherited=ctx.read_base_xmlb(F.MENU_PKG_DIR + '/trivia.PKGB'))
    ctx.write_xmlb(F.MENU_PKG_DIR + '/trivia', package, ('.PKGB',), source='frontend:classic Trivia resource closure')
    return report
