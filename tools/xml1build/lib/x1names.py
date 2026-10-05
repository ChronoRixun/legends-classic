"""Collision-free namespace for XML1 character assets inside an XML2 install.

Import this from any converter (zones, scripts, packages) so every workstream renames identically.

Rules (evidence in the characters workstream report):
  SKINS   every XML1 numeric actor id S (4 digits, prefix 00-99) -> S + 14000 (prefix 140-239, 5 digits).
          XMen2.exe parses skin as prefix=all-but-last-2 digits stored in a BYTE (0x4b9c40) and rebuilds
          it with %02d/%03d + %02d (0x4b8090), so prefixes must stay <= 255; XML2 uses prefixes 0-135 and
          200, XML1 uses 0-99 but never 60, so +140 never lands on an XML2 prefix. Costume suffixes (skin_60s
          etc.) are 2-digit variants and do not change. Applies to actors/<id>.igb (incl. numeric bolt-on
          models), hud/hud_head_<id>, ui/hud/characters/<id>, ui/models/characters/<id>, package names
          <name>_<id>[_nc], and in-IGB object names "<id>" / "<id>_<suffix>" (patched in place, igb_rename).
  ANIMDB  non-numeric XML1 character anim DBs (actors/NN_name.igb) whose name also exists in XML2 with
          different content -> 'x1_' + name; XML1-only names are kept. 'common' and fightstyle_*/moveset_*
          DBs are shared with XML2 (they are global, linked by talent/fightstyle name).
  STYLES  data/powerstyles: per-character, 'x1_' on collision (identical files shared).
          data/fightstyles: shared with XML2 by name (fidelity option: 'x1_' + new shared talent), except
          X1_OWN_FIGHTSTYLES, which always ship as 'x1_' + name (style file, anim DB, shared talent).
  STATS   XML1 stats names that equal an XML2 name (case-insensitive) -> XML2's entry wins in additive
          mode; in xml1 mode XML2's same-named entry is replaced. (optional 'x1_' prefix = fidelity mode)
"""
import json, os, re

SKIN_OFFSET = 14000
_col = None
_col_path = None          # None: default_collisions()


def default_collisions():
    """the developer-mode table: research/characters/collisions.json under the repo root (xml1build.sources.REPO_ROOT,
    $XML1_PORT_ROOT). A build reads its Sources' table instead (BuildContext -> sources.apply_collisions ->
    use_collisions; prepared mode: P2's regenerated copy). Nothing is read relative to this file (it moved here from
    research/characters, BUILDER_DESIGN.md 1.5)."""
    from ..sources import REPO_ROOT, COLLISIONS_REL
    return os.path.join(str(REPO_ROOT), 'research', *COLLISIONS_REL.split('/'))


def use_collisions(path):
    """read the collision table from `path` from now on (the builder's prepared tables/collisions.json; default:
    default_collisions()). The table is cached per process; a different path drops the cache."""
    global _col, _col_path
    if os.path.normcase(os.path.abspath(path)) != os.path.normcase(os.path.abspath(_col_path or default_collisions())):
        _col_path = path
        _col = None


def _collisions():
    global _col
    if _col is None:
        with open(_col_path or default_collisions()) as fh:
            _col = json.load(fh)
    return _col


def _colliding(prefix_dir):
    """set of lowercase stems under prefix_dir (e.g. 'actors/') whose XML1 content differs from XML2's."""
    out = set()
    for cat, d in _collisions().items():
        for rel in d.get('collision', []):
            if rel.startswith(prefix_dir):
                out.add(os.path.splitext(rel[len(prefix_dir):])[0].lower())
    return out


def _identical(prefix_dir):
    out = set()
    for cat, d in _collisions().items():
        for rel in d.get('identical', []):
            if rel.startswith(prefix_dir):
                out.add(os.path.splitext(rel[len(prefix_dir):])[0].lower())
    return out


def is_skin_id(s):
    return bool(re.fullmatch(r'\d{4,5}', s or ''))


def map_skin(s):
    """'5810' -> '19810'. Non-skin strings are returned unchanged."""
    if not is_skin_id(s):
        return s
    n = int(s)
    if n >= 10000:
        raise ValueError(f'XML1 never uses 5-digit skins; got {s}')
    new = n + SKIN_OFFSET
    assert 14000 <= new <= 23999 and new // 100 != 200, s
    return str(new)


def map_skin_part(s):
    """Sub-skin names ('3401_helmet', Multipart hideskin/showskin, powerstyle skinsegment) are looked up
    inside the actor's own skin IGB, so they are NOT renamed (igb_rename only touches '<id>' and
    '<id>_outline'); references stay as they are."""
    return s


# Fighting styles shipped under their own name ('x1_' + name: the style file, its anim DB and its shared talent)
# because XML2's same-named file lacks animations the first game's moves play. fightstyle_gun_rifle: XML2's anim DB
# has 13 animations, XML1's 22 - idle, attack_light1/heavy1 and the fire moves power_1/3/5/10-12 are XML1-only, so a
# rifle soldier on XML2's file stands in another style's idle and fires without a fire animation (issue #52).
X1_OWN_FIGHTSTYLES = frozenset({'fightstyle_gun_rifle'})


