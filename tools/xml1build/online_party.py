"""In-session Party screen (lc-online-party/1): authoring contract for `lc_party` and the pause-menu rename.

The companion DLL owns every runtime fact (roster, phases, clipboard, departures). This module authors the
screen, its hideable scenes and its exact command constants, and models the DLL's show/hide selection so host
fixtures and offline renders can exercise both role variants. Nothing here starts a game or a network service.
Coordinates are the approved 640 x 480 canvas; frame 06-party is 1920 x 1080 (x / 3, y / 2.25).
"""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field as dc_field

from . import online_menus as O

NAME = O.PARTY_MENU
PROBE = b'lc-online-party/1'
LINK = 'lc_party_link'                      # the renamed PDA Players row
LINK_COMMAND = 'openmenu lc_party'
LINK_TEXT = 'Party'
NATIVE_PLAYERS = 'label_option07'           # intercepted by the native PDA independently of usecmd
# Native PDA rows whose exact usecmd the rail reuses (read from the native tree at build time, never copied by hand).
RAIL_NATIVE = {'lc_rail_team': 'label_option02', 'lc_rail_options': 'label_option06', 'lc_rail_quit': 'label_option09'}
# 060q live: 'runscript codexMenu(0)' did nothing here - codexMenu (0x49e250) runs only while NO menu is open (manager
# vt+0x84 = 0x5d5170 refuses with a current menu; it is the world-trigger entry). From a menu the codex opens directly.
CODEX_COMMAND = 'openmenu codex'
RAIL = (('lc_rail_resume', 'RESUME', 103), ('lc_rail_team', 'TEAM', 132), ('lc_rail_party', 'PARTY', 160),
        ('lc_rail_codex', 'CODEX', 188), ('lc_rail_options', 'OPTIONS', 217), ('lc_rail_quit', 'QUIT GAME', 245))
ROW_Y = (157, 195, 232, 270)                # card rows, 37 units high
PHASE_TONES = {'connecting': 'warn', 'checking build': 'warn', 'in lobby': 'good', 'ready': 'good', 'waiting for next area': 'warn',
               'receiving campaign': 'warn', 'loading': 'warn', 'playing': 'good', 'watching story': 'idle', '': 'idle'}
CONFIRMS = ('lc_party_confirm_leave_host', 'lc_party_confirm_leave_guest', 'lc_party_confirm_kick')
CONFIRM_COPY = {'lc_party_confirm_leave_host': ('End for everyone?', 'Leaving ends the game for every player.'),
                'lc_party_confirm_leave_guest': ('Leave this party?', 'The game continues for the others.'),
                'lc_party_confirm_kick': ('Remove this player?', '')}
NOTICE_COPY = {'lc_party_waiting': 'is waiting for the next area', 'lc_party_receiving': 'is receiving the campaign'}
FEEDBACK_COPY = {'lc_party_copied': ('Invite code copied', 6), 'lc_party_copy_failed': ('Could not copy the invite code', 7)}
RECOVERY = ('If the host disconnects, the game ends.', 'Host again from an available local save.')
BREADCRUMB = 'Pause > Party - the game keeps running'
DATA = ('lc_room_name', 'lc_room_visibility', 'lc_room_code', 'lc_notice_name', 'lc_notice_percent', 'lc_kick_name',
        *(f'lc_p{n}_{k}' for n in range(1, 5) for k in ('name', 'slot', 'phase', 'ping', 'route')))
CARD_SCENES = ('card', 'empty', 'empty_title', 'empty_help', 'empty_plus', 'host', 'you', 'hero_fallback', 'hero_next', 'ms', 'measuring',
               'to_host', 'same_build', 'checking_build', 'other_build', 'pending', 'selected', 'tone_good', 'tone_warn', 'tone_idle')
HIDDEN_BY_DEFAULT = (*(f'lc_p{n}_{k}' for n in range(1, 5) for k in (*CARD_SCENES, 'name', 'slot', 'ping', 'kick')),
                     'lc_party_waiting', 'lc_party_receiving', 'lc_party_copied', 'lc_party_copy_failed', *CONFIRMS,
                     'lc_party_propose_soon', 'lc_party_propose_host_only', 'lc_notice_name', 'lc_notice_percent', 'lc_kick_name',
                     'lc_party_leave_yes', 'lc_party_cancel')
