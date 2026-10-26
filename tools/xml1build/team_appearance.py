"""Disc character-room artwork around the native PC TEAM service.

The roster, detail modes, actor selection and gameplay callbacks stay native.
Only presentation resources and the room's coordinate system are translated.
"""
from __future__ import annotations

import math
import copy
import struct

from . import igb_file as G, menu_conversion as M, menu_scene as S
from . import menu_theme as T, service_shell as H

SCENE, BACK = 'lc_team', 'lc_team_back'
EXIT_PODIUM = 'UI/models/model_char_persp_exit.IGB'   # external reference inside the disc room file
LEVELUP_RING = 'UI/models/m_team_levelup.IGB'         # assigned by TEAM code to pad_levelup%02d items
LISTS = ('equipment', 'equipment_inv')
FRAMES = {
    'ui/models/m_team_browse_screen': 'ui/models/lc_team_browse',
    'ui/models/m_team_browse_iteminven': 'ui/models/lc_team_inventory',
    'ui/models/m_team_helpbar': 'ui/models/lc_team_help',
    'ui/models/m_team_stats_panel': 'ui/models/lc_team_stats',
    'ui/models/m_team_ai_panel': 'ui/models/lc_team_ai',
    'ui/models/m_team_options_panel': 'ui/models/lc_team_tabs',
    'ui/models/m_team_option_focus': 'ui/models/lc_team_tab_focus',
    'ui/models/m_team_skills_panel': 'ui/models/lc_team_skills',
    'ui/models/m_team_detail_screen': 'ui/models/lc_team_skill_detail',
    'ui/models/m_team_gear_panel': 'ui/models/lc_team_gear',
    'ui/models/m_team_gear_screen': 'ui/models/lc_team_gear_screen',
    'ui/models/m_team_roster_screen': 'ui/models/lc_team_roster_screen',
}
RETIRED = ('track01', 'track02', 'helpbar_hinge_left', 'helpbar_hinge_right',
           'item_inven_bracket', 'roster_bracket_top', 'roster_bracket_bottom',
           'roster_focus', 'roster_light',
           'details_hinge01', 'details_hinge02', 'details_bracket_top',
           'details_tabfocus_top', 'details_tabfocus_bottom',
           'details_tablight_top', 'details_tablight_bottom',
           *(f'char_bracket{i:02}' for i in range(1, 5)),
           *(f'char_light{i:02}' for i in range(1, 5)))


def panel_source(data):
    """Collapse the disc dialog's separate footer below its content seam.

    TEAM already has its own help strip. Keeping the dialog footer inside each
    summary/detail panel creates a second empty help strip. Preserve texture UVs,
    topology and the content frame, collapsing only geometry below authored Z=0.
    """
    graph = G.IgbFile(data)
    if graph.objects_of('igTransform'):
        raise G.IgbError('TEAM panel source must be flat')
    seen, zs = set(), []
    for array in graph.objects_of('igVertexArray1_1'):
        refs = graph.ref_list(array.get(2))
        ref = refs[0] if refs else -1
        if ref not in graph.blocks or ref in seen or graph.block(ref)[1] != array.get(3)*12:
            raise G.IgbError('TEAM panel source has unsupported positions')
        seen.add(ref)
        values = graph.block_floats(ref)
        if any(not math.isfinite(v) for v in values):
            raise G.IgbError('TEAM panel source has nonfinite positions')
        zs.extend(values[2::3])
        values[2::3] = [max(0, z) for z in values[2::3]]
        graph.set_block_floats(ref, values)
    if not zs or min(zs) >= 0 or max(zs) <= 0:
        raise G.IgbError('TEAM dialog source does not straddle its content seam')
    for box in graph.objects_of('igAABox'):
        for slot in (2, 3):
            graph.set_floats(box, slot, [max(0, box.get(slot)[2])], 2)
    return graph.edited()


