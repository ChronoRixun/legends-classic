"""xml1build.x1schema - XML1 -> XML2 schema conversions applied to every XML1 text file the build writes.

common.BuildContext.import_x1_asset runs convert() on every imported XML1 text tree (before the importing module's
own patch), and zones runs it on the world tables it merges itself, so every module gets the same conversion:

1. Entity classes (any element with a 'classname' attribute).
   XMen2.exe registers exactly 27 entity classes through 0x461080 (REGISTERED_ENTITY_CLASSES). An unknown
   classname does not fail: the class lookup 0x4611a0 falls back to the default factory 0x718444 (0x4611ee
   cmp 0x3fffffff), registered at 0x67a45c as the bare 0x70-byte 'ent' - no health, no damage, no deathscript.
   XML1 (default.xbe) also registers harmtargetent, scanturretent and lightningentity (strings 0x3cda84,
   0x3d342c, ...), which XMen2.exe does not know, so they are remapped (CLASS_REMAP):
     * harmtargetent   -> affectableharment  (XML2's successor: every harmtargetent attribute XML2 reads is on
                                              XML2's own affectableharment entities: damage, damagetype,
                                              radiusdamage, boxdamage, knockback, actrescheduledelay, ...)
     * lightningentity -> affectableharment  (XML2's own port of the same entity: ents_storm storm_p1_lightning
                                              has XML1 storm_lightning1's attribute set with classname
                                              affectableharment)
     * scanturretent   -> physent            (keeps health / structure / deathscript / spawnscript / deathspawn /
                                              deathsound / targetlockable, so the progression deathscripts fire;
                                              turret aiming and firing are lost - XMen2.exe has no turret class
                                              and no 'turret' string at all). XML1 draws a scan turret with its
                                              turretweapon's model (the entity has no model attribute); the
                                              physent gets that model so it stays visible and hittable.
2. Renamed entity attributes: XML1 'persistant' (default.xbe string; XMen2.exe has none) -> XML2 'persistent'
   (XMen2.exe string 0x68683c; 94 XML2 retail entities use it).
3. Effect colours (files under effects/). XML1 colours each primitive with quadratic 'red'/'green'/'blue' curves
   ('a1 b1 c1 a2 b2 c2 [max min]': v(t) = a*t^2 + b*t + c over the particle life, colour 1 and colour 2);
   XMen2.exe reads only packed colours startColor1/2, midColor1/2, endColor1/2 (strings next to 'radius2' at
   0x681ca4-0x681cbc; 'red'/'green'/'blue' are not XMen2.exe or DLL strings). XML2 retail uses the packed form
   in all 3,975 coloured primitives except 3 unreferenced leftovers. Conversion, matching XML2's own conversion
   of the same-named test effects (test/redsquare, greensquare, yellowsquare, ...; see selftest()):
     * each channel is evaluated at t = 0, 0.5, 1, clamped to [min, max] (8-value form) and to 0..1, and
       scaled to a byte with truncation (0.5 -> 0x7F, 0.1 -> 0x19, 0.4 -> 0x66, as XML2 did);
     * packed A<<24 | B<<16 | G<<8 | R as an unsigned decimal (XML2's spelling);
     * a constant 'alpha' curve is folded into the A byte and dropped (as XML2 did for the test squares);
       a varying 'alpha' curve is kept (XML2 retail keeps 3,728 alpha curves, 46 of them in the 8-value form)
       and A = 0xFF (what Raven's converter wrote next to kept curves, e.g. base/hit/hit_cold);
     * red/green/blue are removed.
4. Combat styles (data/powerstyles/*, data/fightstyles/*, data/shared_nodes): combat_events.rewrite_style - an
   event or trigger built on an XML1-only shared combat event (blast_ranged) is re-pointed at XML2's equivalent
   with the XML1 parent's attributes / damageMods it does not set itself, and XML1 FightMove handlers with an XML2
   counterpart are renamed (ch_throw -> ch_pickup_throw), as is the affecter atk_damage_scale (-> scale-type
   atk_damage). XMen2.exe drops a trigger whose name does not resolve (0x501630), runs an unknown handler as
   %default% (0x4fd860) and parses an unknown affecter as none (0x534d90). SPEC.md section 22.
   Then combat_events.apply_x1_shared_values: an XML1 event / trigger that leaves damage (or the throw's damageMod) to
   a shared combat event XML2's shipped table changed gets XML1's value (punch L1 = "4 5" instead of XML2's "2 3"),
   SPEC.md section 33; and convert_renderfx: XML1's ce_renderfx tint form -> XML2's add / remove="cloaked",
   SPEC.md section 31.
5. Object physics scales (issue #51): entity heaviness 0..5 -> XMen2.exe's 0..3 and structure 0..10 -> 0..2
   (convert_physics), so ordinary objects can be lifted and breakable walls can open. Attack levels retain
   main behavior: level zero cannot damage living characters (0x4293e3). The punch/power wall rule needs an engine fix.
"""
from __future__ import annotations

