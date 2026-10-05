"""xml1build.combat_events - how XMen2.exe resolves a style's <trigger> / <event> names and FightMove handlers, the
registered name tables (with the addresses they were read at), the table-driven XML1 -> XML2 rewrite of what the
engine would otherwise drop, and the checker V18 / V-H5 use. SPEC.md section 22.

Engine facts (XMen2.exe, PE base 0x400000; research/scripts/xml2_text.asm):

  * A style file (powerstyle, fightstyle, shared_nodes) is loaded by 0x5010b0: a fresh event list (0x1a890-byte
    object, ctor 0x4f7ea0) receives every <event> of data/shared_combat_events.xmlb (string 0x694558, loop
    0x50114d), then the style's root <event>s in document order (0x501180), then the FightMoves (0x500de0). An
    <event> is added to the list only when it resolves (0x5017c0: 0x501630 false -> 0x501700 not called).
  * A FightMove (0x4f7ef0) copies its `inherit` move's triggers (0x4f7b10), registers its own <event>s (0x4f7fcc),
    then reads each <trigger> that has a name or a tag (0x4f8074; neither -> skipped): a tag the move already
    holds updates that trigger (0x4f6a1f); otherwise the name is resolved by 0x501630 (no name -> skipped,
    0x4f6a73). A move holds at most 19 triggers (0x4f6aa7 cmp 0x13: the 20th is freed). Only "trigger" (0x691d18)
    and "event" (0x691d20) children are read - XML1's <trigger2> developer leftovers were read by neither exe.
  * 0x501630 resolves an event or trigger: a `type` attribute names the type directly (0x501673); otherwise the
    name in `inherit`, else `name`, is looked up case-insensitively (_stricmp 0x672562 in the tree walk 0x501410,
    via 0x5015c0) in the list, whose record carries the parent's type. Nothing found -> type NULL -> 0x501350
    fails -> the trigger / event is dropped without a message. Names live in 0x20-byte fields (0x5016dd strncpy,
    [0x1f] = 0): at most 31 characters.
  * 0x501350 creates the event through the factory 0x4faea0, which _stricmp-compares the type with the 70 ce_*
    names of CE_TYPES; an unknown type ends with index -1 (0x4fbcf2) -> NULL. The new event copies its parent
    (vt+0x1c; for attack events 0x4dbd10 + 0x4dce80 copy the attack data, whose +0x10 bits are the damageMods, so a
    child inherits its parent's damageMods) and then parses its own attributes and <damageMod> children (vt+0xc).
  * FightMove `handler` (0x4f6bdf "Handler") -> 0x4fd860: lookup in the table 0x789e58 filled by 0x4fd8d0 (the 68
    names of FM_HANDLERS); an unknown name falls back to the handler registered as '%default%' (0x4fd8bb:
    [0x6dc3b8] -> string 0x691a7c): the move plays its animation and triggers without the handler's logic.
  * A powerup's <affecter attribute=...> is parsed by 0x534d90 against the {name, id} table 0x6ddb18 (the 95 names
    of AFFECTERS); an unknown name gives id 0 ('none'): the affecter does nothing.

XML1 (default.xbe) resolves the same way; its data/shared_combat_events.xml defines three events XML2's lacks:
blast_ranged (ce_atk_blast), grab_throw (ce_atk_grab_throw) and grab_attack (ce_atk_grab_attack). Only
blast_ranged is named by XML1 style data (7 events in the Beast, Gambit, Jubilee, Magma, Psylocke and Storm
styles, e.g. Magma's lava_rift = power2 Lava Fissure); on XMen2.exe those events and every trigger naming them
were dropped. EVENT_REBASE re-points them at XML2's `blast` (the same ce_atk_blast type; XML2's own ps_gambit
card_impact is XML1's card_impact re-pointed exactly this way) and supplies blast_ranged's attributes `blast`
does not share where the event does not set them itself. HANDLER_RENAME maps XML1's ch_throw to XML2's
ch_pickup_throw (the XML1 and XML2 shared_nodes `pickupobjectthrow` are the same node under those two names), and
AFFECTER_RENAME XML1's atk_damage_scale (not in XMen2.exe's affecter table) to XML2's scale-type atk_damage.

Pure: no file I/O except verify_exe / derive_from_asm, which only read.
"""
from __future__ import annotations

import collections
import re
import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

# ------------------------------------------------------------------------------------------ registered names
CE_FACTORY = 0x4faea0            # type name -> event object (the 70 names below, in this order)
FM_HANDLER_REGISTRAR = 0x4fd8d0  # fills the FightMove handler table 0x789e58 (the 68 names below)
DEFAULT_HANDLER = '%default%'    # 0x4fd8bb: [0x6dc3b8] -> 0x691a7c
MOVE_TRIGGER_CAP = 19            # 0x4f6aa7 cmp dword [esi+0x11c], 0x13 (XML2 retail maximum: ps_bishop power10, 19)
EVENT_NAME_MAX = 31              # 0x5016dd strncpy(.., 0x20) + byte [0x1f] = 0
SHARED_EVENTS_REL = 'Data/shared_combat_events.XMLB'    # 0x694558 "data/shared_combat_events.xmlb"

