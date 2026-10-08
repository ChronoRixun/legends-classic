"""Balance-only melee weapon metadata (SPEC 69.5; V40).

XML2 ignores stats.weapon. Carry the original fixed bonus and matching attack
kind for XML2 Fix without allocating fighting styles or shared talents.
"""
from __future__ import annotations

from . import balance as B, common as C

# XMen2.exe's attack and damage-type enums (0x4dc0bb / 0x4dc0e5).
ATTACK_TYPES = {'punch': 1, 'kick': 2, 'throw': 3}
DAMAGE_TYPES = {'dmg_physical': 128, 'dmg_energy': 32768, 'dmg_electricity': 131072}
FIELDS = ('xml1weaponattacktype', 'xml1weaponbonus', 'xml1weapondamagetype')
INI_KEY = 'MeleeWeapons'


def weapon_bonus(weapon, values):
    """Prototype +0x1c6: truncated minimum, not a roll or mean (0xbc2ef..0xbc30d)."""
    if not weapon or (weapon.get('category') or '').strip().lower() != 'melee':
        return None
    damage = values.resolve(weapon.get('damage', '0'))
    return int(float(damage.split()[0]))


def profile(weapon, values):
    bonus = weapon_bonus(weapon, values)
    if bonus is None:
        return {}
    attack = ATTACK_TYPES[weapon.get('attacktype', '').strip().lower()]
    damage = DAMAGE_TYPES[(weapon.get('damagetype') or 'dmg_physical').strip().lower()]
    if weapon.get('damagemod') or weapon.get('damagemods'):
        raise ValueError('melee weapon damage modifiers need an explicit conversion')
    if not 0 <= bonus <= 32000:
        raise ValueError('melee weapon bonus outside the original damage range')
    return dict(zip(FIELDS, map(str, (attack, bonus, damage))))


def apply(builder, entries, sources):
    """Attach inert attributes only to source entries armed with melee weapons."""
    if not B.enabled():
        return
    values = builder.ctx.x1_values()
    original = {e.get('name', '').lower(): e for e in sources}
    count = 0
    for st, _ in entries:
        source = original.get(st.get('name', '').lower())
        weapon = builder.x1_weapons.get((source.get('weapon') or '').lower()) if source is not None else None
        want = profile(weapon, values)
        st.attrib.update(want)
        count += bool(want)
    builder.ctx.set_count('melee_weapon_entries', count)


def ini_value(root):
    """Bounded name:type:bonus:damage-bits records, read from a build's npcstat."""
    rows = []
    for st in root.iter('stats') if root is not None else ():
        if not any(st.get(k) is not None for k in FIELDS):
            continue
        name = (st.get('name') or '').lower()
        if not name or len(name) > 63 or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_' for c in name):
            raise ValueError('melee weapon entry has an invalid name')
        attrs = [st.get(k) for k in FIELDS]
        if any(v is None or not v.isdecimal() for v in attrs):
            raise ValueError(f'{name}: incomplete melee weapon metadata')
        attack, bonus, damage = map(int, attrs)
        if attack not in ATTACK_TYPES.values() or not 0 <= bonus <= 32000 or damage not in DAMAGE_TYPES.values():
            raise ValueError(f'{name}: invalid melee weapon metadata')
        rows.append((name, f'{name}:{attack}:{bonus}:{damage}'))
    if len(rows) > 16 or len({n for n, _ in rows}) != len(rows):
        raise ValueError('too many or duplicate melee weapon entries')
    return '|'.join(row for _, row in sorted(rows))


def validate(v, ck):
    """V40: all and only source melee-armed NPCs carry exact weapon metadata."""
    on = B.enabled() or C.build_options(v.ctx.out).get(B.REPORT_KEY) == B.REPORT_ON
    values = v.ctx.x1_values()
    sources = v.x1_stats()
    expected = {name: profile(v.x1_weapons().get((source.get('weapon') or '').lower()), values)
                for name, (kind, source) in sources.items() if on and kind == 'npcstat'}
    for name, want in expected.items():
        if want and name not in v.stats()['by_name']:
            ck.error(f'{name}: melee-armed source entry missing from build')
    for name, (kind, st) in sorted(v.stats()['by_name'].items()):
        source = sources.get(name)
        weapon = v.x1_weapons().get((source[1].get('weapon') or '').lower()) if source else None
        want = profile(weapon, values) if on and kind == 'npcstat' else {}
        have = {k: st.get(k) for k in FIELDS if st.get(k) is not None}
        if have != want:
            ck.error(f'{kind}:{name}: melee weapon metadata {have!r}, expected {want!r}')
        if want:
            ck.count('melee_weapon_entries_checked')
    for ext in ('.XMLB', '.engb'):
        root = v.tree(f'Data/npcstat{ext}')
        found = {(st.get('name') or '').lower(): st for st in root.iter('stats')} if root is not None else {}
        for name in set(found) | {n for n, want in expected.items() if want}:
            have = {k: found[name].get(k) for k in FIELDS if found[name].get(k) is not None} if name in found else {}
            if have != expected.get(name, {}):
                ck.error(f'npcstat{ext}:{name}: missing or differing melee weapon metadata')
        try:
            value = ini_value(root)
        except ValueError as exc:
            ck.error(str(exc))
        else:
            ck.set(f'melee_weapon_ini_bytes{ext}', len(value))
