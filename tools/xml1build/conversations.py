"""SPEC 34: XML1's `runWithoutUser` conversation lines through xml2-fix [Game] AutoAdvance (2026-10-01, audit W1).

XML1's conversations flag lines (and whole startConditions, and single %BLANK% responses) `runWithoutUser="true"`:
the tour and the walk-and-talk lines, the cutscene chains - 151 conversations wholly, 51 more in part. XMen2.exe never
reads the attribute (no such string in the exe; the line parser 0x458820 / 0x459860 looks for it nowhere), so on the
XML2 engine every one of those lines sat until the player pressed accept (seen in game, audit W1). The engine does
parse `timeDelay` (0x458b68: atof into the line's +0x80, 0.5 when absent) and then never uses it (its only other use
is a copy into the conversation system's +0x239a8 at display, which nothing reads).

The builder writes the flag INTO that number: a line that should run without the user gets a NEGATIVE `timeDelay`,
and xml2-fix 1.3.0's conversation hook (conversations_rules.hpp in the xml2-fix repository) reads it at the game's
accept check: the sign marks the line, the magnitude is how long to show it when there is no voice to wait for (the
hook waits for the line's voice to play and end when there is one; with no voice, or a voice the sound system never
started, it waits |timeDelay| seconds). The hook picks only when exactly one reply is visible - a menu is never
picked for the player - and only outside the engine's own first-second accept lock-out. Retail data has no negative
timeDelay (XML1: 6 lines and 6 responses at 2 or 3; XML2: 2 and 2), and without the fix the number is as inert as
it always was. Idempotent: a line already marked is left alone (scripts_selftest runs rewrite_data_tree twice).

Which lines: the line itself flagged, or its enclosing startCondition flagged (every line of that tree), or its one
and only response flagged (XML1 flags the %BLANK% response under a flagged line, and 11 times the response alone).
Responses are not marked: the engine's pending-reply step has its own fix (xml2-fix ReplyVoices).

How long: an existing positive `timeDelay` on the line (XML1's own 2 / 3) is kept as the magnitude; otherwise a reading
time from the text after its %SPEAKER% token: BASE_SECONDS + PER_CHAR per character, clamped to MIN..MAX_SECONDS.
"""
import copy
import re
import xml.etree.ElementTree as ET

AUTO_ATTR = 'timeDelay'          # the engine's own attribute name (its lookup is case-insensitive)
RWU_ATTR = 'runwithoutuser'      # XML1's flag, compared in lower case
MIN_SECONDS, MAX_SECONDS = 2.0, 12.0
BASE_SECONDS, PER_CHAR = 1.0, 0.06   # ~17 characters a second of reading, plus a second
_TOKEN = re.compile(r'^\s*%[^%]*%:?\s*')


def _true(el, attr):
    """attribute `attr` (any case) of `el` is 'true' (any case)."""
    return any(k.lower() == attr and (v or '').strip().lower() == 'true' for k, v in el.attrib.items())


def _attr(el, attr):
    """(key, value) of attribute `attr` (any case), or (None, None)."""
    for k, v in el.attrib.items():
        if k.lower() == attr.lower():
            return k, v
    return None, None


def _children(el, tag):
    return [c for c in el if isinstance(c.tag, str) and c.tag.lower() == tag]


# These tokens do not select a named stats entry. The activator's head is supplied
# by its own character package; end/blank/control tokens require no portrait.
PORTRAIT_BUILTINS = frozenset({'player', 'x-team', 'null', 'end', 'more', 'continue', 'blank'})