# name -> (address of the `push <string>` in the registrar, string address). verify_exe() checks both against
# the install's XMen2.exe (the push is 68 <imm32>); derive_from_asm() re-reads them from the disassembly.
CE_TYPES = {
    'ce_trail': (0x4faf0b, 0x692f18), 'ce_effect': (0x4faf43, 0x692f0c), 'ce_effect_sound': (0x4faf78, 0x692efc),
    'ce_bolton': (0x4fafa6, 0x692ef0), 'ce_remove': (0x4fafd1, 0x692ee4), 'ce_sound': (0x4fb000, 0x692ed8),
    'ce_charsound': (0x4fb071, 0x692ec8), 'ce_footstep': (0x4fb0a0, 0x692ebc), 'ce_action': (0x4fb0d2, 0x692eb0),
    'ce_powerup': (0x4fb104, 0x692ea4), 'ce_set_chargedata': (0x4fb136, 0x692e90),
    'ce_set_constantbeamdata': (0x4fb168, 0x692e78), 'ce_xtreme': (0x4fb19a, 0x692e6c),
    'ce_atk': (0x4fb1cc, 0x692e64), 'ce_atk_self': (0x4fb1fe, 0x692e58), 'ce_atk_kick': (0x4fb230, 0x692e4c),
    'ce_atk_punch': (0x4fb262, 0x692e3c), 'ce_atk_grab': (0x4fb294, 0x692e30), 'ce_atk_throw': (0x4fb2c6, 0x692e20),
    'ce_atk_pickup': (0x4fb2f8, 0x692e10), 'ce_atk_pickup_throw': (0x4fb32a, 0x692dfc),
    'ce_atk_spawn': (0x4fb35c, 0x692dec), 'ce_atk_spawn_proj': (0x4fb38e, 0x692dd8),
    'ce_atk_spawn_relative': (0x4fb3c0, 0x692dc0), 'ce_atk_spawn_grenade': (0x4fb3f2, 0x692da8),
    'ce_spawn_minion': (0x4fb424, 0x692d98), 'ce_spawn_actor': (0x4fb456, 0x692d88),
    'ce_atk_spawn_sentry': (0x4fb488, 0x692d74), 'ce_atk_beam': (0x4fb4ba, 0x692d68),
    'ce_atk_blast': (0x4fb4ec, 0x692d58), 'ce_atk_blast_objects': (0x4fb51e, 0x692d40),
    'ce_atk_weap': (0x4fb550, 0x692d34), 'ce_atk_suspend': (0x4fb573, 0x692d24),
    'ce_atk_teleport': (0x4fb5a5, 0x692d14), 'ce_atk_teleport_strike': (0x4fb5d7, 0x692cfc),
    'ce_atk_teleport_return': (0x4fb609, 0x692ce4), 'ce_atk_post_tele_punch': (0x4fb63b, 0x692ccc),
    'ce_atk_teleport_dash': (0x4fb66d, 0x692cb4), 'ce_atk_teleport_dash_prep': (0x4fb69f, 0x692c98),
    'ce_atk_teleport_mark_start': (0x4fb6d1, 0x692c7c), 'ce_atk_move': (0x4fb703, 0x692c70),
    'ce_atk_taunt': (0x4fb735, 0x692c60), 'ce_camera_shake': (0x4fb767, 0x692c50), 'ce_slide': (0x4fb799, 0x692c44),
    'ce_victim_set': (0x4fb7cb, 0x692c34), 'ce_victim': (0x4fb7fd, 0x692c28),
    'ce_victim_release': (0x4fb82f, 0x692c14), 'ce_victim_throw': (0x4fb861, 0x692c04),
    'ce_count': (0x4fb893, 0x692bf8), 'ce_resurrect': (0x4fb8c5, 0x692be8),
    'ce_setup_ally_resurrect': (0x4fb8f7, 0x692bd0), 'ce_use': (0x4fb929, 0x692bc8),
    'ce_renderfx': (0x4fb95b, 0x692bbc), 'ce_stop_movement': (0x4fb98d, 0x692ba8),
    'ce_on_ground': (0x4fb9bf, 0x692b98), 'ce_hotspot': (0x4fb9f1, 0x692b8c),
    'ce_invulnerable': (0x4fba23, 0x692b7c), 'ce_force_visibility': (0x4fba55, 0x692b68),
    'ce_steal_skin': (0x4fba87, 0x692b58), 'ce_velocity': (0x4fbab9, 0x692b4c),
    'ce_skinsegment': (0x4fbaeb, 0x692b3c), 'ce_setskin': (0x4fbb1d, 0x692b30),
    'ce_otherevent': (0x4fbb4f, 0x692b20), 'ce_set_combat_node': (0x4fbb81, 0x692b0c),
    'ce_random_event': (0x4fbbb3, 0x692afc), 'ce_rumble': (0x4fbbe5, 0x692af0),
    'ce_remove_powerups': (0x4fbc17, 0x692adc), 'ce_filter_event': (0x4fbc49, 0x692acc),
    'ce_lightning_data': (0x4fbc7b, 0x692ab8), 'ce_heal': (0x4fbcad, 0x692ab0),
}
FM_HANDLERS = {
    'ch_idle': (0x4fd974, 0x693d60), 'ch_bored_loop': (0x4fd9b5, 0x693d50), 'ch_bored_generic': (0x4fd9f4, 0x693d3c),
    'ch_charge': (0x4fda33, 0x693d30), 'ch_guard_decide': (0x4fda72, 0x693d20), 'ch_move': (0x4fdab1, 0x693d18),
    'ch_jump': (0x4fdaf0, 0x693d10), 'ch_move_jump': (0x4fdb2f, 0x693d00), 'ch_tele_jump': (0x4fdb6e, 0x693cf0),
    'ch_jump_punch': (0x4fdbad, 0x693ce0), 'ch_jump_lift_attack': (0x4fdbec, 0x693ccc),
    'ch_dive_kick_prep': (0x4fdc2b, 0x693cb8), 'ch_dive_kick': (0x4fdc6a, 0x693ca8),
    'ch_teleport_stomp': (0x4fdca9, 0x693c94), 'ch_teleport_frenzy_dash': (0x4fdce8, 0x693c7c),
    'ch_teleport_dash_start': (0x4fdd27, 0x693c64), 'ch_move_jump_land': (0x4fdd66, 0x693c50),
    'ch_move_tele_land': (0x4fdda5, 0x693c3c), 'ch_strafe': (0x4fdde4, 0x693c30), 'ch_spin': (0x4fde23, 0x693c28),
    'ch_flying': (0x4fde62, 0x693c1c), 'ch_skating': (0x4fdea1, 0x693c10), 'ch_bounce_move': (0x4fdee0, 0x693c00),
    'ch_charge_move': (0x4fdf1f, 0x693bf0), 'ch_jump_attack': (0x4fdf5e, 0x693be0),
    'ch_fly_charge': (0x4fdf9d, 0x693bd0), 'ch_fly_move': (0x4fdfdc, 0x693bc4), 'ch_grab_hold': (0x4fe01b, 0x693bb4),
    'ch_grab_throw_ally': (0x4fe05a, 0x693ba0), 'ch_restore_visible_on_interrupt': (0x4fe099, 0x693b80),
    'ch_grab_victim': (0x4fe0d8, 0x693b70), 'ch_thrown': (0x4fe117, 0x693b64),
    'ch_thrown_land': (0x4fe156, 0x693b54), 'ch_thrown_getup': (0x4fe195, 0x693b44),
    'ch_thrown_hit_wall': (0x4fe1d4, 0x693b30), 'ch_fastball': (0x4fe213, 0x693b24),
    'ch_wall_lunge': (0x4fe252, 0x693b14), 'ch_pickup_grab': (0x4fe291, 0x693b04), 'ch_pickup': (0x4fe2d0, 0x693af8),
    'ch_pickup_idle': (0x4fe30f, 0x693ae8), 'ch_pickup_walk': (0x4fe34e, 0x693ad8),
    'ch_pickup_throw': (0x4fe38d, 0x693ac8), 'ch_popup': (0x4fe3cc, 0x693abc), 'ch_popup_land': (0x4fe40b, 0x693aac),
    'ch_air_spin': (0x4fe44a, 0x693aa0), 'ch_popup_attack': (0x4fe489, 0x693a90), 'ch_pain': (0x4fe4c8, 0x693a88),
    'ch_trip': (0x4fe507, 0x693a80), 'ch_telekinesis': (0x4fe546, 0x693a70), 'ch_lockon': (0x4fe585, 0x693a64),
    'ch_lockedon': (0x4fe5c4, 0x693a58), 'ch_constantbeam': (0x4fe603, 0x693a48),
    'ch_gambitdecide': (0x4fe640, 0x693a38), 'ch_gambitdecide2': (0x4fe667, 0x693a24),
    'ch_gambitboltons': (0x4fe68e, 0x693a10), 'ch_nightcrawlerdecide': (0x4fe6b5, 0x6939f8),
    'ch_nightcrawlerboltons': (0x4fe6dc, 0x6939e0), 'ch_ngtmovingboltons': (0x4fe703, 0x6939cc),
    'ch_block': (0x4fe72a, 0x6939c0), 'ch_wolv_frenzy': (0x4fe751, 0x6939b0), 'ch_wolv_lunge': (0x4fe778, 0x6939a0),
    'ch_wolv_lunge_attack': (0x4fe79f, 0x693988), 'ch_bishop_drain': (0x4fe7c6, 0x693978),
    'ch_magnetic_grasp': (0x4fe7ed, 0x693964), 'ch_storm_chain_lightning': (0x4fe814, 0x693948),
    'ch_toad_leap': (0x4fe83b, 0x693938), 'ch_rogue_torpedo': (0x4fe862, 0x693924),
    'ch_rogue_energy_drain_atk': (0x4fe889, 0x693908),
}
_REGISTRARS = ((CE_TYPES, CE_FACTORY, 0x4fbd33, 'ce_'), (FM_HANDLERS, FM_HANDLER_REGISTRAR, 0x4fe8a0, 'ch_'))
# <affecter attribute=...> (and a <powerup> affecter) -> id: 0x534d90 parses the name against the {char *name, int id}
# table at 0x6ddb18 (NULL-terminated, _stricmp via 0x5602f0); an unknown name gives id 0 = 'none' (the affecter does
# nothing). name (lowercase) -> (id, string address), in table order (id 54 is unused; damage / atk_damage share 57).
AFFECTER_TABLE = 0x6ddb18
AFFECTER_PARSER = 0x534d90
AFFECTERS = {
    'none': (0, 0x6850d4), 'count_only': (1, 0x696ce8), 'strength': (2, 0x684884), 'speed': (3, 0x68487c),
    'body': (4, 0x684874), 'mind': (5, 0x68486c), 'traits': (6, 0x696ce0), 'talent': (7, 0x68ebac),
    'all_talents': (8, 0x696cd4), 'move': (9, 0x6895e4), 'move_attack': (10, 0x696cc8), 'invisible': (11, 0x68744c),
    'energy_drain': (12, 0x696cb8), 'resist_physical': (13, 0x696ca8), 'resist_mental': (14, 0x696c98),
    'resist_energy': (15, 0x696c88), 'resist_radiation': (16, 0x696c74), 'resist_elemental': (17, 0x696c60),
    'resist_cold': (18, 0x696c54), 'resist_fire': (19, 0x696c48), 'resist_electricity': (20, 0x696c34),
    'resist_all': (21, 0x696c28), 'health_regen': (22, 0x696c18), 'health_regen_pct': (23, 0x696c04),
    'energy_regen': (24, 0x696bf4), 'health_per_kill': (25, 0x696be4), 'energy_per_kill': (26, 0x696bd4),
    'maxhealth': (27, 0x68d460), 'maxenergy': (28, 0x68d454), 'structure': (29, 0x689db8),
    'spend_damage': (30, 0x696bc4), 'damage_to_energy': (31, 0x696bb0), 'attack_rating': (32, 0x696ba0),
    'defense_rating': (33, 0x696b90), 'min_damage': (34, 0x696b84), 'max_damage': (35, 0x696b78),
    'damagelevel': (36, 0x696b6c), 'might_heaviness': (37, 0x696b5c), 'might_structure': (38, 0x696b4c),
    'def_damage': (39, 0x696b40), 'def_knockback': (40, 0x696b30), 'def_stun': (41, 0x696b24),
    'def_pain': (42, 0x696b18), 'def_critical': (43, 0x696b08), 'def_pickup': (44, 0x696afc),
    'def_grab': (45, 0x696af0), 'def_reflect_pain': (46, 0x696adc), 'def_finisher': (47, 0x696acc),
    'def_popup': (48, 0x696ac0), 'def_trip': (49, 0x696ab4), 'def_mind_control': (50, 0x696aa0),
    'def_defense_rating': (51, 0x696a8c), 'def_absorb_damage': (52, 0x696a78), 'def_absorb_energy': (53, 0x696a64),
    'def_dodge': (55, 0x696a58), 'def_damage_scope': (56, 0x696a44), 'damage': (57, 0x6844c8),
    'atk_damage': (57, 0x696a38), 'atk_range': (58, 0x696a2c), 'atk_range_scale': (59, 0x696a1c),
    'atk_knockback': (60, 0x696a0c), 'atk_knockback_scale': (61, 0x6969f8), 'atk_attack_rating': (62, 0x6969e4),
    'atk_critical': (63, 0x6969d4), 'atk_vampire': (64, 0x6969c8), 'atk_vampire_energy': (65, 0x6969b4),
    'reflect_damage': (66, 0x6969a4), 'deflect_damage': (67, 0x696994), 'power_cost': (68, 0x696988),
    'bypass_enemy_dr': (69, 0x696978), 'critical': (70, 0x69696c), 'drain_victim': (71, 0x69695c),
    'drain_time': (72, 0x696950), 'xp': (73, 0x689260), 'nullify': (74, 0x696948), 'jump': (75, 0x691468),
    'combo_damage': (76, 0x696938), 'combo_xp': (77, 0x69692c), 'confused': (78, 0x696920), 'fear': (79, 0x696918),
    'team_switch': (80, 0x69690c), 'no_iceshell': (81, 0x696900), 'frozen': (82, 0x693f50),
    'stun_lock': (83, 0x6968f4), 'stolen_damage': (84, 0x6968e4), 'slow_immune': (85, 0x6968d8),
    'reveal_hidden': (86, 0x6968c8), 'extra_potions': (87, 0x6968b8), 'extra_money': (88, 0x6968ac),
    'continuous': (89, 0x6968a0), 'special': (90, 0x68a144), 'powerup_scope': (91, 0x696890),
    'time_bomb': (92, 0x696884), 'dmg_custom_ent': (93, 0x696874), 'scale_factor': (94, 0x68e7d4),
}