# Commands the screen may carry: constant integers through the guarded dispatcher, plus the native routes below.
COMMANDS = {'lc_rail_resume': 63, 'lc_party_invite': 64, 'lc_party_propose': 65, 'lc_party_leave': 66, 'lc_party_leave_yes': 67,
            'lc_rail_quit': 66, 'lc_party_cancel': 8, **{f'lc_p{n}_kick': 70 + n for n in range(1, 5)}}


def native_rail_commands(native):
    """{rail item: usecmd} from the native PDA tree; an incomplete native tree is a build error, never a guess."""
    items = {e.get('name'): e for e in native.findall('item')}
    out = {}
    for key, label in RAIL_NATIVE.items():
        cmd = (items.get(label).get('usecmd') if items.get(label) is not None else None) or ''
        if not cmd or 'lcOnlineIntent' in cmd:
            raise ValueError(f'native PDA item {label} has no usable usecmd for {key}')
        out[key] = cmd
    return out


def party_layout(role='host', *, native=None, members=4, fixture=False, notice='', confirm='', copied='', picker=0, pending=False,
                 phases=None, rtts=None, builds=None):
    """The authored lc_party scene. `native` = {rail item: usecmd}; the fixture arguments only seed preview text/visibility."""
    if role not in ('host', 'guest') or not 1 <= members <= 4: raise ValueError('invalid party preview')
    native = native or {'lc_rail_team': 'openmenu team', 'lc_rail_options': 'options', 'lc_rail_quit': 'mainmenuexit'}
    if set(native) != set(RAIL_NATIVE): raise ValueError('native rail commands incomplete')
    screen = {'name': NAME, 'items': [], 'shapes': [], 'focus': 'lc_rail_party', 'runtime': True, 'fixture_only': fixture, 'party': True}
    items, shapes = screen['items'], screen['shapes']
    entry, variant = O._entry, O._variant

    def text(key, value, rect, style='body', color=4, **kw):
        items.append(entry(key, value, rect, style, color, **kw)); return items[-1]

    def shape(kind, rect, color, **kw): shapes.append(dict(kind=kind, rect=rect, color=color, **kw))

    def scene(key, rect, parts, visible=False, **kw):
        items.append(variant(key, rect, parts, **kw)); items[-1]['hidden'] = not visible; return items[-1]

    def label(value, rect, style='label', color=3): return dict(text=value, rect=rect, style=style, color=color)
    me = 3 if role == 'guest' else 1                    # preview only: the local card
    names = ('Logan', 'Kitty', 'Alex', 'Sam')
    # ---- left rail: PAUSED title and six real rows (Resume/Team/Codex/Options/Quit are native or guarded routes)
    text('lc_party_paused', 'PAUSED', (43, 43, 200, 43), 'title')
    shape('bar', (43, 73, 62, 4), 5)
    shape('bar', (43, 147, 133, 26), 2); shape('rect', (33, 147, 5, 26), 5)    # the current page, as in the frame
    for key, word, cy in RAIL:
        cmd = native.get(key)
        e = text(key, word, (54, cy - 9, 118, 18), 'row', 4 if key == 'lc_rail_party' else 3, hit_rect=(43, cy - 13, 133, 26),
                 intent={'lc_rail_resume': 'party-resume', 'lc_rail_party': 'current', 'lc_rail_quit': 'party-leave'}.get(key, 'native:' + key))
        if key == 'lc_rail_codex': e['usecmd'] = CODEX_COMMAND
        # QUIT GAME is the Leave confirmation (intent 66): the native mainmenuexit has no confirmation of its own, so a host
        # would skip 'End for everyone'. The DLL runs the native quit after the confirmation (and at once outside a session).
        elif key == 'lc_rail_quit': e['usecmd'] = O.command(66)
        elif key in native: e['usecmd'] = native[key]
        elif key == 'lc_rail_party': e['usecmd'] = ''
    # ---- right panel: header, invite code, notice, four rows, recovery text
    shape('panel', (203, 43, 394, 353), 1); shape('rect', (203, 43, 394, 22), 2); shape('notch', (203, 43, 11, 11), 5)
    shape('outline', (542, 47, 43, 14), 3)
    text('lc_party_title', 'PARTY -', (220, 49, 54, 13), 'label', 4)
    text('lc_room_name', 'WEEKEND CO-OP' if fixture else 'Room details pending', (262, 49, 272, 13), 'label', 4, data=True)
    text('lc_room_visibility', 'PRIVATE' if fixture else 'PENDING', (546, 49, 37, 12), 'label', 3, data=True)
    text('lc_party_code_label', 'INVITE CODE', (440, 78, 140, 13), 'label', 3, align='right')
    text('lc_room_code', 'K7QN-2X9M' if fixture else '---- ----', (430, 88, 150, 24), 'title', 5, data=True, align='right')
    # Notice bar (the one joining member): one of two scenes; the DLL binds the name/percent beside them.
    for key, copy_ in NOTICE_COPY.items():
        scene(key, (221, 116, 359, 33), [dict(kind='outline', rect=(0, 0, 359, 33), color=5), dict(kind='diamond', rect=(14, 13, 7, 6), color=5),
                                         label(copy_, (112, 8, 240, 17), 'body', 4)], visible=fixture and notice == key)
    text('lc_notice_name', 'Alex' if fixture and notice else '', (245, 124, 84, 17), 'body', 4, data=True, align='right', hidden=not (fixture and notice))
    text('lc_notice_percent', '65%' if fixture and notice == 'lc_party_receiving' else '', (500, 124, 70, 17), 'body', 5, data=True, align='right',
         hidden=not (fixture and notice == 'lc_party_receiving'))
    phases = phases or ('playing', 'playing', 'waiting for next area', 'watching story')
    rtts = rtts or (None, 41, 118, 55)
    builds = builds or ('same', 'same', 'checking', 'same')
    for n in range(1, 5):
        y = ROW_Y[n - 1]; prefix = f'lc_p{n}_'; occupied = n <= members; shown = fixture and occupied
        scene(prefix + 'card', (221, y, 359, 37), [dict(kind='rect', rect=(0, 36, 359, 1), color=2)], visible=shown)
        scene(prefix + 'selected', (216, y - 1, 369, 39), [dict(kind='panel', rect=(0, 0, 369, 39), color=2, outline=5)], visible=shown and picker == n)
        scene(prefix + 'pending', (221, y, 359, 37), [dict(kind='dashed', rect=(0, 0, 359, 37), color=5)], visible=shown and pending and n == members)
        text(prefix + 'slot', f'P{n}', (205, y + 6, 16, 12), 'label', 3, data=True, hidden=not shown)
        e = text(prefix + 'name', names[n - 1] if fixture else '', (221, y + 2, 104, 20), 'title', 4, data=True, hidden=not shown)
        e['font_alias'] = 'card_name'
        scene(prefix + 'host', (328, y + 4, 31, 14), [dict(kind='outline', rect=(0, 0, 31, 14), color=5), label('HOST', (5, 1, 24, 13), 'label', 5)],
              visible=shown and n == 1)
        scene(prefix + 'you', (362, y + 5, 38, 13), [label('(you)', (0, 0, 38, 13), 'label', 3)], visible=shown and n == me)
        waiting = phases[n - 1] == 'waiting for next area'
        text(prefix + 'hero_fallback', 'Hero assigned at start', (221, y + 20, 100, 14), 'body', 3, variant=True, hidden=not shown or waiting)
        text(prefix + 'hero_next', 'Hero at the next area', (221, y + 20, 100, 14), 'body', 3, variant=True, hidden=not (shown and waiting))
        for key, word, color in (('same_build', 'SAME BUILD', 6), ('checking_build', 'CHECKING BUILD...', 3), ('other_build', 'OTHER BUILD', 7)):
            scene(prefix + key, (324, y + 21, 80, 14), [dict(kind='outline', rect=(0, 0, 80, 14), color=color), label(word, (5, 1, 73, 13), 'label', color)],
                  visible=shown and key == {'same': 'same_build', 'agreed': 'same_build', 'other': 'other_build'}.get(builds[n - 1], 'checking_build'))
        tone = PHASE_TONES.get(phases[n - 1], 'idle')
        for key, color in (('good', 6), ('warn', 5), ('idle', 3)):
            scene(f'{prefix}tone_{key}', (412, y + 9, 7, 6), [dict(kind='diamond', rect=(0, 0, 7, 6), color=color)], visible=shown and tone == key)
        text(prefix + 'phase', phases[n - 1].capitalize() if shown else '', (424, y + 4, 122, 15), 'body', 4, data=True)
        bars = [dict(kind='rect', rect=(i * 4, 9 - h, 2.5, h), color=6 if n == me else 2) for i, h in enumerate((3, 6, 9, 12))]
        ping = rtts[n - 1]
        scene(prefix + 'ms', (412, y + 19, 130, 16), [*bars, label('ms', (38, 0, 20, 16), 'body', 3)],
              visible=shown and n != me and ping is not None)
        scene(prefix + 'measuring', (412, y + 19, 130, 16), [*bars, label('Measuring', (20, 0, 90, 16), 'body', 3)],
              visible=shown and n != me and ping is None)
        text(prefix + 'ping', str(ping) if shown and ping is not None and n != me else '', (432, y + 19, 26, 16), 'body', 3, data=True, hidden=not shown)
        text(prefix + 'route', 'direct' if shown and n != me and ping is not None else '', (484, y + 19, 34, 16), 'label', 3, data=True)
        scene(prefix + 'to_host', (520, y + 21, 32, 14), [label('to host', (0, 0, 32, 14), 'label', 3)], visible=False)
        scene(prefix + 'empty', (221, y, 359, 37), [dict(kind='dashed', rect=(0, 0, 359, 37), color=3)], visible=fixture and not occupied)
        text(prefix + 'empty_title', 'Open slot', (240, y + 4, 200, 16), 'row', 3, variant=True, hidden=not (fixture and not occupied))
        text(prefix + 'empty_help', 'Share the invite code', (240, y + 20, 200, 14), 'body', 3, variant=True, hidden=not (fixture and not occupied))
        text(prefix + 'empty_plus', '+', (224, y + 4, 14, 28), 'title', 2, variant=True, hidden=not (fixture and not occupied))
        e = text(prefix + 'kick', 'KICK', (557, y + 10, 22, 16), 'label', 7, intent=f'party-kick:{n}', hit_rect=(553, y + 9, 27, 18),
                 hidden=not (shown and role == 'host' and n > 1 and n != me and not confirm))
        e['enabled'] = True
    text('lc_party_recovery_1', RECOVERY[0], (221, 317, 359, 15), 'body', 3)
    text('lc_party_recovery_2', RECOVERY[1], (221, 333, 359, 15), 'body', 3)
    # ---- action bar. Invite copies the code; Propose load stays visibly unavailable (round 14); Leave confirms inline.
    # 060q live: the field painted INVITE amber with its focus tick, so with the rail's PARTY focused two amber bars showed.
    # Every action is a steel bar in the field; amber comes only from the focus model of the focused item.
    shape('bar', (221, 351, 142, 30), 2); shape('bar', (372, 351, 116, 30), 2); shape('bar', (497, 351, 83, 30), 2)
    text('lc_party_invite', 'INVITE', (234, 358, 60, 16), 'row', 4, intent='party-invite', hit_rect=(221, 351, 142, 30))
    text('lc_party_invite_hint', 'Copy code', (294, 361, 62, 13), 'body', 3, align='right')
    e = text('lc_party_propose', 'PROPOSE LOAD...', (384, 351, 98, 16), 'row', 4, intent='party-propose', hit_rect=(372, 351, 116, 30))
    e['enabled'] = False
    text('lc_party_leave', 'LEAVE', (509, 358, 60, 16), 'row', 4, intent='party-leave', hit_rect=(497, 351, 83, 30))
    for key, word in (('lc_party_propose_soon', 'Available soon'), ('lc_party_propose_host_only', 'Host only')):
        scene(key, (384, 368, 98, 12), [label(word, (0, 0, 98, 12), 'label', 3)], visible=fixture and key.endswith('soon' if role == 'host' else 'only'))
    # ---- inline feedback and confirmations (never openmenu); buttons live inside the same panel region.
    for key, (word, color) in FEEDBACK_COPY.items():
        scene(key, (221, 316, 359, 29), [dict(kind='panel', rect=(0, 0, 359, 29), color=1), label(word, (10, 6, 330, 20), 'row', color)],
              visible=fixture and copied == key, plane=-280)
    for key, (title, body) in CONFIRM_COPY.items():
        parts = [dict(kind='panel', rect=(0, 0, 359, 35), color=1), label(title, (10, 3, 215, 16), 'row', 7)]
        if body: parts.append(label(body, (10, 20, 215, 13), 'body', 3))
        scene(key, (221, 314, 359, 35), parts, visible=fixture and confirm == key, plane=-280)
    text('lc_kick_name', 'Kitty' if fixture and confirm == 'lc_party_confirm_kick' else '', (231, 331, 215, 13), 'body', 3, data=True, plane=-300,
         hidden=not (fixture and confirm == 'lc_party_confirm_kick'))
    # ONE shared Yes (intent 67): the DLL resolves it from the confirmation that is open (Leave -> native quit, Kick -> the
    # agreed removal), so Cancel's left link always reaches it by pad and keyboard whichever confirmation is shown.
    for key, word, rect, intent in (('lc_party_leave_yes', 'Confirm', (452, 321, 58, 22), 'party-leave-yes'),
                                    ('lc_party_cancel', 'Cancel', (518, 321, 58, 22), 'dismiss')):
        on = fixture and bool(confirm)
        e = text(key, word, rect, 'body', 4, intent=intent, hidden=not on, plane=-300)
        e['enabled'] = on          # authored disabled; a fixture shows what the DLL enables with the panel
    # ---- footer: the standard five description slots, then the breadcrumb
    shape('rect', (0, 441, 640, 39), 0)
    for i, (word, x, w) in enumerate((('$MENU_ACCEPT Select', 43, 59), ('$MENU_NEXT Copy code', 106, 80), ('$MENU_BACK Resume', 189, 70))):
        text(f'desctext{i + 1}', word, (x, 454, w, 17), 'body', 4)
    for i in (3, 4): text(f'desctext{i + 1}', '', (43, 454, 1, 17))
    text('lc_party_breadcrumb', BREADCRUMB, (370, 455, 227, 15), 'label', 3, align='right')
    _graph(screen)
    return screen


