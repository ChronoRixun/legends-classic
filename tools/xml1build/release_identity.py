"""Append-only official LC content identities and the four-character lobby namespace.

Add a row when assigning a release; never edit, reorder or reuse an issued token.
Final integration must assign its final CONTENT_VERSION/catalogue revision here.
Private candidates use a separate namespace and never append release reservations.
"""
from dataclasses import dataclass
from xml1builder import CONTENT_VERSION, VERSION


@dataclass(frozen=True)
class Identity:
    release: str
    content_version: int
    catalogue_revision: int
    token: str
    bind_manifest: str = ''


# Historical lobby tokens stay reserved even though these pre-LC builds had no catalogue.
# A token reservation is an identity in the history; it cannot be assigned again.
CURRENT_CATALOGUE_REVISION = 7

# This private test envelope is deliberately outside the append-only release
# history. Its exact generated files/fingerprint are checked by the package's
# peer receipt. Release integration must assign an immutable official identity.
# It applies only while VERSION is the candidate's (0.4.0e); a release builder never takes it.
PRIVATE_CANDIDATE = Identity('0.4.0e', 33, 7, 'C04E')

HISTORY = (
    Identity('port-before-LC', 0, 0, 'X1.0'),
    Identity('balance-experiment', 0, 0, 'X1.1'),
    Identity('0.2.0b-original', 0, 0, 'X1.2'),
    Identity('0.2.0', 16, 2, 'LC20', '34afe76239b548e3dd808c00b94c3de99cb0feff40e5b25f9b83d3c5f1b8438f'),
    Identity('0.2.0-integrated-guards', 16, 3, 'LC21', '8c1737d887e8113887fdff56004bf931995c31b30b359bb894fb3c245af9fa72'),
    Identity('0.2.0-integrated-talents', 16, 4, 'LC22', 'b6f19256b5b2e9d0bce31e622404cbe173891e0ccfe216ab0707db1a525f1d50'),
    Identity('0.2.0-talents-minimal', 16, 5, 'LC23', '7d62fba81dd1cf58ea375311d8697d34cf6c213a16e25d0a0f8ab57b0d736e0f'),
    Identity('0.2.0-candidate-e', 16, 6, 'LC24', '8ecd8ea2e8f4172ae9b7b7ea57b6f29c30dd9eb832f8dc187a4787e0aaab9c53'),
    Identity('0.2.0-candidate-i', 17, 6, 'LC25', '85fbdb54e626766891bb0d9e118f2087a24a5027309959e31a4a3b8cebe14779'),
    Identity('0.2.0-candidate-j', 18, 6, 'LC26', '7fb2123737d6eb0a604a0bb8c1f3b80b7c56407b36b73ef2ccd0a690fc33979b'),
    Identity('0.2.2', 19, 6, 'LC27', '2e2e5b4e2ef1940b7d63dc3d5cf8647940c4ff7d3c97572f5095481b37966a62'),
    Identity('0.2.3', 20, 6, 'LC28', 'e6b547bed0ea8986cb3493a8d219bda220eec0416661ab72d9b1074b06f7e5f2'),
    Identity('0.2.3c', 20, 7, 'LC29', 'fceba8e8092e5eb4c363d7a9054c6e3db16fb4adbbc9f193193f16ed76a7c549'),
    Identity('0.2.3h', 21, 7, 'LC30', '1b87836ed197fe8b101325d8a8171c01f19c4691c2c5216da2741d61db41cafd'),
    Identity('0.2.4', 22, 7, 'LC31', 'd20e76286784f46971ccb903bc4813513607e62c9df2c07aaf327eaeeca9eebe'),
    Identity('0.2.5', 23, 7, 'LC32', '03b447adfb79a60a7ac84e52d7cb801a11b69a50c40e5e0c6fcb922db69017fe'),
    # Issued as 0.3.0; renumbered 0.4.0 while in beta. The release label is history (append-only), the token LC33 is unchanged.
    Identity('0.3.0', 24, 7, 'LC33', '240ef860ad0a8676bff9bcd9302ad40fe12993af0f27768d45e0e172e11d424a'),
    # Issued at 0.4.0-beta.5: the classic look (classic HUD, menus and map assets, team-room selection cones/rings off).
    Identity('0.4.0', 25, 7, 'LC34', '28230ad0107151f048560c0ef475322d658dee4644a0726ea9fc95c8e533b5d4'),
    # Issued at 0.4.0-beta.6: enemy AI fidelity (rule 16 revision 10, the officer's weapon brain) and the classic HUD
    # atlas without the small-map frame.
    Identity('0.4.0-beta.6', 26, 7, 'LC35', '3f378bccc40eee3e2830b944ba69ee2c41b8cc721dcb02f7ed10666866958de5'),
    # Issued at 0.4.0-beta.7: every gun NPC's weapon brain with the XML1 bullet trace gate (schema 4 rows, rule 16
    # revision 11), the "Alison" speaker label, one-sided level walls in the XML1 zones (rule 30 revision 2).
    Identity('0.4.0-beta.7', 27, 7, 'LC36', '22a8c77d592f9e436adb724d6be5a9fdff4f4108ddd89bc2ba4d6c513f403e72'),
)