def tree(native):
    root = H.tree(native, SCENE, FRAMES, RETIRED, lists=LISTS)
    # The native primary scene draws portrait textures without lighting. The
    # separate perspective helper owns the room/actor lights. Lighting the flat
    # primary scene turns an unlocked hero's portrait into a black rectangle.
    if 'lighting' in native.attrib:
        root.set('lighting', native.get('lighting'))
    else:
        root.attrib.pop('lighting', None)
    for helper in root.findall('items'):
        helper.set('igb', BACK)
        # The disc scene supplies the room. The native act-specific cave model
        # is presentation only; all native actor/camera helper roles remain.
        helper.attrib.pop('act_background', None)
    for precache in root.findall('precache'):
        if precache.get('filename') == 'ui/menus/x2m_team_back':
            precache.set('filename', 'ui/menus/' + BACK)
    return root


def control_problems(native, converted):
    """Compare every nonvisual attribute and all service children, including unknown fields."""
    errors = H.control_problems(native, converted, RETIRED)
    if native.get('lighting') != converted.get('lighting'):
        errors.append('TEAM primary portrait lighting policy changed')
    before = [e for e in native if e.tag != 'item']
    after = [e for e in converted if e.tag != 'item']
    if len(before) != len(after):
        errors.append('TEAM service child count changed')
    for old, new in zip(before, after):
        allowed = {'igb', 'act_background'} if old.tag == 'items' else \
                  {'filename'} if old.tag == 'precache' else set()
        if old.tag != new.tag or any(old.get(k) != new.get(k)
                for k in set(old.attrib) | set(new.attrib) if k not in allowed):
            errors.append('TEAM service helper/animation changed: ' + old.tag)
    if sorted(e.get('name', '') for e in native.findall('item')) != \
            sorted(e.get('name', '') for e in converted.findall('item')):
        errors.append('TEAM native item set changed')
    return errors


def detail_camera_position(camera, actor, room_scale):
    """Keep the native preview distance after mapping a differently sized room."""
    if len(camera) != 3 or len(actor) != 3 or not .5 < room_scale < 2 or \
            any(not math.isfinite(v) for v in (*camera, *actor)):
        raise G.IgbError('TEAM detail camera needs finite positions and a supported room scale')
    return [a + (c-a)/room_scale for c, a in zip(camera, actor)]


def quiet_room(data):
    """Retire ray and pulse meshes whose disc visibility pumps are not used here.

    The room and its blue podium materials/lights remain. Native TEAM owns the
    selected actor; freezing the disc's material pumps exposed every light cone.
    """
    graph = G.IgbFile(data)
    rays = [o for o in graph.objects_of('igTransform')
            if (o.get(2) or '').startswith('Lightrays_')]
    pulses = [o for o in graph.objects_of('igTransform')
              if (o.get(2) or '').startswith('LightPulse')]
    if len(rays) != 4 or len(pulses) != 16:
        raise G.IgbError('TEAM room needs four ray and sixteen pulse transforms')
    for node in rays + pulses:
        children = graph.obj(node.get(7))
        if children is None or children.name != 'igNodeList':
            raise G.IgbError('TEAM light ray has unsupported children')
        for slot,value in ((2,0),(3,0),(4,-1)):
            struct.pack_into('<i', graph.buf, children.fields[slot].offset, value)
    return graph.edited()


def helper_tree(native):
    """Keep native actor/focus/camera roles over the disc's blue podiums."""
    root = copy.deepcopy(native)
    for i in range(1, 5):
        root.find(f"item[@name='pad{i:02}']").set('model', 'ui/models/model_hide')
        effect = root.find(f"item[@name='pad{i:02}_loopfx']")
        effect.attrib.pop('effect', None)
        effect.set('hide', 'true')
    return root


