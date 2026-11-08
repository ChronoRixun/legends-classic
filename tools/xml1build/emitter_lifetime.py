"""Bound transient harm helpers to their physical bodies without renumbering.

Smart stream-out can bypass native parent-removal notification. A transient
action child checks the helper's exact parent handle, so siblings sharing an
instance name remain independent. No original body or placement is changed.
"""
from __future__ import annotations

import ast
import copy
import math
import xml.etree.ElementTree as ET

WATCHER = 'lc_emitter_watch'
START_REF = 'x1/emitter_lifetime/start'
CHECK_REF = 'x1/emitter_lifetime/check'
MARKER = 'xml1emitterlifetime'
_SPAWN_FIELDS = ('actspawn', 'deathspawn', 'xdeathspawn', 'monster_deathspawn')


def _factory(owner):
    """Recognize a literal spawn result immediately parented to _OWNER_."""
    try:
        code = owner.get('spawnscript', '').replace(r'\n\r', '\n')
        statements = ast.parse(code).body
    except (SyntaxError, ValueError):
        return None
    if len(statements) != 2:
        return None
    assign, parent = statements
    if not (isinstance(assign, ast.Assign) and len(assign.targets) == 1
            and isinstance(assign.targets[0], ast.Name)
            and isinstance(assign.value, ast.Call)
            and isinstance(assign.value.func, ast.Name)
            and assign.value.func.id == 'spawn' and not assign.value.keywords
            and len(assign.value.args) == 5):
        return None
    args = assign.value.args
    if not all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in args):
        return None
    if args[0].value != '_OWNER_':
        return None
    call = parent.value if isinstance(parent, ast.Expr) else None
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            and call.func.id == 'setParent' and not call.keywords and len(call.args) == 2
            and isinstance(call.args[0], ast.Name) and call.args[0].id == assign.targets[0].id
            and isinstance(call.args[1], ast.Constant) and call.args[1].value == '_OWNER_'):
        return None
    return args[1].value


def links(root):
    """Eligible (body definition, unplaced nonpersistent radius helper) pairs."""
    definitions = {e.get('name'): e for e in root.iter('entity')}
    placed = {g.get('type') for g in root.iter('entinst') if len(g)}
    result = []
    for owner in definitions.values():
        if (owner.get('classname') != 'physent' or owner.get('name') not in placed
                or any(owner.get(k) != 'true' for k in ('nogravity', 'nopickup', 'nopush'))
                or owner.get('startenabled') != 'false' or owner.get('actondeath') == 'true'):
            continue
        try:
            health = float(owner.get('health', '0'))
        except ValueError:
            continue
        if not math.isfinite(health) or health <= 0:
            continue
        factory = _factory(owner)
        child = definitions.get(factory)
        if child is None or factory in placed:
            continue
        if (child.get('classname') not in ('harmtargetent', 'affectableharment')
                or child.get('persistent', child.get('persistant')) != 'false'
                or child.get('model') or child.get('radiusdamage') != 'true'
                or child.get('spawnscript', '') not in ('', START_REF)):
            continue
        result.append((owner.get('name'), factory))
    # A factory also used by an unrelated authored spawner is not exclusively a
    # parent-bound helper. Preserve that factory rather than policing its birth.
    shared = {factory for _, factory in result if any(
        factory in e.get(field, '').split() and
        not ((e.get('name'), factory) in result and field == 'actspawn')
        for e in definitions.values() for field in _SPAWN_FIELDS)}
    for e in definitions.values():
        for key, code in e.attrib.items():
            if not key.endswith('script') or 'spawn' not in code:
                continue
            try:
                tree = ast.parse(code.replace(r'\n\r', '\n'))
            except (SyntaxError, ValueError):
                # Unknown control-flow syntax is not evidence of exclusive use.
                shared.update(factory for _, factory in result if factory in code)
                continue
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == 'spawn' and len(node.args) > 1
                        and isinstance(node.args[1], ast.Constant)):
                    factory = node.args[1].value
                    if key != 'spawnscript' or (e.get('name'), factory) not in result:
                        shared.add(factory)
    return [(owner, factory) for owner, factory in result if factory not in shared]


def _watcher():
    return dict(name=WATCHER, classname='actionent', smartent='false', persistent='false',
                nocollide='true', nogravity='true', startenabled='true', actonuse='false',
                actontouch='false', toggleonact='false', firstact='0.05',
                actrescheduledelay='0.05', actscript=CHECK_REF)


def generated_scripts():
    return {
        START_REF: f'lc_em_watch = spawn("_OWNER_", "{WATCHER}", "{WATCHER}", "0 0 0", "0 0 0")\n'
                   'setParent(lc_em_watch, "_OWNER_")\n',
        CHECK_REF: 'lc_em_helper = getParentID("_OWNER_")\n'
                   'lc_em_body = getParentID(lc_em_helper)\n'
                   'lc_em_health = getHealth(lc_em_body)\n'
                   'if lc_em_health <= 0\n'
                   '    setEnable(lc_em_helper, "FALSE")\n'
                   '    remove(lc_em_helper, "_OWNER_")\n'
                   '    remove("_OWNER_", "_OWNER_")\n'
                   'endif\n',
    }


def convert(root, scripts=None):
    """Add one unplaced watcher factory; change only eligible helper spawnscript.

The native timer avoids waiting script contexts and script recursion. The
watcher's first positive delay also lets the original caller install parentage.
"""
    selected = links(root)
    definitions = {e.get('name'): e for e in root.iter('entity')}
    watcher = definitions.get(WATCHER)
    helpers = {factory for _, factory in selected}
    marked = {e.get('name') for e in root.iter('entity') if MARKER in e.attrib}
    if marked - helpers or any(definitions[n].get(MARKER) != 'true' for n in marked):
        raise ValueError('invalid emitter lifetime helper marker')
    if watcher is not None and (not selected or watcher.attrib != _watcher()
                               or list(watcher) or any(g.get('type') == WATCHER for g in root.iter('entinst'))):
        raise ValueError('emitter lifetime watcher definition/placement collision')
    if not selected:
        return 0
    changed = watcher is None or any(definitions[n].get('spawnscript') != START_REF
                                    or definitions[n].get(MARKER) != 'true' for n in helpers)
    if watcher is None:
        ET.SubElement(root, 'entity', _watcher())
    for name in helpers:
        definitions[name].set('spawnscript', START_REF)
        definitions[name].set(MARKER, 'true')
    if scripts is not None:
        scripts.update(generated_scripts())
    return len(helpers) if changed else 0


def problems(root):
    expected = copy.deepcopy(root)
    try:
        changed = convert(expected)
    except ValueError as exc:
        return [str(exc)]
    return ['missing emitter lifetime watcher or helper startup'] if changed else []


def equivalent(previous, current):
    """Authenticate exactly this conversion, never a general definition waiver."""
    expected = copy.deepcopy(previous)
    try:
        changed = convert(expected)
    except ValueError:
        return False
    def canonical(e):
        return [e.tag, sorted(e.attrib.items()), [canonical(c) for c in e]]
    return bool(changed) and canonical(expected) == canonical(current)