def speaker_keys(root):
    """Named speakers in final line/response text, including the engine's offset-four form.

    Read transformed trees (including copied tagjump subtrees), not source aliases.
    A percent token later in dialogue is not a speaker selector.
    """
    speakers = set()
    for el in root.iter():
        if not isinstance(el.tag, str) or el.tag.lower() not in ('line', 'response'):
            continue
        for attr, value in el.attrib.items():
            if attr.lower() not in ('text', 'textb'):
                continue
            text = value or ''
            match = re.match(r'%([^%]+)%', text)
            if match is None:
                match = re.match(r'%([^%]+)%', text[4:])
            if match and match[1].lower() not in PORTRAIT_BUILTINS:
                speakers.add(match[1].lower())
    return sorted(speakers)


def portrait_requirements(root, stats):
    """speaker -> final baseline HUD head, or None for a missing stats/skin.

    An unloaded speaker uses its exact stats skin. Do not invent a costume-01
    fallback or remap an already converted skin. A loaded hero can fall back to
    this default through the engine's existing current/default costume lookup.
    """
    result = {}
    for speaker in speaker_keys(root):
        entry = stats.get(speaker)
        skin = _attr(entry, 'skin')[1] if entry is not None else None
        result[speaker] = 'hud/hud_head_' + skin.lower() if skin else None
    return result


def reading_seconds(text):
    """how long a line with no voice stays up: its text after the %SPEAKER% token, at the reading rate."""
    chars = len(_TOKEN.sub('', text or '').strip())
    return min(MAX_SECONDS, max(MIN_SECONDS, round(BASE_SECONDS + PER_CHAR * chars, 1)))


def _delay_value(raw):
    try:
        return float((raw or '').strip())
    except ValueError:
        return None


def auto_lines(root):
    """[(line element, why)] of every <line> that should advance by itself: 'startcondition' (its tree is
    flagged), 'line' (the line is), 'response' (its only response is)."""
    out = []
    for sc in root.iter():
        if not isinstance(sc.tag, str) or sc.tag.lower() != 'startcondition':
            continue
        sc_flag = _true(sc, RWU_ATTR)
        for line in sc.iter():
            if not isinstance(line.tag, str) or line.tag.lower() != 'line':
                continue
            responses = _children(line, 'response')
            if sc_flag:
                out.append((line, 'startcondition'))
            elif _true(line, RWU_ATTR):
                out.append((line, 'line'))
            elif len(responses) == 1 and _true(responses[0], RWU_ATTR):
                out.append((line, 'response'))
    return out


def mark_line(line):
    """the line's timeDelay made negative (the magnitude from an existing positive value, else the reading time);
    returns True when the attribute changed."""
    key, raw = _attr(line, AUTO_ATTR)
    current = _delay_value(raw)
    if current is not None and current < 0:
        return False                                      # marked already (a second pass)
    seconds = current if current is not None and current >= 0.5 else reading_seconds(line.get('text') or '')
    if key is not None and key != AUTO_ATTR:
        del line.attrib[key]
    line.set(AUTO_ATTR, f'-{seconds:g}')
    return True


def mark_auto_advance(root):
    """every auto line of the conversation tree `root` marked in place; returns the number of lines changed."""
    if root is None:
        return 0
    return sum(1 for line, _why in auto_lines(root) if mark_line(line))


def marked_lines(root):
    """[line] whose timeDelay is negative (what the fix will advance by itself)."""
    out = []
    for line in root.iter():
        if isinstance(line.tag, str) and line.tag.lower() == 'line':
            v = _delay_value(_attr(line, AUTO_ATTR)[1])
            if v is not None and v < 0:
                out.append(line)
    return out