import collections
import math

from . import combat_events as CE

# XMen2.exe entity classes (registered through 0x461080; each name is a 4-aligned .rdata string, e.g. physent at
# 0x682a30, affectableharment at 0x6841f4). XML2 retail data uses 26 of them as classname (all but worldent).
REGISTERED_ENTITY_CLASSES = frozenset({
    'actionent', 'actor', 'affectableharment', 'cameramagnetent', 'doorent', 'enabletargetent', 'ent', 'gameent',
    'guidedprojectileent', 'inventoryent', 'lightent', 'monsterspawnerent', 'moverent', 'physent',
    'playerstartent', 'powertriggerent', 'projectileent', 'projectiletornadoent', 'rememberent',
    'scripttriggerent', 'sentryent', 'tileent', 'treasureent', 'waterent', 'waypointent', 'worldent',
    'zonelinkent'})

CLASS_REMAP = {
    'harmtargetent': 'affectableharment',
    'lightningentity': 'affectableharment',
    'scanturretent': 'physent',
}
CLASS_REMAP_LOSSES = {
    'harmtargetent': 'none known (XML1-only extras kept: actscript/actspawn/spawnscript/deathstyle/stophero/'
                     'stopnpc*; the typo "healh" is kept as in XML1, where it was not read either)',
    'lightningentity': "'chains' (chain count) has no XML2 reader",
    'scanturretent': 'turret aiming/firing (turretweapon, turnrate, turndelay, resetdelay, yaw/pitch/visextent, '
                     'rotatesound); the fixed mount is kept by TURRET_MOUNT_FLAGS',
}
# XML1's scanturretent is a fixed mount (it never falls, is never pushed or picked up). A plain physent does all
# three, so a remapped turret gets the flags every XML1-authored physent on the same vehicles carries (haarp_ext02 /
# haarp_ext04 tank_base, tank, tank_turret_haarp_sp_d; hive1_1_1 tank_vehicle_hex01-04, tank_turret_sp_d all have
# nogravity=nopickup=nopush=true). Without them setNoClip('tank_turret', 'FALSE') in haarp/ext/tank_ready lets the
# turret drop off the tank or be thrown, while its deathscript gates progression (tank_destroyed, haarp3 flag,
# turret_death). An explicit value the entity already has is kept.
TURRET_MOUNT_FLAGS = (('nogravity', 'true'), ('nopickup', 'true'), ('nopush', 'true'))
ENTITY_ATTR_RENAMES = {'persistant': 'persistent'}

COLOR_CHANNELS = ('red', 'green', 'blue')
COLOR_KEYS = (('startcolor', 0.0), ('midcolor', 0.5), ('endcolor', 1.0))


# --------------------------------------------------------------------------------------------- effect colours
def parse_curve(value):
    """'a1 b1 c1 a2 b2 c2 [max min]' | 'a b c' -> ((a1, b1, c1), (a2, b2, c2), lo, hi) or None if unparsable."""
    try:
        v = [float(x) for x in str(value).split()]
    except ValueError:
        return None
    if len(v) == 3:
        v = v + v
    if len(v) not in (6, 8):
        return None
    hi, lo = (v[6], v[7]) if len(v) == 8 else (math.inf, -math.inf)
    if lo > hi:
        lo, hi = hi, lo
    return (tuple(v[0:3]), tuple(v[3:6]), lo, hi)


def eval_curve(coef, t, lo=-math.inf, hi=math.inf):
    a, b, c = coef
    v = a * t * t + b * t + c
    v = min(max(v, lo), hi)
    return min(max(v, 0.0), 1.0)