# ------------------------------------------------------------------------------------------ the rewrite tables
@dataclass(frozen=True)
class Rebase:
    base: str                 # XML2 shared event the XML1 one is re-pointed at
    attrs: tuple              # (attribute, XML1 value) supplied where the event does not set it itself
    damagemods: tuple         # damageMods the XML1 parent carried (inherited as bits, 0x4dce80)
    why: str


# XML1 data/shared_combat_events.xml events that XML2's data/shared_combat_events.xmlb lacks: name -> XML1 type
X1_ONLY_SHARED_EVENTS = {
    'blast_ranged': 'ce_atk_blast',          # 7 events in 6 XML1 hero styles -> EVENT_REBASE
    'grab_throw': 'ce_atk_grab_throw',       # type unregistered in XMen2.exe; named by no XML1 style
    'grab_attack': 'ce_atk_grab_attack',     # type unregistered in XMen2.exe; named by no XML1 style
}
EVENT_REBASE = {
    # XML1: <event name="blast_ranged" type="ce_atk_blast" PowerAttack="true" AttackType="blast" Damage="L3"
    #        damagelevel="1" DamageType="dmg_fire" MaxRange="50" Angle="0" Radius="50"><damageMod dmgmod_popup/>
    # XML2: <event name="blast" type="ce_atk_blast" angle="0" attacktype="blast" damage="6 9" damagelevel="1"
    #        damagescale="none" maxrange="200" radius="50"/>  - same type; attacktype / angle / damagelevel /
    # radius equal; damagescale "none" is what XML2's hero blasts (Pyro / Sunfire ignite, Iceman ice pillar) use.
    # PowerAttack is no XMen2.exe attribute (only the unrelated enum string 'POWERATTACK' 0x68cf04).
    'blast_ranged': Rebase('blast', (('damage', 'L3'), ('damagetype', 'dmg_fire'), ('maxrange', '50')),
                           ('dmgmod_popup',),
                           "XML1 shared event (ce_atk_blast) XML2 lacks; XML2's own ps_gambit card_impact is XML1's "
                           "card_impact re-pointed at 'blast'"),
}
# XML1 FightMove handler -> XML2's registered handler of the same behaviour
HANDLER_RENAME = {
    'ch_throw': ('ch_pickup_throw', "XML1 shared_nodes pickupobjectthrow (ea_pickup_object_throw, trigger "
                                    "pickup_throw) is XML2's same node with handler ch_pickup_throw"),
}
# XML1 affecter / powerup attribute -> (XML2 affecter, affect_type it needs). XML1's atk_damage_scale (default.xbe
# string; XMen2.exe's table lacks it, so it parsed as 'none') multiplies attack damage; XML2 writes the same thing as
# <affecter affect_type="scale" attribute="atk_damage"> (16 retail uses, e.g. ps_bishop's handicap drain level 0.5).
# XML1 users: Jubilee's taunt boost (power3, weakens enemies to 0.75), NPC Mystique.
AFFECTER_RENAME = {
    'atk_damage_scale': ('atk_damage', 'scale'),
}
# names left unresolved on purpose: proven to do nothing in XML1 either
UNRESOLVED_ALLOWED = {
    'pickup_sound': "x1_ps_juggernaut grabstart: XML1 never defined it (no <event> of that name in XML1's "
                    "shared_combat_events.xml or ps_juggernaut, no default.xbe string), so the trigger was a no-op "
                    "in XML1 too",
}
# XML1 handlers XMen2.exe does not register and that have no XML2 counterpart: the move runs as %default%
# (animation + triggers, no handler logic). Reported (V18 warning), not rewritten.
UNREGISTERED_HANDLER_NOTES = {
    'ch_grab_attack': "Juggernaut's grab-and-pound (x1_ps_juggernaut grabattack); XML2 has no grab-attack handler "
                      "(ch_grab_hold / ch_grab_victim are the hold and the victim side)",
    'ch_weapon_semi_auto': "GRSO / flamethrower soldiers' repeat fire (ps_grso, ps_flamethrower); XML2's gunmen fire "
                           "through weapon_fire / projectile triggers with no weapon handler",
    'ch_grenade': "grenade lob (x1_ps_mystique, ps_shadowking_one); XML2 retail names the same unregistered handler "
                  "in its own moveset_grenade / moveset_stealth - the grenade flies by its trigger",
    'ch_clingwalldecide': "wall cling (moveset_acrobat); XML2 has no wall cling (ch_wall_lunge is the lunge off a wall)",
    'ch_clingwallbackflip': "wall-cling backflip (moveset_acrobat); no wall cling in XML2",
    'ch_clingwallidle': "wall-cling idle; no wall cling in XML2",
    'ch_air_grab_pickup': "flying carry (XML1 moveset_flying); XML2's moveset_flying is used and has none",
    'ch_air_grab_pickup_idle': "flying carry; XML2 has none",
    'ch_air_grab_pickup_throw': "flying carry throw; XML2 has none",
    'ch_air_grab_victim': "flying-carry victim / ally nodes (XML1 shared_nodes airgrab*, appended by zones); "
                          "reachable only from XML1's moveset_flying, which XML2's replaces",
    'ch_fly_guard_decide': "flying guard decide (XML1 moveset_flying); XML2's moveset_flying is used",
    'ch_stun': "XML1 shared_nodes stun; XML2's same-name node (no handler) wins",
    'ch_roguedecide': "Rogue's drain decide chain; heroes drops it (power slot keeps the registered drain chain)",
}
# (XML1 style stem, move, tag) of a tag-only trigger with no inherited trigger of that tag: XML1's own data bug,
# dropped by XML1 too (same 0x4f6a1f logic), so the behaviour is XML1's
ORPHAN_TAG_ALLOWED = {
    ('ps_pyro', 'power_smash', '3'): "XML1 data: firecolumn1's fire_column trigger has no tag, so power_smash's "
                                     "damage=M2 update never had a trigger to update in XML1 either",
}
IGNORED_CHILD_TAGS = ('trigger2',)     # read by neither exe (XML1 developer leftovers, moveset_sent_adv)

