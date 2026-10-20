"""Target resistance subtitles use existing localized strings and color slots.

No game text or art is carried here. V63 compares the native HUD's resources
with the player's original data, including the PC's swapped mental/energy IDs.
"""
from . import fix_ini as FI

STRING_IDS = {103: 103, 201: 130, 202: 131, 210: 155, 211: 156, 212: 140}
COLOR_IDS = {22: 22, 23: 24, 24: 23}


def resource_problems(original_strings, original_colors, strings, colors):
    def entries(root, tag):
        return [el for el in root.iter() if isinstance(el.tag, str) and el.tag.lower() == tag] if root is not None else []

    source_text = {el.get('id'): el.get('text') for el in entries(original_strings, 'string')}
    output_text = {el.get('id'): el.get('text') for el in entries(strings, 'string')}
    source_colors = entries(original_colors, 'color')
    output_colors = {el.get('id'): el for el in entries(colors, 'color')}
    errors = []
    for pc, original in STRING_IDS.items():
        expected = source_text.get(str(original))
        if expected is None or output_text.get(str(pc)) != expected:
            errors.append(f'localized resistance string {pc} differs from original slot {original}')
    for pc, original in COLOR_IDS.items():
        source = source_colors[original] if original < len(source_colors) else None
        output = output_colors.get(str(pc))
        try:
            expected = tuple(map(float, source.get('value', '').split())) if source is not None else ()
            actual = tuple(map(float, output.get('value', '').split())) if output is not None else ()
        except ValueError:
            expected, actual = (), ()
        if len(expected) != 4 or actual != expected:
            errors.append(f'resistance color {pc} differs from original slot {original}')
    return errors


def validate(v, ck):
    if FI.game_keys(xml1_opening=True).get('ResistanceDisplay') != 'xml1':
        ck.error('converted scoped resistance needs [Game] ResistanceDisplay=xml1')
    try:
        strings = v.ctx.read_x1_xml('data/strings.eng')
        colors = v.ctx.read_x1_xml('data/colors.xml')
    except KeyError:
        ck.error('original resistance HUD resources are unavailable')
        return
    for problem in resource_problems(strings, colors, v.tree('Data/strings.engb'), v.tree('Data/colors.XMLB')):
        ck.error(problem)
    ck.set('resistance_strings', len(STRING_IDS))
    ck.set('resistance_colors', len(COLOR_IDS))