def to_byte(v):
    """0..1 -> 0..255 truncating, as XML2's conversion did (0.5 -> 127, 0.1 -> 25, 0.4 -> 102), with a small
    tolerance so float noise (0.6 * 255 = 152.99999999999997) does not lose a step."""
    return max(0, min(255, int(math.floor(v * 255.0 + 1e-6))))


def pack_abgr(r, g, b, a):
    return (a << 24) | (b << 16) | (g << 8) | r


def curve_is_constant(curve):
    (a1, b1, _), (a2, b2, _), _, _ = curve
    return a1 == 0 and b1 == 0 and a2 == 0 and b2 == 0


def convert_effect_colors(root):
    """Convert every primitive of an effect tree that has red/green/blue curves (see module doc). Returns the
    number of primitives converted. Attribute order is left to encode_xmlb (lowercase + sorted)."""
    n = 0
    for el in root.iter():
        if not any(el.get(c) is not None for c in COLOR_CHANNELS):
            continue
        if el.get('startcolor1') is not None:            # already XML2 form: just drop the dead XML1 channels
            for c in COLOR_CHANNELS:
                el.attrib.pop(c, None)
            continue
        curves = {}
        for c in COLOR_CHANNELS:
            raw = el.get(c)
            curves[c] = parse_curve(raw) if raw is not None else ((0, 0, 1.0), (0, 0, 1.0), -math.inf, math.inf)
            if curves[c] is None:                          # unparsable channel: treat as white, like a missing one
                curves[c] = ((0, 0, 1.0), (0, 0, 1.0), -math.inf, math.inf)
        alpha_raw = el.get('alpha')
        alpha = parse_curve(alpha_raw) if alpha_raw is not None else None
        fold_alpha = alpha is not None and curve_is_constant(alpha)
        for key, t in COLOR_KEYS:
            for idx in (0, 1):
                rgb = [to_byte(eval_curve(curves[c][idx], t, curves[c][2], curves[c][3])) for c in COLOR_CHANNELS]
                a = to_byte(eval_curve(alpha[idx], 0.0, alpha[2], alpha[3])) if fold_alpha else 255
                el.set(f'{key}{idx + 1}', str(pack_abgr(rgb[0], rgb[1], rgb[2], a)))
        for c in COLOR_CHANNELS:
            el.attrib.pop(c, None)
        if fold_alpha:
            el.attrib.pop('alpha', None)
        n += 1
    return n


# --------------------------------------------------------------------------------------------- entities
def convert_entities(root, weapon_models=None):
    """Remap XML1-only entity classes and renamed attributes in place. weapon_models: lower weapon name ->
    model path (XML1 data/weapons/weapons.eng) for the scan-turret model. Returns [(kind, detail)]."""
    changes = []
    for el in root.iter():
        for old, new in ENTITY_ATTR_RENAMES.items():
            if old in el.attrib:
                v = el.attrib.pop(old)
                if new not in el.attrib:
                    el.set(new, v)
                changes.append(('attr', f'{old}->{new}'))
        cls = el.get('classname')
        if cls is None:
            continue
        lc = cls.strip().lower()
        new = CLASS_REMAP.get(lc)
        if new is None:
            if cls != lc and lc in REGISTERED_ENTITY_CLASSES:
                el.set('classname', lc)
            continue
        el.set('classname', new)
        changes.append(('class', f'{lc}->{new}'))
        if lc == 'scanturretent':
            for k, v in TURRET_MOUNT_FLAGS:
                if el.get(k) is None:
                    el.set(k, v)
                    changes.append(('turret_mount', k))
            if not el.get('model') and weapon_models:
                m = weapon_models.get((el.get('turretweapon') or '').strip().lower())
                if m:
                    el.set('model', m)
                    changes.append(('turret_model', m))
    return changes