STYLE_PREFIXES = ('data/powerstyles/', 'data/fightstyles/')
SHARED_NODES_STEM = 'data/shared_nodes'


def is_style_rel(rel) -> bool:
    """an XML1 or <out> path of a combat style file (powerstyle, fightstyle / moveset, shared_nodes)."""
    r = str(rel).replace('\\', '/').lower().lstrip('/')
    return r.startswith(STYLE_PREFIXES) or r.rsplit('.', 1)[0] == SHARED_NODES_STEM


def _l(el):
    return {k.lower(): v for k, v in el.attrib.items()}


def _get(el, key):
    """attribute value by lowercase name (XML1 trees are lowercased by the parser, XMLB ones by the writer)."""
    for k, v in el.attrib.items():
        if k.lower() == key:
            return v
    return None


def _set(el, key, value):
    for k in list(el.attrib):
        if k.lower() == key and k != key:
            del el.attrib[k]
    el.set(key, value)


def _tag(el):
    return el.tag.lower() if isinstance(el.tag, str) else ''


# ------------------------------------------------------------------------------------------ rewrite
def rewrite_style(root) -> collections.Counter:
    """Table-driven XML1 -> XML2 rewrite of one style tree, in place (idempotent: a second call changes nothing).
    Every <event>/<trigger> whose `inherit` (or, without inherit and type, `name`) is an EVENT_REBASE key is
    re-pointed at the XML2 event and gets the XML1 parent's attributes / damageMods it does not set itself; every
    FightMove handler in HANDLER_RENAME is renamed; an AFFECTER_RENAME name in an <affecter attribute> or an XML1
    powerup trigger's `powerup` becomes the XML2 affecter (with its affect_type). Returns a Counter of change kinds
    (x1schema / schema_log)."""
    c = collections.Counter()
    if root is None:
        return c
    for el in root.iter():
        t = _tag(el)
        key = 'attribute' if t == 'affecter' else ('powerup' if t in ('trigger', 'event') else None)
        old = (_get(el, key) or '').lower() if key else ''
        if old in AFFECTER_RENAME:
            new, affect_type = AFFECTER_RENAME[old]
            _set(el, key, new)
            if affect_type and _get(el, 'affect_type') is None:
                _set(el, 'affect_type', affect_type)
            c[f'combat_affecter:{old}->{new}'] += 1
        if t in ('event', 'trigger'):
            if _get(el, 'type'):
                continue                                    # a type wins over inherit / name (0x501673)
            inh = _get(el, 'inherit')
            key = 'inherit' if inh else 'name'
            base = (inh or _get(el, 'name') or '').lower()
            rb = EVENT_REBASE.get(base)
            if rb is None or (key == 'name' and t == 'event'):
                continue                                    # an <event name=blast_ranged> would redefine it
            _set(el, key, rb.base)
            c[f'combat_event:{base}->{rb.base}'] += 1
            for k, v in rb.attrs:
                if _get(el, k) is None:
                    _set(el, k, v)
                    c[f'combat_event_attr:{k}'] += 1
            have = {(_get(d, 'name') or '').lower() for d in el if _tag(d) == 'damagemod'}
            for dm in rb.damagemods:
                if dm not in have:
                    el.append(_damage_mod(el, dm))
                    c[f'combat_event_damagemod:{dm}'] += 1
        elif t == 'fightmove':
            h = (_get(el, 'handler') or '').lower()
            if h in HANDLER_RENAME:
                _set(el, 'handler', HANDLER_RENAME[h][0])
                c[f'combat_handler:{h}->{HANDLER_RENAME[h][0]}'] += 1
    return c


