"""SPEC 27.5.2: XML1 zone scripts that strand a reloaded zone, patched at the source before the script rewrite.

nyc/fb/nyc_fb1 (the Sentinel flashback's first street, tester report 11-11): its zone script plays the intro
conversation 1_4_5 only while the mission var s_fb_intro is 0 and sets it to 1 at once. The intro is what acts the
spawner of the first Sentinel (1_4_5 -> nyc/fb/sentinel_intro -> ss_sentinelflashback01) and only that Sentinel's
death script (nyc/fb/sentinel1_death) enables the way on: zone_link01 on, the "finish your objectives" trigger_touch02
off. The zone has a save Xtraction Point and its world is nosave="true": a save made there keeps the var and the
objectives but not the zone's entity states. Loading it (also through "All X-Men have been eliminated" -> Load Game)
gives a street with no Sentinel, s_fb_intro = 1, the link off and the trigger on - no way out. Proven live on
0.6.0-beta.6 for a save made before and one made after the first Sentinel's death.

The fix keeps the first visit as it is and adds the reload case as an else branch of the intro gate: the first
Sentinel already destroyed (objective sentinel1 complete - objectives are saved) -> redo what its death script did;
not yet -> play the intro again, which spawns it. Nothing else enters nyc_fb1 with s_fb_intro set: the flashback
start clears it and no zone links back into nyc_fb1.

Each fix names the XML1 source it was written for by the sha1 of its lines ('\\n'-joined, line ends and trailing empty
lines ignored), so a different source fails closed; an already fixed source is left as it is.
"""
import hashlib

# zone script rel -> (sha1 of the XML1 source lines, lines inserted before its last line, the intro gate's 'endif')
FIXES = {
    'nyc/fb/nyc_fb1': ('d9ace8000e8e027a03a5cef72d78fdf9d382dd58', [
        'else',
        '     # ( "x1: SPEC 27.5.2 - a save loaded here keeps s_fb_intro and the objectives, not the zone entities" )',
        '     x1fb_s1 = getObjective("sentinel1", "COMPLETE" )',
        '     if x1fb_s1 == 1',
        '          # ( "x1: the first Sentinel is destroyed - redo its death script (nyc/fb/sentinel1_death)" )',
        '          setEnable("zone_link01", "TRUE" )',
        '          setEnable("trigger_touch02", "FALSE" )',
        '     else',
        '          # ( "x1: not yet - the intro spawns it again (1_4_5 -> nyc/fb/sentinel_intro)" )',
        '          startConversation("nyc/fb/1_4_5" )',
        '     endif',
    ]),
}


def _key(rel):
    key = str(rel).replace('\\', '/').lower()
    if key.startswith('scripts/'):
        key = key[len('scripts/'):]
    return key[:-3] if key.endswith('.py') else key


def _lines(data):
    if data.startswith(b'\xef\xbb\xbf'):
        raise ValueError('reload fix: unexpected byte order mark')
    out = data.decode('latin-1').replace('\r\n', '\n').replace('\r', '\n').split('\n')
    while out and out[-1] == '':
        out.pop()
    return out


def _sha1(lines):
    return hashlib.sha1('\n'.join(lines).encode('latin-1')).hexdigest()


def fixed_lines(original, insert):
    """The fixed script: the inserted lines go before the source's last line (the gate's 'endif')."""
    if not original or original[-1].strip().lower() != 'endif':
        raise ValueError('reload fix: the source does not end with the gate it extends')
    return original[:-1] + list(insert) + [original[-1]]


def apply(rel, data):
    """The script bytes to convert for scripts/<rel>.py (rel without .py, any case and slashes)."""
    fix = FIXES.get(_key(rel))
    if fix is None:
        return data
    sha1, insert = fix
    have = _lines(bytes(data))
    if _sha1(have) != sha1:
        n = len(insert)
        if len(have) > n + 1 and have[-n - 1:-1] == list(insert) and _sha1(have[:-n - 1] + have[-1:]) == sha1:
            return data                      # already fixed
        raise ValueError(f'scripts/{_key(rel)}.py: reload fix expects the XML1 source it was written for')
    return ('\r\n'.join(fixed_lines(have, insert)) + '\r\n').encode('latin-1')