# --------------------------------------------------------------------------------------------- object physics scales
# XML1 and XMen2.exe read an entity's `heaviness` and `structure` on different scales (issue #51):
#   * heaviness: default.xbe clamps it to 5 and lifts an object when heaviness < 5 and heaviness <= might + 1
#     (pickup gate 0x38400, might = the hero's `might` talent rank, 0xb1ba0), so anyone lifts 0-1 and might rank
#     1/2/3 lifts 2/3/4. XMen2.exe clamps it to 3 (physent parser 0x498900) and lifts when heaviness < 3 and
#     heaviness <= the might_heaviness affecter sum (0x427f60 -> 0x427dc0, 0 without Might), so a hero without
#     Might lifts only 0. XML1's value copied unchanged turned every heaviness-1 trash can into a Might-only object.
#     HEAVINESS_X1_TO_X2 reproduces anyone / might 1 / might 2 exactly; XML1's 4 (might 3) and 5 (never) both
#     become 3, which XMen2.exe never lifts (the "< 3" at 0x427fa3; an engine limit, see SPEC).
HEAVINESS_X1_TO_X2 = (0, 0, 1, 2, 3, 3)
# Characters' heaviness (herostat / npcstat <stats>) is a different property and is not touched: only elements with
# a classname (entity definitions) are converted.


def heaviness_x1_to_x2(value):
    """XML1 heaviness text -> XMen2.exe's (str), or None when it is not a number (left as it is)."""
    try:
        v = int(float(str(value).strip()))
    except ValueError:
        return None
    return str(HEAVINESS_X1_TO_X2[min(max(v, 0), len(HEAVINESS_X1_TO_X2) - 1)])


# Object structure is compressed so formerly unbreakable walls can open. Attack levels must remain as on main:
# living characters require hit level > structure (0x4293e3), so ordinary level-zero hits do no damage. Objects
# require level >= structure (0x498044), and the effective attack level is capped at 1 (0x44f770). With main's
# level-one punches, remapped structure-one walls also break to plain combos. Preserving the first game's
# punch/power distinction needs an independent object-only level comparison in XML2 Fix (SPEC issue #51).
STRUCTURE_X1_TO_X2 = (0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 2)


def _ival(value):
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def structure_x1_to_x2(value):
    v = _ival(value)
    return None if v is None else str(STRUCTURE_X1_TO_X2[min(max(v, 0), len(STRUCTURE_X1_TO_X2) - 1)])



def convert_physics(root):
    """XML1 -> XMen2.exe object physics scales on every entity definition (element with a classname), in place:
    heaviness and structure; attack damagelevel is unchanged. NOT idempotent (heaviness 2 -> 1 -> 0):
    convert() runs once on each freshly parsed XML1 tree. Returns a Counter."""
    c = collections.Counter()
    for el in root.iter():
        if el.get('classname') is None:
            continue
        for attr, fn in (('heaviness', heaviness_x1_to_x2), ('structure', structure_x1_to_x2)):
            old = el.get(attr)
            if old is not None and old.strip():
                new = fn(old)
                if new is not None and new != old:
                    el.set(attr, new)
                    c[f'{attr}_rescaled'] += 1
    return c



def physics_scale_problems(root):
    """[(entity name, attribute, value)] of entity definitions whose heaviness / structure is above XMen2.exe's range
    (0..3 / 0..2): an XML1 value that was not converted (convert_physics)."""
    out = []
    for el in root.iter():
        if el.get('classname') is None:
            continue
        for attr, top in (('heaviness', HEAVINESS_X1_TO_X2[-1]), ('structure', STRUCTURE_X1_TO_X2[-1])):
            v = _ival(el.get(attr)) if (el.get(attr) or '').strip() else None
            if v is not None and v > top:
                out.append((el.get('name'), attr, el.get(attr)))
    return out



def turret_mount_problems(root):
    """[(entity name, missing flags)] of physents that are remapped XML1 scan turrets (they carry a turretweapon)
    without the fixed-mount flags (TURRET_MOUNT_FLAGS)."""
    out = []
    for el in root.iter():
        if (el.get('classname') or '').strip().lower() != 'physent' or not el.get('turretweapon'):
            continue
        miss = [k for k, v in TURRET_MOUNT_FLAGS if (el.get(k) or '').strip().lower() != v]
        if miss:
            out.append((el.get('name'), miss))
    return out


def unknown_classes(root):
    """[(entity name, classname)] of elements whose classname XMen2.exe does not register."""
    out = []
    for el in root.iter():
        cls = el.get('classname')
        if cls is not None and cls.strip().lower() not in REGISTERED_ENTITY_CLASSES:
            out.append((el.get('name'), cls))
    return out