def _damage_mod(parent, name):
    """a <damageMod> in the spelling the tree already uses (XML1 / XMLB both write the tag 'damageMod')."""
    tag = next((d.tag for d in parent.iter() if _tag(d) == 'damagemod'), 'damageMod')
    return ET.Element(tag, {'name': name})


# ------------------------------------------------------------------------------------------ XML1 shared values
# SPEC.md section 33. The build ships XML2's data/shared_combat_events (SPEC 4.4) and XML1 styles inherit from it by
# name (0x501630), so an XML1 event / trigger that leaves an attribute to its shared parent gets XML2's number. Every
# event of XML1's data/shared_combat_events.xml whose XML1 value differs from the shipped XML2 event's, with the XML1
# value (a code of XML1's data/values.xml, resolved like section 24) and the damageMods the XML1 parent carried
# (inherited as bits, 0x4dce80). Equal values are not listed (knockback: XML1 K1 = 40 and K2 = 120 are XML2's 40 and
# 120). Differences deliberately NOT written (section 33.2):
#   * damagescale: XML1 has no such attribute (not a default.xbe string); XMen2.exe's enum (0x44ec00 over the table
#     0x6d6dec: none 0 / normal 1 / difficulty 2) is stored by 0x4dc118 and its consumer is not traced. XML2's own
#     re-ships of XML1 NPCs (ps_sabretooth, ps_blob, ps_juggernaut punches) keep the shared punch's 'normal'.
#   * grab damagetype dmg_grab: not an XMen2.exe string (the damage-type parser 0x43bd70 has no such type).
#   * pickup_throw (XML1 sets no damage; XML2 "21 26") and throw impactdamage / throwspeed: XML1 has no number for
#     them (impactdamage / throwspeed are not default.xbe strings); writing 0 would remove the damage XMen2.exe takes
#     from these attributes.
#   * trail colour / width: cosmetic (XML2's trail names an effect).
#   * weapon_fire (XML1 L0, XML2 "2 3"): ce_atk_weap is XMen2.exe's sound class (SPEC 29); weapons.py replaces every
#     weapon_fire trigger of a gun style with the weapon's own attack.
X1_SHARED_EVENT_VALUES = {
    # event: (((attribute, XML1 value), ...), (damageMods))     the shipped XML2 value in the comment
    'punch': ((('damage', 'L1'),), ()),                 # "2 3"
    'kick': ((('damage', 'L1'),), ()),                  # "2 3"
    'teleport_punch': ((('damage', 'L1'),), ()),        # "3 5"
    'punch_heavy': ((('damage', 'L2'),), ()),           # "3 5"
    'kick_heavy': ((('damage', 'L2'),), ()),            # "3 5"
    'move_damage': ((('damage', 'L2'),), ()),           # "3 5"
    'punch_veryheavy': ((('damage', 'L3'),), ()),       # "6 9"
    'kick_veryheavy': ((('damage', 'L3'),), ()),        # "6 9"
    'beam': ((('damage', 'L4'),), ()),                  # "3 5"
    'fry': ((('damage', 'L4'),), ()),                   # "6 9"
    'suspend': ((('damage', 'L4'),), ()),               # "6 9"
    'throw': ((), ('dmgmod_auto_knockback',)),          # XML1 Damage="0" + this damageMod; XML2 has neither
}
X1_SHARED_KIND = 'x1_shared_value'      # Counter prefix (not 'combat_': combat_events_selftest T4/T5 count those)


def apply_x1_shared_values(root, values=None) -> collections.Counter:
    """SPEC 33: write XML1's value of every X1_SHARED_EVENT_VALUES attribute (and damageMod) onto each <event> /
    <trigger> of one XML1 style tree that names that shared event directly and does not set the attribute itself,
    in place and idempotent. An event of the style that inherits the shared one carries the value on to every
    trigger naming it, so only the direct child is written. Left alone: an element with a `type`; a trigger or
    inheriting event whose name resolves to an event of the style itself (a style event of the shared name shadows
    it, combat_events.resolve looks the style up first); an <event name=X> without inherit (a redefinition); a tag
    update of an inherited trigger (0x4f6a1f re-parses only its own attributes onto the inherited copy, which carries
    the value already). values: heroes.Values of XML1's data/values.xml (code -> XML1's number(s), as
    npc_values.resolve_style); None writes the code itself. Returns a Counter {'x1_shared_value:<event>.<attr>': n}.
    Run after rewrite_style (whose re-pointed names are XML2's)."""
    c = collections.Counter()
    if root is None:
        return c
    local = {(_get(e, 'name') or '').lower() for e in root.iter() if _tag(e) == 'event' and _get(e, 'name')}
    moves = style_moves(root)
    todo = [(e, None) for e in root.iter() if _tag(e) == 'event']
    todo += [(t, m) for m in root.iter() if _tag(m) == 'fightmove' for t in m if _tag(t) == 'trigger']
    for el, move in todo:
        if _get(el, 'type'):
            continue
        inh = (_get(el, 'inherit') or '').lower()
        nm = (_get(el, 'name') or '').lower()
        base = inh or nm
        if base not in X1_SHARED_EVENT_VALUES:
            continue
        if _tag(el) == 'event' and not inh:
            continue                                    # <event name=punch> without inherit: a redefinition
        if base in local and not (_tag(el) == 'event' and nm == base):
            continue                                    # resolves to the style's own event of that name
        if move is not None and not inh and _get(el, 'tag') is not None and \
                inherited_trigger(moves, move, _get(el, 'tag')) is not None:
            continue                                    # tag update of an inherited trigger
        attrs, mods = X1_SHARED_EVENT_VALUES[base]
        for k, code in attrs:
            if _get(el, k) is not None:
                continue
            _set(el, k, values.resolve(code) if values is not None else code)
            c[f'{X1_SHARED_KIND}:{base}.{k}'] += 1
        have = {(_get(d, 'name') or '').lower() for d in el if _tag(d) == 'damagemod'}
        for dm in mods:
            if dm not in have:
                el.append(_damage_mod(el, dm))
                c[f'{X1_SHARED_KIND}:{base}.{dm}'] += 1
    return c