def quiet_marker(data):
    """Keep the flat blue seated-hero marker without a selection spotlight.

    Native TEAM instantiates this focus model for every seated hero. The disc
    selection model also contains animated beams and gold rings, appropriate
    for its single selected podium but overexposing all four native seats.
    """
    graph = G.IgbFile(data)
    transforms = graph.objects_of('igTransform')
    beams = [o for o in transforms if (o.get(2) or '').startswith('$nn$_Pedastal_Spot_')]
    rings = [o for o in transforms if o.get(2) == '$nn$_SelectionRing']
    if len(beams) != 4 or len(rings) != 2:
        raise G.IgbError('TEAM selection marker has unsupported beam/ring layout')
    for node in beams + rings:
        children = graph.obj(node.get(7))
        if children is None or children.name != 'igNodeList':
            raise G.IgbError('TEAM selection marker has unsupported children')
        for slot,value in ((2,0),(3,0),(4,-1)):
            struct.pack_into('<i', graph.buf, children.fields[slot].offset, value)
    return graph.edited()


def quiet_pad_effect(native):
    """Retain the native effect resource with transparent visual emitters.

    TEAM reactivates seated-pad effects during updates. Its additive cylinder
    carries a one-second alpha pulse independently of the backdrop geometry.
    """
    root=copy.deepcopy(native)
    for emitter in root.iter():
        if emitter.get('alpha') is not None:
            emitter.set('alpha','0 0 0 0 0 0')
    return root


DETAIL_REGIONS = {
    'ui/models/m_team_stats_panel': ((-145,65,145,127), (-145,41,145,65), (-145,-149,145,37)),
    'ui/models/m_team_gear_panel': ((-145,65,145,127), (-145,7,145,55), (-170,-149,145,0)),
    'ui/models/m_team_ai_panel': ((-145,22,145,128), (-145,-149,145,12)),
}


def detail_frames(data, source, regions, depth):
    """Frame native tables, counters and descriptions with the same classic art.

    Native widgets keep their positions and depths. Insets sit in front of the
    outer fill and behind its text, retaining separate texture registrations.
    """
    data = S.static_model(data)
    for rectangle in regions:
        section, _ = M.fit_flat_panel(source, rectangle, border=4, opaque=True)
        section = M.foreground_chrome(section, layer=(depth[0]+1, depth[1]-1))
        data, _ = S.attach(data, S.static_model(section), merge_textures=True)
    return data


def backdrop(original, native):
    """Keep native helper references while moving them into the authored room.

    Both rooms have the same diamond party arrangement. Derive its similarity
    transform from the disc's four actor anchors and the native four pad anchors;
    never hardcode hero IDs, stat values or an original four-podium browse flow.
    """
    a, n = G.IgbFile(original), G.IgbFile(native)
    def node(graph, name):
        values = [o for o in graph.objects_of('igTransform') if o.get(2) == name]
        if len(values) != 1:
            raise G.IgbError('TEAM room needs one anchor: ' + name)
        return values[0]
    src = [node(n, f'pad{i:02}_model').get(8)[12:15] for i in range(1, 5)]
    dst = [node(a, f'char_model{i}').get(8)[12:15] for i in range(1, 5)]
    sx, sy = src[1][0]-src[0][0], src[1][1]-src[0][1]
    dx, dy = dst[1][0]-dst[0][0], dst[1][1]-dst[0][1]
    denominator = sx*sx + sy*sy
    if denominator < 1:
        raise G.IgbError('TEAM room has degenerate actor positions')
    c, s = (dx*sx+dy*sy)/denominator, (dy*sx-dx*sy)/denominator
    scale = math.hypot(c, s)
    if not .5 < scale < 2:
        raise G.IgbError('TEAM room scale is outside the supported range')
    tx = dst[0][0] - c*src[0][0] + s*src[0][1]
    ty = dst[0][1] - s*src[0][0] - c*src[0][1]
    tz = dst[0][2] - scale*src[0][2]
    def position(v):
        return [c*v[0]-s*v[1]+tx, s*v[0]+c*v[1]+ty, scale*v[2]+tz]
    if any(math.dist(position(x), y) > 1 for x, y in zip(src, dst)):
        raise G.IgbError('TEAM rooms do not share the supported party arrangement')
    # Rotate every helper basis without scaling actors. The overview follows the
    # room; detail camera distances remain native so floating/tall previews fit.
    detail_actors = {f'cam_position{i:02}': src[i-1] for i in range(1, 5)}
    for obj in n.objects_of('igTransform'):
        matrix = list(obj.get(8))
        for offset in (0, 4, 8):
            x, y = matrix[offset:offset+2]
            matrix[offset:offset+2] = [(c*x-s*y)/scale, (s*x+c*y)/scale]
        mapped = position(matrix[12:15])
        if obj.get(2) in detail_actors:
            mapped = detail_camera_position(mapped, position(detail_actors[obj.get(2)]), scale)
        matrix[12:15] = mapped
        n.set_floats(obj, 8, matrix)
    # Retire aliases in the art so native TEAM alone owns interactive actors.
    names = {o.get(2) for o in a.objects_of('igHashedUserInfo')}
    art, _ = M.rename_aliases(quiet_room(original), {name: 'lc_room_' + name for name in sorted(names)})
    art = S.static_model(art, allow_transforms=True)
    data, report = S.attach(S.retire_camera(n.edited()), art)
    report['room_scale'] = scale
    report['native_detail_distance_preserved'] = True
    return data, report


