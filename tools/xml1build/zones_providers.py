"""xml1build.zones_providers - fallback copies of the scripts-module provider functions (SPEC.md 5.0 / 5.2.5).

zones.py calls the provider functions of tools/xml1build/scripts.py (rewrite_data_tree, zone_script_ref,
zone_package_extras, zone_act, script_exists). When that module is absent (it is written by another owner) or
lacks one of them, zones.py falls back to the implementations here, which follow the SPEC 5.2.5 text exactly
and read only research/scripts/out (the same inputs the scripts module installs). They are pure: they never
write, and cache their data in ctx.shared['_zones_prov'] (private key, not part of the SPEC hand-over table).
"""
from __future__ import annotations

import threading

from . import common as C

# XML1 front-end scripts the scripts module does NOT install (SPEC 5.2.1); XML2 keeps its own intro_normal,
# main_back_main and main_back_debug, which exist in the base install anyway.
FRONT_END_NOT_INSTALLED = frozenset({'menus/intro_demo', 'menus/intro_e3'})
SCRIPT_ATTRS = frozenset({'actscript', 'deathscript', 'chosenscriptfile', 'scriptfile', 'script', 'zonescript'})
NOT_SCRIPT_ATTRS = frozenset({'launchedfromscript'})     # boolean flag in XML1 data (launchedFromScript="true")
INLINE_LIMIT = 255                   # XMen2.exe 0x4a12b5 strncpy(buf, src, 0xff)
_lock = threading.RLock()


def is_script_attr(name: str) -> bool:
    n = (name or '').lower()
    return n not in NOT_SCRIPT_ATTRS and (n in SCRIPT_ATTRS or n.endswith('script') or n.endswith('scriptfile'))


def _cache(ctx):
    with _lock:
        c = ctx.shared.get('_zones_prov')
        if c is None:
            c = ctx.shared['_zones_prov'] = {}
        return c


def _research_json(ctx, rel):
    try:
        return ctx.research_json(rel)
    except FileNotFoundError:
        return {}


def research_script_refs(ctx):
    """lowercase refs of every script in research/scripts/out/scripts (the set the scripts module installs)."""
    c = _cache(ctx)
    with _lock:
        if 'refs' not in c:
            root = ctx.research_path('scripts/out/scripts')
            refs = set()
            if root.is_dir():
                for p in root.rglob('*.py'):
                    refs.add(C.script_ref(p.relative_to(root).as_posix()))
            c['refs'] = frozenset(refs - FRONT_END_NOT_INSTALLED)
        return c['refs']


def script_exists(ctx, ref) -> bool:
    """SPEC 5.2.5: the ref is in the installed (ctx.shared['scripts_installed']) or planned set."""
    r = C.script_ref(ref or '')
    if not r:
        return False
    inst = ctx.shared.get('scripts_installed')
    if inst and r in inst:
        return True
    return r in research_script_refs(ctx)


def rewrite_data_tree(ctx, root, rel) -> int:
    """SPEC 5.2.5: exact-value replacement from inline_rewrites.json; script-reference attributes without '('
    get backslash -> '/', lower case and no '.py'; inline code > 255 bytes gives a warning. Returns #changes."""
    inline = _research_json(ctx, 'scripts/out/inline_rewrites.json')
    n = 0
    for el in root.iter():
        for k, v in list(el.attrib.items()):
            if v is None:
                continue
            nv = inline.get(v, v)
            if is_script_attr(k) and nv and '(' not in nv:
                s = nv.replace('\\', '/').lower()
                if s.endswith('.py'):
                    s = s[:-3]
                nv = s
            elif '(' in nv and len(nv.encode('latin-1', 'replace')) > INLINE_LIMIT:
                ctx.warn(f'{rel}: inline script in {el.tag}@{k} is {len(nv)} bytes (> {INLINE_LIMIT}, truncated by '
                         f'XMen2.exe)')
            if nv != v:
                el.set(k, nv)
                n += 1
    return n


def _x1_world_zonescript(ctx, zone):
    for ext in ('.eng', '.xml'):
        rel = f'maps/{zone}{ext}'
        if ctx.x1_path(rel) is None:
            continue
        try:
            root = ctx.read_x1_xml(rel)
        except (KeyError, ValueError, SyntaxError):
            return None
        if root is None:
            return None
        w = C.find_world(root)
        v = (w.get('zonescript') or '').strip() if w is not None else ''
        return C.script_ref(v) if v and '(' not in v else None
    return None


def zone_script_ref(ctx, zone):
    """SPEC 5.2.5 order: zone_acts[zone]['zonescript'] if installed; else x1/zones/<zone> if generated; else the
    XML1 world zonescript normalised, if that script exists; else None."""
    zone = C.norm(zone)
    acts = _research_json(ctx, 'scripts/out/zone_acts.json')
    d = acts.get(zone) or {}
    zs = d.get('zonescript')
    if zs and script_exists(ctx, zs):
        return C.script_ref(zs)
    gen = f'x1/zones/{zone}'
    if script_exists(ctx, gen):
        return gen
    ws = _x1_world_zonescript(ctx, zone)
    if ws and script_exists(ctx, ws):
        return ws
    return None


def zone_package_extras(ctx, zone):
    """SPEC 5.2.5: zone_extra_files.json -> dialogs/x1/pNNN as ('xml_resident', ...), scripts/x1/... as
    ('script', ...)."""
    extra = _research_json(ctx, 'scripts/out/zone_extra_files.json').get(C.norm(zone), [])
    out = []
    for f in extra:
        f = C.norm(f)
        if f.startswith('dialogs/'):
            out.append(('xml_resident', f))
        elif f.startswith('scripts/'):
            out.append(('script', f))
        else:
            out.append(('xml', f))
    return out


def zone_act(ctx, zone):
    """SPEC 5.2.5: inject_act, else the first of acts, else None."""
    d = _research_json(ctx, 'scripts/out/zone_acts.json').get(C.norm(zone)) or {}
    if d.get('inject_act'):
        return int(d['inject_act'])
    if d.get('acts'):
        return int(d['acts'][0])
    return None