# ------------------------------------------------------------------------------------------ resolution
def style_moves(root):
    """{lower FightMove name: element} of one style tree (first definition wins, as XMen2.exe's lookup)."""
    moves = {}
    if root is None:
        return moves
    for top in (list(root) if root.tag == 'xmlb_multiple_roots' else [root]):
        for m in top:
            if _tag(m) == 'fightmove' and _get(m, 'name'):
                moves.setdefault(_get(m, 'name').lower(), m)
    return moves


def inherited_trigger(moves, move, tag):
    """the trigger a tag-only <trigger tag=N .../> of `move` updates (0x4f6a1f): the nearest named trigger with that
    tag up `move`'s inherit chain (moves: style_moves), or None."""
    seen = set()
    m = moves.get((_get(move, 'inherit') or '').lower())
    while m is not None and id(m) not in seen:
        seen.add(id(m))
        for t in m:
            if _tag(t) == 'trigger' and _get(t, 'tag') == tag and _get(t, 'name'):
                return t
        m = moves.get((_get(m, 'inherit') or '').lower())
    return None


# XML1 powerup terms XMen2.exe reads only on an <affecter> (0x534d90), never on the trigger: a tag-only update of an
# inherited powerup trigger that carries one of them (or a scope_*) changes nothing on XMen2.exe (SPEC 22.7 / 24)
UPDATE_AFFECTER_ATTRS = ('level', 'affect_type', 'level_max')
NEW_TAG_BASE = 100               # heroes._npc_powerup_updates: first tag of a replacement powerup trigger


def x1_powerup_update_terms(t, moves, move):
    """{attr: value} of the affecter terms a tag-only update of an inherited powerup trigger carries ({} when `t`
    is no such update)."""
    if _tag(t) != 'trigger' or _get(t, 'name') or _get(t, 'tag') is None or \
            (_get(t, 'remove') or '').strip().lower() == 'true':
        return {}
    terms = {k.lower(): v for k, v in t.attrib.items() if k.lower() in UPDATE_AFFECTER_ATTRS
             or k.lower().startswith('scope_')}
    if not terms:
        return {}
    p = inherited_trigger(moves, move, _get(t, 'tag'))
    return terms if p is not None and (_get(p, 'name') or '').lower() == 'powerup' else {}


def is_x1_powerup_remove(t, moves, move):
    """XML1's removal form (default.xbe remove flag, 0x95bd3; XMen2.exe reads remove_tag instead, 0x4e7e79): a
    trigger with remove="true" that is a powerup trigger or a tag-only update of an inherited powerup trigger."""
    if _tag(t) != 'trigger' or (_get(t, 'remove') or '').strip().lower() != 'true':
        return False
    name = (_get(t, 'name') or '').lower()
    if name == 'powerup':
        return True
    if name or _get(t, 'tag') is None:
        return False
    p = inherited_trigger(moves, move, _get(t, 'tag'))
    return p is not None and (_get(p, 'name') or '').lower() == 'powerup'


def event_table(shared_root):
    """the shared events of data/shared_combat_events in document order, each resolved as the loader does:
    {lower name: (type or None, attrs)} (an unresolved shared event is not added, 0x5017c0)."""
    table = {}
    if shared_root is None:
        return table
    for e in shared_root.iter():
        if _tag(e) != 'event':
            continue
        a = _l(e)
        typ, _ = resolve(a, table)
        if typ is not None and a.get('name'):
            table[a['name'].lower()] = (typ, a)
    return table


def resolve(attrs, *tables):
    """0x501630 on one lowercase attribute dict: (registered type or None, chain of names looked up).
    tables: {lower name: (type, attrs)} searched in order (the style's list = shared + root events)."""
    typ = attrs.get('type')
    if typ:
        t = typ.lower()
        return (t if t in CE_TYPES else None), [f'type:{t}']
    base = (attrs.get('inherit') or attrs.get('name') or '').lower()
    if not base:
        return None, ['<no name>']
    for table in tables:
        if base in table:
            t = table[base][0]
            return t, [base]
    return None, [f'{base}?']


@dataclass
class Finding:
    kind: str       # unresolved | handler | affecter | trigger_cap | name_len | orphan_tag | ignored_tag |
                    # x1_powerup_form | x1_powerup_remove | x1_powerup_update
    move: str
    name: str
    detail: str

    def text(self, style=''):
        return f'{style}{":" if style else ""}{self.move} {self.kind} {self.name}: {self.detail}'