def validate_history(rows, *, previous=()):
    if tuple(rows[:len(previous)]) != tuple(previous):
        raise ValueError('release identity history is append-only')
    tokens, versions = set(), set()
    for row in rows:
        if len(row.token) != 4 or not all(c.isascii() and (c.isalnum() or c in '._-') for c in row.token):
            raise ValueError('GameVersion must have exactly four ASCII token characters')
        if row.token == '1.30' or row.token.casefold() in tokens:
            raise ValueError('GameVersion token already assigned')
        tokens.add(row.token.casefold())
        if row.content_version:
            version = (row.content_version, row.catalogue_revision)
            if version in versions:
                raise ValueError('official content identity already assigned')
            versions.add(version)


def game_version(*, content_version=None, catalogue_revision=None):
    validate_history(HISTORY)
    cv = CONTENT_VERSION if content_version is None else content_version
    if catalogue_revision is None and cv == CONTENT_VERSION:
        catalogue_revision = CURRENT_CATALOGUE_REVISION
    matches = [r for r in HISTORY if r.content_version == cv and cv != 0 and
               (catalogue_revision is None or r.catalogue_revision == catalogue_revision)]
    candidate = PRIVATE_CANDIDATE
    if not matches and VERSION == candidate.release and cv == candidate.content_version and \
            catalogue_revision == candidate.catalogue_revision:
        validate_history(HISTORY + (candidate,))
        return candidate.token
    if len(matches) != 1:
        raise ValueError(f'unassigned official release identity: content {cv}, catalogue {catalogue_revision}')
    return matches[0].token


def manifest(out):
    """Identity of the actual catalogue and bind manifest, archived with each build."""
    from pathlib import Path
    from lcsave import lcfiles
    cat = lcfiles.read_catalogue_lcc((Path(out) / 'Data/lcsave/catalogue.lcc').read_bytes())
    token = game_version(content_version=cat['content_version'], catalogue_revision=cat['revision'])
    if cat['content_version'] != CONTENT_VERSION:
        raise ValueError('save catalogue content version differs from this builder')
    fingerprint = lcfiles.content_fingerprint(str(out))
    issued = next((r for r in HISTORY if r.token == token), None)
    if issued is not None and (not issued.bind_manifest or fingerprint != issued.bind_manifest):
        raise ValueError('official release bind manifest differs from its immutable history; assign a new identity')
    files = sorted([Path(out) / 'Data/lcsave/catalogue.lcc', Path(out) / 'Data/lcsave/legacy.lcm'] +
                   list((Path(out) / 'Data').rglob('*.lcbind')))
    import hashlib
    hashes = {p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    return dict(schema=1, builder_version=VERSION, content_version=cat['content_version'],
                catalogue_revision=cat['revision'], game_version=token,
                identity_kind='official' if issued is not None else 'private-candidate',
                bind_manifest_algorithm='lcsave-bind-sha256-v1',
                bind_manifest=fingerprint, files_sha256=hashes)
