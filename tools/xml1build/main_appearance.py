"""Bounded main-menu palette and scene aliases; assets are read from the player's disc.

The PC model parser defaults to an invisible model (0x5c5080). Its main-menu open
method hides desctext1 (0x5c99e1), so the imported help anchor needs a separate name.
Styles use modern colour fields, not the first game's legacy colour attribute.
"""
from __future__ import annotations

import math

from . import igb_file as G
from . import menu_theme as T

MAIN_STYLE = 'STYLE_LC_MAIN'
HELP_STYLE = 'STYLE_LC_MAIN_DESC'
HELP_NODE = 'helptext1'                         # same byte length as the original alias
HELP_Z = 4.0                                  # below the eight PC rows, inside the visible footer
COLOR_LIMIT = 75
STYLE_LIMIT = 32
LAYOUTS = ('classic',)
# 0.2.0j's 'widescreen' moved the whole composition 48 units right on top of the engine's own centring
# (screen_x): ~6-7 % right of centre at every aspect. It is kept only as an accepted name that builds the
# classic composition, so old command lines, jobs and build reports still work.
RETIRED_LAYOUTS = {'widescreen': 'classic'}
VIEW_SIZE = (512.0, 384.0)                    # the 4:3 2D view the menu camera centres (frontend.MENU_SCREEN)


def _rgba(value):
    values = tuple(float(v) for v in (value or '').split())
    if len(values) != 4 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in values):
        raise ValueError('menu palette needs four finite colour channels in 0..1')
    return values


def palette_styles(base_colors, base_styles, original_colors):
    """Append only the original main's colours/styles; preserve every existing PC entry.

    Reuse identical non-pulsing colours and allocate unoccupied IDs deterministically.
    Refuse either native table ceiling before returning any output.
    """
    # Keep the established main allocation byte-for-byte; new screen families use
    # the allocator's reserved headroom rather than consuming the native ceilings.
    return T.allocate(base_colors, base_styles, original_colors, (
        T.text_style(MAIN_STYLE, font='big', normal=9, focus=10, allow=True),
        T.text_style(HELP_STYLE)), color_reserve=0, style_reserve=0)


def help_alias(data, source_name='desctext1', target_name=HELP_NODE, z=HELP_Z):
    """Rename the transform and its serialized binding aliases, keeping byte sizes intact.

    A transform rename alone does not change the engine's component lookup: the
    igHashedUserInfo and igStringValue aliases must follow it. Refuse unknown layouts.
    """
    if len(source_name.encode('ascii')) != 9 or len(target_name.encode('ascii')) != 9:
        raise G.IgbError('main help aliases must fit the existing nine-byte names')
    g = G.IgbFile(data)
    aliases = []
    allowed = {'igTransform', 'igHashedUserInfo', 'igStringValue'}
    transforms = []
    for obj in g.objects:
        for field in obj.fields.values():
            if field.type == 'igStringMetaField' and field.value == source_name:
                if not obj.decoded or obj.name not in allowed:
                    raise G.IgbError('unsupported main help alias owner')
                aliases.append(field)
                if obj.name == 'igTransform':
                    transforms.append(obj)
    if len(aliases) != 3 or len(transforms) != 1:
        raise G.IgbError('main help needs its transform and two binding aliases')
    for field in aliases:
        g.buf[field.offset + 4:field.offset + 13] = target_name.encode('ascii')
    g.set_floats(transforms[0], 8, [z], 14)
    out = g.edited()
    check = G.IgbFile(out)
    if len(out) != len(data) or any(field.value == source_name for obj in check.objects
                                   for field in obj.fields.values()):
        raise G.IgbError('main help alias verification failed')
    return out, {'aliases': len(aliases), 'node': target_name, 'z': z}


def write_styles(ctx):
    original = ctx.read_x1_xml('data/colors.xml')
    if original is None:
        raise ValueError('original palette is missing')
    colors, styles, mapping = palette_styles(ctx.read_base_xmlb('Data/colors.XMLB'),
                                             ctx.read_base_xmlb('Data/styles.XMLB'), original)
    ctx.write_xmlb('Data/colors', colors, source='frontend:bounded original main palette')
    ctx.write_xmlb('Data/styles', styles, source='frontend:original main styles in PC schema')
    return {'color_ids': mapping, 'colors': len(colors), 'styles': len(styles)}


def layout(value):
    """The main-menu layout a requested or recorded name builds: 'classic' (also for None and the retired
    'widescreen'). Refuse anything else."""
    name = RETIRED_LAYOUTS.get(value or 'classic', value or 'classic')
    if name not in LAYOUTS:
        raise ValueError('unsupported main menu layout')
    return name


def screen_x(x, camera_x, width, height):
    """Pixel column (float) of world x in the main menu on a width x height screen (pure).

    XMen2.exe draws a menu IGB orthographically through its camera. The 2D view is 384 units
    tall and aspect * 384 wide, centred on the 512-wide 4:3 view (camera 0xa0a138 vt+0x20/+0x28,
    left -(width - 512) / 2 at vt+0x2c; the mouse mapping 0x5f9eb0 uses the same numbers), and the
    aspect is the resolution's w / h without a clamp (0x5fad61). The 4:3 composition therefore
    stays centred on the camera at every aspect; nothing in the file has to move for wide screens.
    """
    return width / 2.0 + (x - camera_x) * height / VIEW_SIZE[1]


def panel_column(data):
    """(panel centre x, camera x) of a main-menu IGB: the shared X of its button*_back transforms
    (the panel models are centred on them) and its camera's X. Refuse a menu without both."""
    from . import frontend as F
    g = G.IgbFile(data)
    frame = F._scene_frame(g)
    if frame['problems']:
        raise G.IgbError('; '.join(frame['problems']))
    xs = {round(obj.get(8)[12], 4) for obj in frame['transforms'].values()
          if isinstance(obj.get(2), str) and obj.get(2).startswith('button') and obj.get(2).endswith('_back')}
    if len(xs) != 1:
        raise G.IgbError('main menu panels do not share one column')
    return xs.pop(), frame['camera_transform'].get(8)[12]