def style_findings(root, shared):
    """Everything XMen2.exe would drop or run without logic in one style tree (0x5010b0 semantics).
    shared: event_table() of the <out> data/shared_combat_events. Returns [Finding]."""
    out = []
    if root is None:
        return out
    roots = list(root) if root.tag == 'xmlb_multiple_roots' else [root]
    local = {}
    moves = {}
    for top in roots:
        for e in top:
            t = _tag(e)
            if t == 'event':
                a = _l(e)
                typ, chain = resolve(a, local, shared)
                nm = (a.get('name') or '').lower()
                if typ is None:
                    out.append(Finding('unresolved', '<style>', nm, _chain_text(a, chain)))
                elif nm:
                    local[nm] = (typ, a)
                if len(nm) > EVENT_NAME_MAX:
                    out.append(Finding('name_len', '<style>', nm, f'{len(nm)} chars > {EVENT_NAME_MAX}'))
            elif t == 'fightmove':
                nm = _get(e, 'name') or ''
                moves.setdefault(nm.lower(), e)
    eff = {}                                    # move -> [trigger tags] after inheritance (for cap / tag updates)

    def effective(nm, seen=()):
        if nm in eff:
            return eff[nm]
        m = moves.get(nm)
        if m is None or nm in seen:
            return None
        inh = (_get(m, 'inherit') or '').lower()
        parent = effective(inh, seen + (nm,)) if inh else []
        tags = list(parent or [])
        mev = dict(local)
        for e in m:
            if _tag(e) == 'event':
                a = _l(e)
                typ, chain = resolve(a, mev, shared)
                if typ is not None and a.get('name'):
                    mev[a['name'].lower()] = (typ, a)
        for tr in m:
            if _tag(tr) != 'trigger':
                continue
            a = _l(tr)
            tag, name = a.get('tag'), a.get('name')
            if tag is not None and tag in tags:
                continue                            # updates the inherited trigger (0x4f6a1f)
            if not name:
                continue
            typ, _ = resolve(a, mev, shared)
            if typ is not None:
                tags.append(tag if tag is not None else object())
        eff[nm] = tags
        return tags

    for nm, m in moves.items():
        mname = _get(m, 'name') or '?'
        inh = (_get(m, 'inherit') or '').lower()
        parent = effective(inh) if inh else []
        ptags = set(t for t in (parent or []) if isinstance(t, str))
        mev = dict(local)
        for e in m.iter():
            t = _tag(e)
            if t in IGNORED_CHILD_TAGS:
                out.append(Finding('ignored_tag', mname, _get(e, 'name') or '', f'<{e.tag}> is read by neither exe'))
        for e in m:
            if _tag(e) != 'event':
                continue
            a = _l(e)
            typ, chain = resolve(a, mev, shared)
            en = (a.get('name') or '').lower()
            if typ is None:
                out.append(Finding('unresolved', mname, en, _chain_text(a, chain)))
            elif en:
                mev[en] = (typ, a)
            if len(en) > EVENT_NAME_MAX:
                out.append(Finding('name_len', mname, en, f'{len(en)} chars > {EVENT_NAME_MAX}'))
        for tr in m:
            if _tag(tr) != 'trigger':
                continue
            a = _l(tr)
            tag, name = a.get('tag'), a.get('name')
            if tag is not None and tag in ptags:
                continue
            if not name:
                if tag is not None and inh and parent is None:
                    continue                        # parent move outside this file: cannot judge the tag
                out.append(Finding('orphan_tag' if tag is not None else 'unresolved', mname, f'tag={tag}',
                                   'a trigger without a name updates an inherited tag only; none to update'
                                   if tag is not None else 'a trigger with neither name nor tag is skipped (0x4f8074)'))
                continue
            typ, chain = resolve(a, mev, shared)
            if typ is None:
                out.append(Finding('unresolved', mname, name.lower(), _chain_text(a, chain)))
            if len(name) > EVENT_NAME_MAX:
                out.append(Finding('name_len', mname, name.lower(), f'{len(name)} chars > {EVENT_NAME_MAX}'))
        n = len(effective(nm) or [])
        if n > MOVE_TRIGGER_CAP:
            out.append(Finding('trigger_cap', mname, str(n), f'{n} triggers > {MOVE_TRIGGER_CAP} (0x4f6aa7: the rest '
                                                              f'are freed)'))
        h = (_get(m, 'handler') or '').lower()
        if h and h not in FM_HANDLERS:
            out.append(Finding('handler', mname, h, UNREGISTERED_HANDLER_NOTES.get(h, 'UNDOCUMENTED')))
        for tr in m:
            if is_x1_powerup_remove(tr, moves, m):
                out.append(Finding('x1_powerup_remove', mname, f'tag={_get(tr, "tag")}',
                                   'XML1 remove="true" powerup trigger: XMen2.exe never reads remove (it removes by '
                                   'remove_tag, 0x4e7e79), so the trigger applies the powerup instead'))
            terms = x1_powerup_update_terms(tr, moves, m)
            if terms:
                out.append(Finding('x1_powerup_update', mname, f'tag={_get(tr, "tag")}',
                                   f'XML1 update {terms} of an inherited powerup trigger: XMen2.exe reads these only '
                                   f'on an <affecter> (0x534d90), so the update changes nothing'))
    for top in roots:
        for e in top:
            where = (_get(e, 'name') or '?') if _tag(e) == 'fightmove' else '<style>'
            for x in e.iter():
                if _tag(x) == 'affecter':
                    at = (_get(x, 'attribute') or '').lower()
                    if at not in AFFECTERS:
                        out.append(Finding('affecter', where, at, f'not in the affecter table 0x{AFFECTER_TABLE:x} '
                                                                  f'(0x{AFFECTER_PARSER:x}: parses as none)'))
                elif _tag(x) in ('trigger', 'event') and _get(x, 'powerup'):
                    out.append(Finding('x1_powerup_form', where, (_get(x, 'powerup') or '').lower(),
                                       'XML1-form powerup trigger (powerup= attribute): XMen2.exe builds the buff '
                                       'only from <affecter> children (0x53df10), so it does nothing'))
    return out


def _chain_text(a, chain):
    how = 'type' if a.get('type') else ('inherit' if a.get('inherit') else 'name')
    return f'{how} {" > ".join(chain)} does not resolve to a registered ce_* type (0x501630 -> dropped)'


# ------------------------------------------------------------------------------------------ exe tables
def _pe_sections(data):
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    if data[pe:pe + 4] != b'PE\0\0':
        raise ValueError('not a PE file')
    nsec = struct.unpack_from('<H', data, pe + 6)[0]
    opt = struct.unpack_from('<H', data, pe + 20)[0]
    base = struct.unpack_from('<I', data, pe + 24 + 28)[0]
    secs = []
    for i in range(nsec):
        o = pe + 24 + opt + 40 * i
        vsize, va, rsize, roff = struct.unpack_from('<IIII', data, o + 8)
        secs.append((va, max(vsize, rsize), roff, rsize))
    return base, secs


def _read_va(data, base, secs, va, n):
    rva = va - base
    for sva, size, roff, rsize in secs:
        if sva <= rva < sva + size:
            off = roff + rva - sva
            if rva - sva + n > rsize:
                return None
            return data[off:off + n]
    return None


def verify_exe(exe_path):
    """check every CE_TYPES / FM_HANDLERS entry against XMen2.exe (the registrar pushes the string's address, 68
    <imm32>, at the recorded address and the string there is the name), every AFFECTERS row of the table 0x6ddb18
    ({string address, id}, NULL-terminated) and the %default% pointer. Returns mismatch strings."""
    data = Path(exe_path).read_bytes()
    base, secs = _pe_sections(data)
    bad = []
    for table, *_ in _REGISTRARS:
        for name, (push, sva) in table.items():
            ins = _read_va(data, base, secs, push, 5)
            if ins != b'\x68' + struct.pack('<I', sva):
                bad.append(f'{name}: no push 0x{sva:06x} at 0x{push:06x}')
                continue
            s = _read_va(data, base, secs, sva, len(name) + 1)
            if s != name.encode() + b'\0':
                bad.append(f'{name}: string at 0x{sva:06x} is {s!r}')
    for k, (name, (ident, sva)) in enumerate(AFFECTERS.items()):
        row = _read_va(data, base, secs, AFFECTER_TABLE + 8 * k, 8)
        if row != struct.pack('<II', sva, ident):
            bad.append(f'affecter {name}: row {k} at 0x{AFFECTER_TABLE + 8 * k:06x} is not (0x{sva:06x}, {ident})')
            continue
        s = _read_va(data, base, secs, sva, len(name) + 1)
        if s is None or s.lower() != name.encode() + b'\0':
            bad.append(f'affecter {name}: string at 0x{sva:06x} is {s!r}')
    end = _read_va(data, base, secs, AFFECTER_TABLE + 8 * len(AFFECTERS), 4)
    if end != b'\0\0\0\0':
        bad.append(f'affecter table 0x{AFFECTER_TABLE:x} has more than {len(AFFECTERS)} rows')
    s = _read_va(data, base, secs, 0x6dc3b8, 4)
    if s is None or _read_va(data, base, secs, struct.unpack('<I', s)[0], 10) != DEFAULT_HANDLER.encode() + b'\0':
        bad.append('default handler pointer 0x6dc3b8 does not name %default%')
    return bad