def is_fightstyle_name(name):
    """a fighting-style talent / file name: XML2's 'fightstyle_*' or an X1_OWN_FIGHTSTYLES 'x1_fightstyle_*'."""
    return (name or '').lower().startswith(('fightstyle_', 'x1_fightstyle_'))


def shares_xml2_animdb(name):
    """Global anim DBs keep XML2's version: 'common' (XML2 permanent package) and the fightstyle/moveset
    DBs, which are named by the fightstyle file's animations= attribute and linked through shared
    talent names (fightstyle="true"), so they are shared rather than duplicated (fidelity option: x1_).
    X1_OWN_FIGHTSTYLES are not shared."""
    n = name.lower()
    return n == 'common' or (n.startswith(('fightstyle_', 'moveset_')) and n not in X1_OWN_FIGHTSTYLES)


def map_animdb(name, fidelity=False):
    """actors/<name>.igb for non-numeric names: character anim DBs that collide with XML2 -> 'x1_'+name;
    the anim DB of an X1_OWN_FIGHTSTYLES style -> 'x1_'+name."""
    if is_skin_id(name):
        return map_skin(name)
    if name.lower() in X1_OWN_FIGHTSTYLES:
        return 'x1_' + name.lower()
    if shares_xml2_animdb(name) and not fidelity:
        return name
    return 'x1_' + name if name.lower() in _colliding('actors/') else name


def map_powerstyle(name):
    """Powerstyles are per character: an XML1 ps_X that differs from XML2's ps_X becomes x1_ps_X."""
    if not name:
        return name
    return 'x1_' + name if name.lower() in _colliding('data/powerstyles/') else name


def map_fightstyle(name, fidelity=False):
    """Fightstyles/movesets are shared by talent name; XML2's same-named file is used unless fidelity.
    X1_OWN_FIGHTSTYLES always get 'x1_' (XML2's file lacks the first game's animations)."""
    if not name:
        return name
    if name.lower() in X1_OWN_FIGHTSTYLES:
        return 'x1_' + name.lower()
    if fidelity and name.lower() in _colliding('data/fightstyles/'):
        return 'x1_' + name
    return name


def map_actor_path(p):
    """'actors/5810' / 'actors/5810.igb' / '5810' -> mapped equivalent (extension preserved)."""
    d, base = os.path.split(p.replace('\\', '/'))
    stem, ext = os.path.splitext(base)
    return (d + '/' if d else '') + map_animdb(stem) + ext


def map_ui_path(p):
    """hud/hud_head_<id>, ui/hud/characters/<id>, ui/models/characters/<id> (any case, ext kept)."""
    q = p.replace('\\', '/')
    m = re.fullmatch(r'(?i)(.*hud_head_)(\d{4})(\.igb)?', q)
    if m:
        return m.group(1) + map_skin(m.group(2)) + (m.group(3) or '')
    m = re.fullmatch(r'(?i)(.*(?:ui/hud|ui/models)/characters/)(\d{4})(\.igb)?', q)
    if m:
        return m.group(1) + map_skin(m.group(2)) + (m.group(3) or '')
    return p


# ---------------------------------------------------------------- IGB in-place object-name rename
def igb_rename(data, old, new, suffixes=('', '_outline', '_skel')):
    """Rename IGB string fields equal to old+suffix (suffix in `suffixes`) to new+suffix.

    The engine looks a character's skin up by name inside its own skin IGB: getSkin(db, "<skin>") with a
    fallback to skinList[0] (XMen2.exe 0x5775b0/0x576cc0) and the cel outline as "<skin>_outline"
    (0x4ea590). Sub-skin part names ('3401_helmet') are left alone.
    IGB serialises a string field as <u32 padded_len><bytes NUL-terminated, zero padded to 4>, so a
    rename that still fits the padded length is done in place (no offsets move). For a 4-digit id the
    three default names always fit (+1 char). Returns (new_bytes, count, problems)."""
    import struct
    buf = bytearray(data)
    count, problems = 0, []
    alt = b'|'.join(re.escape(s.encode()) for s in suffixes if s)
    pat = re.compile(re.escape(old.encode()) + (rb'(' + alt + rb')?' if alt else b'') + rb'\x00')
    for m in list(pat.finditer(data)):
        s = m.start()
        if s < 4:
            continue
        (plen,) = struct.unpack_from('<I', data, s - 4)
        body = m.group(0)[:-1]                      # without NUL
        if plen % 4 or plen < len(body) + 1 or plen > len(body) + 4:
            continue                                 # not a length-prefixed string field
        suffix = (m.group(1) or b'')
        repl = new.encode() + suffix
        if len(repl) + 1 > plen:
            problems.append((s, body.decode(), plen))
            continue
        buf[s:s + plen] = repl + b'\x00' * (plen - len(repl))
        count += 1
    return bytes(buf), count, problems