def _graph(screen):
    by = {e['name']: e for e in screen['items']}

    def link(key, up=None, down=None, left=None, right=None):
        by[key].update(up=up or key, down=down or key, left=left or key, right=right or key)
    chain = [k for k, _, _ in RAIL]
    for i, key in enumerate(chain):
        link(key, up=chain[i - 1], down=chain[(i + 1) % len(chain)], right='lc_party_invite')
    link('lc_party_invite', up='lc_p4_kick', left='lc_rail_party', right='lc_party_propose')
    link('lc_party_propose', up='lc_p4_kick', left='lc_party_invite', right='lc_party_leave')
    link('lc_party_leave', up='lc_p4_kick', left='lc_party_propose')
    for n in range(1, 5):
        link(f'lc_p{n}_kick', up=f'lc_p{n - 1}_kick' if n > 1 else None, down=f'lc_p{n + 1}_kick' if n < 4 else 'lc_party_invite', left='lc_rail_party')
    link('lc_party_leave_yes', right='lc_party_cancel')
    link('lc_party_cancel', left='lc_party_leave_yes')


def party_selection(role, *, roster, local, notice=None, confirm='', picker=0, copied=''):
    """What the DLL shows for a roster (the same rules its binder uses): {scene: visible}, {text: value}, kick targets.

    roster: list of dicts name/host/phase/rtt/route/to_host/build/pending, in card order; `local` = index of this PC."""
    shown, texts, kicks = {}, {}, []
    for n in range(1, 5):
        prefix = f'lc_p{n}_'; m = roster[n - 1] if n <= len(roster) else None
        for key in CARD_SCENES: shown[prefix + key] = False
        shown[prefix + 'kick'] = False
        if m is None:
            shown[prefix + 'empty'] = shown[prefix + 'empty_title'] = shown[prefix + 'empty_help'] = shown[prefix + 'empty_plus'] = True
            continue
        shown[prefix + 'card'] = True
        shown[prefix + 'host'] = m.get('host', False); shown[prefix + 'you'] = n - 1 == local
        shown[prefix + 'pending'] = m.get('pending', False)
        shown[prefix + 'hero_next' if m.get('phase') == 'waiting for next area' else prefix + 'hero_fallback'] = True
        shown[prefix + {'same': 'same_build', 'agreed': 'same_build', 'other': 'other_build'}.get(m.get('build'), 'checking_build')] = True
        shown[prefix + 'tone_' + PHASE_TONES.get(m.get('phase', ''), 'idle')] = True
        rtt = m.get('rtt')
        if n - 1 != local:
            shown[prefix + ('ms' if rtt is not None else 'measuring')] = True
            shown[prefix + 'to_host'] = rtt is not None and m.get('to_host', False)
        texts[prefix + 'name'], texts[prefix + 'phase'] = m['name'], (m.get('phase') or '').capitalize()
        texts[prefix + 'ping'] = str(rtt) if rtt is not None and n - 1 != local else ''
        texts[prefix + 'route'] = m.get('route', '') if rtt is not None and n - 1 != local else ''
        shown[prefix + 'selected'] = picker == n
        # host only; never the local card, never the host's own card (index 0), never a member the broker has no native row for
        if role == 'host' and n - 1 != local and n > 1 and not m.get('pending') and not confirm:
            shown[prefix + 'kick'] = True; kicks.append(n)
    shown['lc_party_propose_soon'] = role == 'host'; shown['lc_party_propose_host_only'] = role != 'host'
    shown['lc_party_waiting'] = notice == 'waiting'; shown['lc_party_receiving'] = notice == 'receiving'
    for key in CONFIRMS: shown[key] = confirm == key
    for key in FEEDBACK_COPY: shown[key] = copied == key
    return shown, texts, kicks