def derive_from_asm(asm_path):
    """re-read both tables from the disassembly listing (research/scripts/xml2_text.asm): {prefix: {name: (push,
    str)}} with the first push of each name inside each registrar function."""
    out = {'ce_': {}, 'ch_': {}}
    pat = re.compile(r'^([0-9a-f]{8}) push (0x[0-9a-f]+) ; "((?:ce|ch)_[a-z0-9_]+)"')
    ranges = [(start, end, prefix) for _t, start, end, prefix in _REGISTRARS]
    with open(asm_path, encoding='latin-1') as f:
        for line in f:
            if ' push 0x6' not in line:
                continue
            m = pat.match(line)
            if not m:
                continue
            va = int(m.group(1), 16)
            for start, end, prefix in ranges:
                if start <= va <= end and m.group(3).startswith(prefix):
                    out[prefix].setdefault(m.group(3), (va, int(m.group(2), 16)))
    return out


# ------------------------------------------------------------------------------------------ validator V18
def _stem(rel):
    return str(rel).replace('\\', '/').rsplit('/', 1)[-1].rsplit('.', 1)[0].lower()


def allowed(stem, f):
    """reason a finding is allowlisted (proven harmless / XML1's own behaviour), else None."""
    x1 = stem[3:] if stem.startswith('x1_') else stem
    if f.kind == 'unresolved' and f.name in UNRESOLVED_ALLOWED:
        return UNRESOLVED_ALLOWED[f.name]
    if f.kind == 'orphan_tag':
        return ORPHAN_TAG_ALLOWED.get((x1, f.move.lower(), f.name[len('tag='):]))
    return None


def style_rels(index):
    """<out> style files: Data/powerstyles/*, Data/fightstyles/*, Data/shared_nodes (XMLB and engb)."""
    rels = [a for pre in ('data/powerstyles/', 'data/fightstyles/') for a in index.under(pre)]
    rels += index.find_all('data/shared_nodes', ('.XMLB', '.engb'))
    return sorted({a for a in rels if a.lower().endswith(('.xmlb', '.engb'))}, key=str.lower)


def v18(v, ck):
    """V18 combat events (SPEC 22): the registered tables match the install's XMen2.exe; in every style file the
    build wrote, every <event> / <trigger> resolves to a registered ce_* type (0x501630), no tag-only trigger lacks
    an inherited trigger to update, no move exceeds 19 triggers, names <= 31 chars, every <affecter attribute> is in
    the affecter table 0x6ddb18, every FightMove handler is registered (unregistered + assessed in
    UNREGISTERED_HANDLER_NOTES: warning; not assessed: error). An XML1-form powerup trigger (powerup= attribute) or
    XML1 removal (remove="true") is an error: heroes.convert_npc_powerups / convert_powerup_trigger convert every one
    (SPEC 22.7). XML2 retail style files (base copies) are allowlisted per file."""
    ctx = v.ctx
    exe = Path(ctx.base) / 'XMen2.exe'
    if not exe.exists():
        exe = v.idx.path('XMen2.exe')
    if exe is None or not Path(exe).exists():
        ck.error('XMen2.exe not found in the base install or <out>: registered tables unverified')
    else:
        for b in verify_exe(exe):
            ck.error(f'XMen2.exe does not match combat_events tables: {b}')
    ck.set('ce_types_registered', len(CE_TYPES))
    ck.set('fm_handlers_registered', len(FM_HANDLERS))
    shared = event_table(v.tree(SHARED_EVENTS_REL))
    ck.set('shared_events', len(shared))
    if not shared:
        ck.error(f'{SHARED_EVENTS_REL} missing or empty in <out> (every style resolves against it, 0x50111e)')
        return
    for name in X1_ONLY_SHARED_EVENTS:
        if name in shared:
            ck.note(f'{SHARED_EVENTS_REL} defines XML1-only event {name}')
    handlers = collections.defaultdict(set)
    retail = collections.Counter()
    x1_powerups = collections.Counter()
    seen = set()
    for rel in style_rels(v.idx):
        root = v.tree(rel)
        if root is None:
            continue                                     # V3 reports undecodable registered files
        stem = _stem(rel)
        ours = v.entry(rel) is not None
        ck.count('style_files_checked')
        ck.count('style_files_built' if ours else 'style_files_retail')
        for f in style_findings(root, shared):
            if not ours:
                retail[(stem, f.kind)] += 1
                continue
            key = (stem, f.kind, f.move, f.name)
            if key in seen:
                continue                                 # the XMLB / engb twin
            seen.add(key)
            ck.count(f'findings_{f.kind}')
            why = allowed(stem, f)
            if f.kind == 'handler':
                handlers[f.name].add(f'{stem}:{f.move}')
            elif why:
                ck.allow(f.text(stem), why)
            elif f.kind == 'ignored_tag':
                ck.note(f.text(stem))
            elif f.kind in ('x1_powerup_form', 'x1_powerup_remove', 'x1_powerup_update'):
                x1_powerups[stem] += 1
                ck.error(f'{f.text(stem)} (heroes.convert_npc_powerups converts it, SPEC 22.7)')
            else:
                ck.error(f.text(stem))
    for h, where in sorted(handlers.items()):
        note = UNREGISTERED_HANDLER_NOTES.get(h)
        eg = sorted(where)[:5]
        if note is None:
            ck.error(f'FightMove handler {h} is not registered in XMen2.exe (runs as {DEFAULT_HANDLER}, 0x4fd860) and '
                     f'is not assessed in combat_events.UNREGISTERED_HANDLER_NOTES: {len(where)} moves, e.g. {eg}')
        else:
            ck.warn(f'FightMove handler {h} runs as {DEFAULT_HANDLER} (not registered, 0x4fd860; no XML2 '
                    f'counterpart): {note}; {len(where)} moves, e.g. {eg}')
    ck.set('x1_powerup_form_triggers', sum(x1_powerups.values()))
    if x1_powerups:
        ck.note(f'XML1-form powerup triggers / removals left per style: {dict(sorted(x1_powerups.items()))}')
    for (stem, kind), n in sorted(retail.items()):
        ck.allow(f'{stem}: {n} {kind} finding(s)', 'XML2 retail style file, unchanged (XMen2.exe ships it so)')
    ck.details['unregistered_handlers'] = {h: sorted(w) for h, w in sorted(handlers.items())}
