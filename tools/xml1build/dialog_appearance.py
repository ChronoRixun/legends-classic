"""One classic frame/style family for native PC messages, lists and confirmations."""
from __future__ import annotations

from . import menu_conversion as M, menu_theme as T, igb_file as G

FRAME = 'UI/hud/dialog.IGB'
SELECT = 'UI/hud/dialog_select.IGB'
RECT = (75,56,438,322)


def problems(colors, styles, data):
    errors = []
    ids = {e.get('id') for e in colors}
    named = {e.get('name'):e for e in styles}
    for name in ('STYLE_NORMAL','STYLE_MENU'):
        style = named.get(name)
        if style is None or style.get('font') not in ('medium','big') or any(
                style.get(key) not in ids for key in T.COLOR_FIELDS):
            errors.append('shared dialog style binding missing: '+name)
    g = G.IgbFile(data)
    vertices = []
    for array in g.objects_of('igVertexArray1_1'):
        refs = g.ref_list(array.get(2))
        row = g.block_floats(refs[0]) if refs else []
        vertices.extend(zip(row[0::3],row[1::3],row[2::3]))
    if not vertices or g.objects_of('igTransform'):
        errors.append('shared dialog frame is not a flat native rectangle')
    else:
        bounds = (min(v[0] for v in vertices),min(v[2] for v in vertices),
                  max(v[0] for v in vertices),max(v[2] for v in vertices))
        if any(abs(a-b)>1e-4 for a,b in zip(bounds,RECT)):
            errors.append('shared dialog frame bounds drift')
    return errors


def write(ctx):
    source = ctx.x1_path('ui/hud/dialog.igb')
    selected = ctx.base_index.path(SELECT)
    if source is None or selected is None:
        raise ValueError('shared dialog frame/selection input is missing')
    original_colors = ctx.read_x1_xml('data/colors.xml')
    colors,styles,_ = T.allocate(ctx.read_out_xmlb('Data/colors.XMLB'),
        ctx.read_out_xmlb('Data/styles.XMLB'),original_colors,(
            T.text_style('STYLE_NORMAL'),T.text_style('STYLE_MENU',normal=1,focus=4,allow=True)))
    frame,report = M.fit_flat_panel(source.read_bytes(),RECT)
    errors = problems(colors,styles,frame)
    if errors:
        raise ValueError('; '.join(errors))
    tint = T.rgba(list(original_colors)[7].get('value'))[:3]
    ctx.write_xmlb('Data/colors',colors,source='frontend:shared dialog palette reuse')
    ctx.write_xmlb('Data/styles',styles,source='frontend:shared native dialog styles')
    ctx.write_bytes(FRAME,frame,source='frontend:classic frame fitted to native dialog bounds')
    ctx.write_bytes(SELECT,M.tint_vertex_colors(selected.read_bytes(),tint),
                    source='frontend:native dialog selection with original palette')
    return report