@dataclass
class PartyFixture:
    """Deterministic H-level model of the DLL's Party intents. Departures happen at most once per roster generation."""
    role: str = 'host'
    roster: list = dc_field(default_factory=lambda: [dict(name='Logan', host=True), dict(name='Kitty'), dict(name='Alex'), dict(name='Sam')])
    local: int = 0
    generation: int = 1
    confirm: str = ''
    target: tuple = ()                 # (card, generation) chosen for a kick
    departures: list = dc_field(default_factory=list)
    resumed: int = 0
    copies: int = 0

    def dispatch(self, intent):
        if intent == 'party-resume': self.resumed += 1; self.confirm = ''
        elif intent == 'party-invite': self.copies += 1
        elif intent == 'party-propose': pass                              # unavailable until round 14: never acts
        elif intent == 'party-leave': self.confirm = 'lc_party_confirm_leave_host' if self.role == 'host' else 'lc_party_confirm_leave_guest'
        elif intent == 'party-leave-yes' and self.confirm == 'lc_party_confirm_kick': self.dispatch('party-kick-yes')   # the shared Yes
        elif intent == 'party-leave-yes' and self.confirm.startswith('lc_party_confirm_leave'):
            self.departures.append(('end' if self.role == 'host' else 'leave', self.generation)); self.confirm = ''
        elif intent.startswith('party-kick:'):
            card = int(intent.split(':')[1])
            if self.role == 'host' and not self.confirm and 2 <= card <= len(self.roster) and card - 1 != self.local and not self.roster[card - 1].get('pending'):
                self.target = (card, self.generation); self.confirm = 'lc_party_confirm_kick'
        elif intent == 'party-kick-yes' and self.confirm == 'lc_party_confirm_kick':
            card, gen = self.target
            if self.role == 'host' and gen == self.generation and card - 1 != self.local and card <= len(self.roster) and (card, gen) not in self.departures:
                self.departures.append((card, gen)); self.generation += 1; del self.roster[card - 1]
            self.confirm = ''; self.target = ()
        elif intent in ('dismiss', 'back') and self.confirm: self.confirm = ''
        return self