# ---------------------------------------------------------------------------------------------- SPEC 39: cross-file tagjumps
# XML1 resolved a response's tagJump across every loaded conversation file; XMen2.exe looks only in the file the
# response lives in (0x45cde0 -> 0x4573f0, case-sensitive; conversation-speakers.md section 4 step 9). Of the 365
# XML1 tagjumps exactly one leaves its file (audit W11, issue #9): mansion/man4/2_5_10b's last response jumps to
# 2_5_10loop, the reply menu that lives in mansion/man4/2_5_10. The lookup fails, the childless %BLANK% response
# sets the ending flag, and Xavier's introduction of Emma ends before the menu. Fix: deep-copy the tagged line and
# its subtree out of the owning conversation into a NEW participant of the jumping startCondition (all 80+1 known
# tagIndexes sit on participant root lines - a second root line of the default participant was tried in game and the
# engine never registered it), so the local lookup finds it. Entry selection (activator name -> 'default') and the
# runOnce startCondition pick are untouched. resolve_cross_file_tagjumps runs before mark_auto_advance and the
# attribute pass (scripts.rewrite_data_tree), so the copy is patched exactly like the rest of the file. The jumping
# response's conversationEnd is also removed: XMen2.exe ends the conversation on that flag even when the tagJump
# resolves, and the copied menu ends at its own %END%. Idempotent: a file that already carries the tagIndex is left
# alone.
CROSS_FILE_TAGJUMPS = {
    'mansion/man4/2_5_10b': (('2_5_10loop', 'mansion/man4/2_5_10'),),
}


def _local_tagindex(root, tag):
    return any(isinstance(el.tag, str) and _attr(el, 'tagindex')[1] == tag for el in root.iter())


def _enclosing(root, el, tag):
    """the ancestor of el whose tag is `tag` - the lookup only needs the line somewhere in-file; placement keeps
    the file's shape (no change to the default participant's root line or to entry selection)."""
    for p in root.iter():
        if isinstance(p.tag, str) and p.tag.lower() == tag.lower() and any(x is el for x in p.iter()):
            return p
    return root


def resolve_cross_file_tagjumps(ctx, root, rel, table=None) -> int:
    """SPEC 39: a conversation whose tabled tagJump leaves its file gets the tagged <line> (and its subtree) copied
    from the owning conversation under the jumping response's participant. The jumping response's conversationEnd
    is removed: XMen2.exe ends the conversation on that flag even when the tagJump resolves (in game, SPEC 39.2),
    and the copied subtree ends at its own %END%. Returns the number of copies inserted."""
    r = (rel or '').replace('\\', '/').lower()
    if not r.startswith('conversations/'):
        return 0
    ref = r[len('conversations/'):].rsplit('.', 1)[0]
    entries = (table if table is not None else CROSS_FILE_TAGJUMPS).get(ref)
    if not entries:
        return 0
    n = 0
    for tag, src in entries:
        if _local_tagindex(root, tag):
            continue                                    # resolves locally already (idempotence)
        jumpers = [el for el in root.iter() if isinstance(el.tag, str) and el.tag.lower() == 'response'
                   and _attr(el, 'tagjump')[1] == tag]
        if not jumpers:
            continue                                    # the jumping response was cut
        try:
            src_root = ctx.read_x1_xml(f'conversations/{src}.eng')
        except KeyError:
            ctx.warn(f'{rel}: cross-file tagjump {tag!r} -> {src}.eng, but XML1 has no such conversation')
            continue
        target = next((el for el in src_root.iter() if isinstance(el.tag, str) and el.tag.lower() == 'line'
                       and _attr(el, 'tagindex')[1] == tag), None)
        if target is None:
            ctx.warn(f'{rel}: cross-file tagjump {tag!r}, but {src}.eng has no such tagIndex')
            continue
        sc = _enclosing(root, jumpers[0], 'startCondition')
        holder = ET.Element('participant', {'name': f'x1_tagjump_{tag}'})
        holder.append(copy.deepcopy(target))
        sc.append(holder)
        for j in jumpers:
            key, _val = _attr(j, 'conversationend')
            if key is not None:
                del j.attrib[key]                       # else the engine ends the conversation at this response
        n += 1
        ctx.note(f'{rel}: tagjump {tag!r} leaves the file (XML1 resolved it in {src}); the tagged line and its '
                 f'subtree were copied into a new participant of this file, and the jumper\'s conversationEnd '
                 f'removed (SPEC 39)')
    return n
