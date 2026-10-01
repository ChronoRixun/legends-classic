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
import re

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