def party_problems(root, screen, native=None, palette_ids=None):
    """Serialized-tree contract of lc_party (probe-gated): exact commands, hidden scenes, DATA nodes, no second Back."""
    errors = O.tree_problems(root, screen, palette_ids)
    items = {e.get('name'): e for e in root.findall('item')}
    if root.get('menu_cancel') is not None or any(k.startswith('menu_') for k in root.attrib): errors.append('Back is routed by the DLL: no menu_cancel/menu_ok')
    cmds = {}
    for key, e in items.items():
        cmd = e.get('usecmd', '')
        if 'openmenu' in cmd and cmd not in ('openmenu team', CODEX_COMMAND) and not (native and cmd in native.values()): errors.append('unexpected menu route: ' + key)
        if cmd and cmd.startswith('runscript lcOnlineIntent('): cmds[key] = int(cmd[len('runscript lcOnlineIntent('):-1])
    for key, number in COMMANDS.items():
        e = items.get(key)
        if e is None: errors.append('missing party item: ' + key); continue
        if cmds.get(key) != number: errors.append(f'party command {key}: expected {number}, got {cmds.get(key)}')
    for key, number in cmds.items():
        if key not in COMMANDS: errors.append('unexpected scripted command: ' + key)
    for key in HIDDEN_BY_DEFAULT:
        e = items.get(key)
        if e is None: errors.append('missing hidden party node: ' + key)
        elif e.get('hide') != 'true': errors.append('initial visibility: ' + key)
    for key in DATA:
        e = items.get(key)
        if e is None: errors.append('missing DATA node: ' + key)
        elif e.get('clamp') != 'true' or any('gamevar' in k.lower() for k in e.attrib): errors.append('DATA binding: ' + key)
    if items.get('lc_rail_quit') is not None and items['lc_rail_quit'].get('usecmd') != O.command(66): errors.append('rail Quit must be the Leave confirmation (66)')
    for key, cmd in (native or {}).items():
        if key == 'lc_rail_quit': continue
        if items.get(key) is None or items[key].get('usecmd') != cmd: errors.append(f'rail {key} is not the native route {cmd!r}')
    if items.get('lc_rail_codex') is not None and items['lc_rail_codex'].get('usecmd') != CODEX_COMMAND: errors.append('rail Codex route')
    if items.get('lc_rail_party') is not None and items['lc_rail_party'].get('usecmd'): errors.append('the current page runs nothing')
    for key, e in items.items():
        if NATIVE_PLAYERS in key or 'lc_party_link' in key: errors.append('pause rename leaked into the Party screen: ' + key)
        if 'fixture' in (e.get('text') or '').lower(): errors.append('fixture wording: ' + key)
    for key in ('lc_party_propose',):
        if items.get(key) is not None and items[key].get('enabled') != 'false': errors.append('Propose load must be visibly unavailable (disabled)')
    for key in ('lc_party_propose_soon', 'lc_party_propose_host_only'):
        if items.get(key) is None: errors.append('missing: ' + key)
    for key, (title, body) in CONFIRM_COPY.items():
        if items.get(key) is None or items[key].get('type') != 'MENU_ITEM_MODEL': errors.append('confirmation scene: ' + key)
    for desc in (f'desctext{i}' for i in range(1, 6)):
        if root.get(desc) is None: errors.append('description slot: ' + desc)
    return errors
