"""Completion-description metadata without new/reordered objectives (SPEC 47)."""


def apply_completion_text(root, group, missions):
    expected = {}
    for mission in missions.values():
        if mission.get('group_file', '').lower() != group.lower():
            continue
        for objective in mission.get('objectives', []):
            key = objective['name'].lower()
            value = objective.get('updatedescription', '')
            if key in expected and expected[key] != value:
                raise ValueError(f'{group}/{key}: conflicting completion descriptions; cannot change saved objective grouping')
            expected[key] = value
    updates = {name: value for name, value in expected.items() if value}
    elements = {e.get('name', '').lower(): e for e in root if e.tag.upper() == 'OBJECTIVE'}
    missing = updates.keys() - elements.keys()
    if missing:
        raise ValueError(f'{group}: completion-text objectives absent from generated mission: {sorted(missing)}')
    changed = 0
    for name, value in updates.items():
        if elements[name].get('updatedescription') != value:
            elements[name].set('updatedescription', value)
            changed += 1
    return changed