def write(ctx):
    from . import frontend as F
    source = ctx.x1_path('ui/hud/dialog.igb')
    room = ctx.x1_path('ui/menus/menu_characters_back.igb')
    native = ctx.base_index.path('UI/menus/x2m_team.IGB')
    back = ctx.base_index.path('UI/menus/x2m_team_back.IGB')
    if any(p is None for p in (source, room, native, back)):
        raise ValueError('classic TEAM frame/room/native input missing')
    tint = T.rgba(list(ctx.read_x1_xml('data/colors.xml'))[7].get('value'))[:3]
    report = {'frames': {}}
    panel = panel_source(source.read_bytes())
    for before, after in FRAMES.items():
        report['frames'][after] = H.frame(ctx, panel, before, after,
                                         tint=tint if before.endswith('_focus') else None)
        if before in DETAIL_REGIONS:
            asset = ctx.base_index.path(before + '.IGB').read_bytes()
            low, high = H.model_bounds(asset)
            framed = detail_frames(ctx.out_index.path(after + '.IGB').read_bytes(),
                                   panel, DETAIL_REGIONS[before], (low[1], high[1]))
            ctx.write_bytes(after + '.IGB', framed,
                            source='frontend:classic TEAM table/counter/description subframes')
            report['frames'][after]['sections'] = DETAIL_REGIONS[before]
        if before not in ('ui/models/m_team_helpbar', 'ui/models/m_team_browse_iteminven'):
            # TEAM also loads panel/selection resources by their native names.
            # Keep those names and native model rectangles for the dynamic path.
            ctx.write_bytes(before + '.IGB', ctx.out_index.path(after + '.IGB').read_bytes(),
                            source='frontend:classic native dynamic TEAM panel')
    data = M.place_anchors(native.read_bytes(), H.retired_layout(native.read_bytes(), RETIRED))
    ctx.write_bytes('UI/menus/' + SCENE + '.IGB', data, source='frontend:classic TEAM native anchors')
    data, report['backdrop'] = backdrop(room.read_bytes(), back.read_bytes())
    ctx.write_bytes('UI/menus/' + BACK + '.IGB', data, source='frontend:disc character room with native TEAM helpers')
    # The disc room file carries an external IGB reference to the disc's exit podium model
    # (ui/models/model_char_persp_exit): the engine loads that model with the room and draws its
    # four pulsing spot cones over every seat (0.4.0b live bisect: only replacing this model removed
    # the cones; retiring room meshes, the focus marker, the pad effect and the lights did not).
    # The disc asset copy supplies the real model; this build writes the invisible model instead.
    invisible = ctx.base_index.path('UI/models/m_invis.IGB')
    if invisible is None:
        raise ValueError('classic TEAM invisible model missing: UI/models/m_invis.IGB')
    ctx.write_bytes(EXIT_PODIUM, invisible.read_bytes(), replace=True,
                    source='frontend:disc TEAM exit podium (room external reference) made invisible')
    # Native TEAM code (0x5dc440) sets each pad_levelup%02d item's model by itself: m_invis, or
    # ui/models/m_team_levelup (a textured cylinder: the spinning gold helix ring) for every seated
    # hero that passes its level check (catalogue name acknowledged_level_compare: a level-up not
    # acknowledged yet). The helper tree's m_invis on those items is overridden every update, so the
    # rings appeared on all four podiums (0.4.0b live bisect: room, pads, focus marker, exit podium
    # and pad_loop emitters were not the source; only this model's removal cleared them). The Xbox
    # original (gallery row 29) draws no such ring; write the invisible model under the native name.
    ctx.write_bytes(LEVELUP_RING, invisible.read_bytes(), replace=True,
                    source='frontend:native TEAM level-up helix ring (code-assigned model) made invisible')
    helper = helper_tree(ctx.read_base_xmlb('UI/menus/team_back.XMLB'))
    ctx.write_xmlb('UI/menus/team_back', helper, source='frontend:native TEAM helper over disc podiums')
    ctx.write_xmlb('Effects/menu/pad_loop', quiet_pad_effect(ctx.read_base_xmlb('Effects/menu/pad_loop.XMLB')),
                   source='frontend:transparent native TEAM additive pad pulse')
    for target, source_name in (('m_team_pad_focus', 'model_char_persp_select'),
                                ('m_team_pad_locked', 'model_char_persp_locked')):
        asset = ctx.x1_path('ui/models/' + source_name + '.igb')
        if asset is None:
            raise ValueError('classic TEAM podium marker missing: ' + source_name)
        marker = asset.read_bytes()
        if target == 'm_team_pad_focus':
            marker = S.static_model(quiet_marker(marker), allow_transforms=True)
        ctx.write_bytes('UI/models/' + target + '.IGB', marker,
                        source='frontend:disc TEAM selection/locked marker')
    for name in ('m_team_namebar', 'm_team_healthgauge', 'm_team_energygauge'):
        asset = ctx.base_index.path('UI/models/' + name + '.IGB')
        ctx.write_bytes('UI/models/' + name + '.IGB', M.tint_vertex_colors(asset.read_bytes(), tint),
                        source='frontend:native TEAM gauge geometry with classic palette')
    for name in ('m_team_stats_select', 'm_team_ai_select', 'm_team_skill_select', 'm_team_gear_selection'):
        asset = ctx.base_index.path('UI/models/' + name + '.IGB')
        ctx.write_bytes('UI/models/' + name + '.IGB', M.tint_vertex_colors(asset.read_bytes(), tint),
                        source='frontend:native TEAM selection geometry with classic palette')
    halves = []
    for ext in ('.XMLB', '.engb'):
        old = ctx.read_base_xmlb('UI/menus/team' + ext)
        new = tree(old)
        errors = control_problems(old, new)
        if errors:
            raise ValueError('; '.join(errors))
        halves.append(new)
    ctx.write_xmlb_pair('UI/menus/team', *halves, source='frontend:classic TEAM with native port flow')
    package = M.package_for(halves[0], inherited=ctx.read_base_xmlb(F.MENU_PKG_DIR + '/team.PKGB'))
    ctx.write_xmlb(F.MENU_PKG_DIR + '/team', package, ('.PKGB',), source='frontend:classic TEAM resource closure')
    return report