def color_channel_elements(root):
    """[(tag, name)] of elements that still carry XML1 red/green/blue channels."""
    return [(el.tag, el.get('name')) for el in root.iter() if any(el.get(c) is not None for c in COLOR_CHANNELS)]


# Positive firstact clears the loop bit in the harm parser (0x4396a0).
# Starting at zero keeps that bit without changing the non-smart damage path.
# Walls are staged underground; their placement scripts restart the loop at the
# destination. Do not use smartfire: it changes damage scheduling (SPEC 45).
def convert_haarp_fire_wall(root, rel):
    path = str(rel).replace('\\', '/').lower().lstrip('/')
    if not path.startswith('maps/haarp/ext/'):
        return 0
    changed = 0
    for el in root.iter('entity'):
        if (el.get('name') != 'fire_wall'
                or el.get('classname') != 'affectableharment'
                or el.get('loopfx') != 'ambient/fire_wall'
                or el.get('loopfxstarton', '').lower() != 'true'
                or 'smartfire' in el.attrib):
            continue
        try:
            delayed = float(el.get('firstact', '0')) > 0
        except ValueError:
            delayed = False
        if delayed:
            el.set('firstact', '0')
            changed += 1
    return changed


# --------------------------------------------------------------------------------------------- dispatcher
def is_effect_rel(rel):
    r = str(rel).replace('\\', '/').lower().lstrip('/')
    return r.startswith('effects/')


def convert(root, rel, weapon_models=None, x1_values=None):
    """Apply every conversion that applies to XML1 file `rel`. x1_values: heroes.Values of XML1's data/values.xml
    (resolves the codes section 33 writes; None writes the codes). Returns a Counter of change kinds."""
    c = collections.Counter()
    if root is None:
        return c
    if is_effect_rel(rel):
        n = convert_effect_colors(root)
        if n:
            c['effect_primitives_recoloured'] += n
            c['effect_files_recoloured'] += 1
    for kind, detail in convert_entities(root, weapon_models):
        c[f'{kind}:{detail}' if kind not in ('turret_model',) else kind] += 1
    c.update(convert_physics(root))
    n = convert_haarp_fire_wall(root, rel)
    if n:
        c['haarp_fire_wall_loop_start'] += n
    if CE.is_style_rel(rel):
        c.update(CE.rewrite_style(root))
        c.update(CE.apply_x1_shared_values(root, x1_values))
        c.update(convert_renderfx(root))
    return c


# --------------------------------------------------------------------------------------------- renderfx (SPEC 31)
# XMen2.exe's ce_renderfx parser (CCERenderFx vtable 0x692770 slot 4 = 0x4e94e0) reads `add` and `remove`, each a
# name of the renderfx table 0x6d7bd8 (none pain1 pain2 chilled metalfreeze radiation radiated fading xtreme_fb
# cloaked bleeding burning) OR-ed into a mask, then the base `time` / `tag`. XML1 (default.xbe) tinted the actor
# instead: tint / solid / alpha flags and an `rgba` colour, and `remove="true"` to end it; none of those names is an
# XMen2.exe string, so the triggers did nothing. XML2's own conversion of the same-named triggers (tintout / tintin,
# e.g. ps_deadpool's cloak) is `add="cloaked"` / `remove="cloaked"`, the translucent cloak.
RENDERFX_X1_ATTRS = ('tint', 'solid', 'alpha', 'rgba')
RENDERFX_X1_CLOAK = 'cloaked'


def convert_renderfx(root):
    """XML1 ce_renderfx tint triggers -> XML2's renderfx names, in place and idempotent: a trigger / event of type
    ce_renderfx with any of tint / solid / alpha / rgba and no `add` / `remove` name gets add="cloaked"; with
    remove="true" it gets remove="cloaked"; the XML1 attributes go. Returns a Counter {'renderfx:add|remove': n}."""
    c = collections.Counter()
    if root is None:
        return c
    for el in root.iter():
        if not isinstance(el.tag, str) or el.tag.lower() not in ('trigger', 'event'):
            continue
        a = {k.lower(): k for k in el.attrib}
        if (el.get(a.get('type', 'type')) or '').strip().lower() != 'ce_renderfx':
            continue
        x1 = [a[k] for k in RENDERFX_X1_ATTRS if k in a]
        rm = (el.get(a['remove']) if 'remove' in a else '') or ''
        if rm.strip().lower() == 'true':
            del el.attrib[a['remove']]
            el.set('remove', RENDERFX_X1_CLOAK)
            kind = 'remove'
        elif x1 and 'add' not in a and 'remove' not in a:
            el.set('add', RENDERFX_X1_CLOAK)
            kind = 'add'
        else:
            continue
        for k in x1:
            del el.attrib[k]
        c[f'renderfx:{kind}'] += 1
    return c


