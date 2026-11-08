"""Conservative static audit of activation delivery to streamed physical entities.

Distance is Chebyshev (the native camera stream box), not path length. Trace data and literal
script chains back to all possible placed firing sources: a relay's editor position is not
where the camera was when a distant guard/switch activated it. Warnings are review candidates;
scripted movement/cameras and unresolved dynamic dispatch require human interpretation.
"""
from __future__ import annotations
from collections import defaultdict
import re

FIELDS = ('acttargets', 'deathtargets', 'monster_acttargets', 'monster_deathtargets', 'qacttargets')
PHYSICAL = frozenset(('physent', 'doorent', 'powertriggerent', 'affectableharment', 'inventoryent'))
SPLIT = re.compile(r'[ ,\t\r\n]+')
CALL = re.compile(r'\b(actSilent|act|setEnable|unlock|runscript|startscript|startConversation)\s*\(\s*["\']([^"\']+)["\']', re.I)


def relay_coverage(root, zone):
    """Only structurally validated generated delivery relays cover a target."""
    from . import progression_relays as PR, death_targets as DT
    covered = set()
    if not PR.problems(root, zone):
        covered.update(e.get('xml1progressiontarget', '').lower() for e in root.iter('entity')
                       if e.get(PR.MARKER) == 'poll')
    if not DT.problems(root, zone):
        covered.update(link['target'].lower() for link in DT.links(root))
    return covered - {''}


def audit(root, read_script, *, zone_script=None, extra_scripts=(), read_conversation=None, covered=(), threshold=650):
    """Return one warning per far activation edge/target placement, or unknown script origin.

    read_script(ref) returns decoded source or None; no files are read or written here. A row
    with distance=None records an unlocated script origin and makes no distance claim.
    """
    definitions = {e.get('name', '').lower(): e for e in root.iter('entity')}
    placed = defaultdict(list)
    positions = defaultdict(list)
    edges, incoming, autonomous = defaultdict(set), defaultdict(set), set()
    labels, entry_roots = {}, set()
    for group in root.findall('entinst'):
        typ = group.get('type', '').lower()
        for inst in group.findall('inst'):
            name = inst.get('name', '').lower()
            try:
                pos = tuple(float(v) for v in inst.get('pos', '0 0 0').split())
                if len(pos) != 3:
                    continue
            except ValueError:
                continue
            node = 'entity:' + name
            placed[name].append((typ, pos))
            positions[node].append((name, pos))
            labels[node] = name
    pending, scripts_seen, conversations_seen = [], set(), set()

    def edge(source, target, activates=True):
        edges[source].add(target)
        if activates:
            incoming[target].add(source)

    def script(value, source):
        if not value:
            return
        if '(' in value:
            parse(value, source)
        else:
            ref = value.replace('\\', '/').removesuffix('.py').lower()
            node = 'script:' + ref
            labels[node] = node
            edge(source, node)
            pending.append(ref)

    def parse(text, source):
        # Raven comments must not manufacture edges.
        text = '\n'.join(line.split('#', 1)[0] for line in (text or '').splitlines())
        for match in CALL.finditer(text):
            fn, target = match.groups()
            if fn.lower() in ('runscript', 'startscript'):
                script(target, source)
            elif fn.lower() == 'startconversation':
                ref = target.replace('\\', '/').lower().removeprefix('conversations/')
                node = 'conversation:' + ref
                edge(source, node)
                if read_conversation is not None and ref not in conversations_seen:
                    conversations_seen.add(ref)
                    tree = read_conversation(ref)
                    if tree is not None:
                        for element in tree.iter():
                            for key, value in element.attrib.items():
                                if 'script' in key.lower():
                                    script(value, node)
            else:
                for name in filter(None, SPLIT.split(target.strip().lower())):
                    edge(source, 'entity:' + name, fn.lower() not in ('setenable', 'unlock'))

    for name, entries in list(placed.items()):
        node = 'entity:' + name
        for typ, _ in entries:
            entity = definitions.get(typ)
            if entity is None:
                continue
            cls = entity.get('classname', '').lower()
            if (any(entity.get(k, '').lower() == 'true' for k in
                    ('actonuse', 'actontouch', 'actondamage', 'actondeath', 'actonremove', 'actonvisible')) or
                    entity.get('firstact') or cls == 'monsterspawnerent' or
                    (cls in PHYSICAL and any(entity.get(k) for k in ('deathtargets', 'deathscript')))):
                autonomous.add(node)
            for field in FIELDS:
                for target in filter(None, SPLIT.split(entity.get(field, '').strip().lower())):
                    edge(node, 'entity:' + target, cls != 'enabletargetent')
            for key, value in entity.attrib.items():
                if key.lower().endswith('script'):
                    script(value, node)
    if zone_script:
        ref = zone_script.replace('\\', '/').removesuffix('.py').lower()
        pending.append(ref)
        labels['script:' + ref] = 'script:' + ref
        entry_roots.add('script:' + ref)
    for ref in extra_scripts:
        pending.append(ref.replace('\\', '/').removesuffix('.py').removeprefix('scripts/').lower())
    while pending:
        ref = pending.pop()
        if ref in scripts_seen:
            continue
        scripts_seen.add(ref)
        parse(read_script(ref), 'script:' + ref)

    def origins(node, seen=frozenset()):
        if node in seen:
            return set()
        result = set(positions.get(node, ())) if node in autonomous or not incoming[node] else set()
        if node in entry_roots:
            result.add(('zone entry:' + node[7:], None))
        for parent in incoming[node]:
            result.update(origins(parent, seen | {node}))
        if not result and node.startswith('script:') and not incoming[node]:
            result.add((node, None))
        return result

    covered = {name.lower() for name in covered}
    rows = []
    for source in sorted(edges):
        for target_node in sorted(edges[source]):
            if not target_node.startswith('entity:'):
                continue
            target = target_node[7:]
            if target in covered:
                continue
            for typ, pos in placed.get(target, ()):
                entity = definitions.get(typ)
                if entity is None or entity.get('classname', '').lower() not in PHYSICAL or entity.get('smartent', '').lower() == 'false':
                    continue
                origin = origins(source)
                known = [(name, p) for name, p in origin if p is not None]
                distance = min((max(abs(a-b) for a,b in zip(p,pos)) for _,p in known), default=None)
                unknown = any(p is None for _,p in origin)
                if not unknown and distance is not None and distance <= threshold:
                    continue
                rows.append(dict(source=labels.get(source, source), target=target, target_type=typ,
                                 target_class=entity.get('classname'), distance=None if unknown else distance,
                                 sources=sorted(name for name,_ in origin), target_position=pos,
                                 reason='unlocated script origin' if unknown or distance is None else 'all firing sources beyond stream radius'))
    return rows