def renderfx_x1_elements(root):
    """[(tag, name)] of ce_renderfx elements still in XML1's form (tint / solid / alpha / rgba, or remove="true")."""
    out = []
    for el in root.iter():
        if not isinstance(el.tag, str) or el.tag.lower() not in ('trigger', 'event'):
            continue
        a = {k.lower(): v for k, v in el.attrib.items()}
        if (a.get('type') or '').strip().lower() == 'ce_renderfx' and \
                (any(k in a for k in RENDERFX_X1_ATTRS) or (a.get('remove') or '').strip().lower() == 'true'):
            out.append((el.tag, a.get('name')))
    return out


# --------------------------------------------------------------------------------------------- selftest
def selftest(xml1_effects_dir, xml2_effects_dir, decode_xmlb, parse_x1_text):
    """Compare convert_effect_colors on XML1's test effects with XML2's own conversions of the same files.
    Returns a list of failure strings (empty = pass)."""
    import os
    fails = []
    # the 6 XML1 test effects XML2 ships converted (test/axis was re-authored for XML2: different primitives)
    pairs = ('test/redsquare', 'test/greensquare', 'test/yellowsquare', 'test/bluesquare', 'test/grnspot',
             'test/testpuff')
    for name in pairs:
        p1 = os.path.join(xml1_effects_dir, name + '.xml')
        p2 = os.path.join(xml2_effects_dir, name + '.XMLB')
        if not (os.path.isfile(p1) and os.path.isfile(p2)):
            fails.append(f'{name}: test pair missing')
            continue
        r1 = parse_x1_text(p1)
        convert_effect_colors(r1)
        r2 = decode_xmlb(open(p2, 'rb').read())
        e1 = [e for e in r1.iter() if e.get('startcolor1') is not None]
        e2 = [e for e in r2.iter() if e.get('startcolor1') is not None]
        if len(e1) != len(e2):
            fails.append(f'{name}: {len(e1)} converted primitives vs {len(e2)} in XML2')
            continue
        for i, (a, b) in enumerate(zip(e1, e2)):
            for k in ('startcolor1', 'startcolor2', 'midcolor1', 'midcolor2', 'endcolor1', 'endcolor2'):
                if a.get(k) != b.get(k):
                    fails.append(f'{name} #{i} {k}: ours {int(a.get(k)):#010x} XML2 {int(b.get(k) or 0):#010x}')
            if (a.get('alpha') is None) != (b.get('alpha') is None):
                fails.append(f'{name} #{i}: alpha kept={a.get("alpha") is not None}, XML2 kept={b.get("alpha") is not None}')
            for c in COLOR_CHANNELS:
                if a.get(c) is not None:
                    fails.append(f'{name} #{i}: {c} not removed')
    # unit cases of the arithmetic
    cases = [('0 0 0.5 0 0 0.5', 127), ('0 0 0.1 0 0 0.1', 25), ('0 0 0.4 0 0 0.4', 102), ('0 0 0.6 0 0 0.6', 153),
             ('0 0 1 0 0 1 0.5 -10000', 127), ('0 0 2 0 0 2', 255), ('0 0 -1 0 0 -1', 0)]
    for raw, want in cases:
        cv = parse_curve(raw)
        got = to_byte(eval_curve(cv[0], 0.0, cv[2], cv[3]))
        if got != want:
            fails.append(f'curve {raw!r} at t=0: {got} != {want}')
    cv = parse_curve('0 -1 1 0 -1 1 10000 -10000')          # linear fade 1 -> 0
    got = [to_byte(eval_curve(cv[0], t, cv[2], cv[3])) for t in (0, 0.5, 1)]
    if got != [255, 127, 0]:
        fails.append(f'linear fade sampled {got} != [255, 127, 0]')
    return fails
