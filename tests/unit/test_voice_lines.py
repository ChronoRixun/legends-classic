"""Issue #49: the first game's voice lines. Synthetic banks and stats only (invented folder and event names): the
voice folder rule, P2's voice folders, and the merge rule that lets XML1's entries win its own voice folders."""
import struct
import tempfile
from pathlib import Path

import synth  # noqa: F401  puts tools/ on sys.path
from xml1build.lib import merge_zsnd, simlookup, zsnd
from xml1build.lib.convert_zsnd import build_pc
from xml1build.lib.zhash import elf_hash
from xml1build.prepare import tables as P2
from xml1build import validate_sound as VSND

RANDOM = '/***RANDOM***/%d'


def _bank(path, keyed):
    """a PC bank with one sound per (key, audio bytes) pair, each on its own sample and file."""
    sounds, samples, files = [], [], []
    for i, (key, audio) in enumerate(keyed):
        sounds.append(([key], struct.pack('<HH', i, 0x1000) + b'\x7f' + b'\0' * 19))
        samples.append(([elf_hash('smp%d' % i)], struct.pack('<HBBI', i, 0, 0, 22050) + b'\0' * 16))
        name = (b'f%d.wav' % i).ljust(64, b'\0')
        files.append(([elf_hash('file%d' % i)], struct.pack('<III', 0, 0, 0x6a) + name, audio))
    Path(path).write_bytes(build_pc(sounds, samples, files, []))
    return path


def _answer(path, name):
    """the audio bytes that answer `name` in a bank (the name, else random variant 0), and the variant count."""
    b = zsnd.load(str(path))
    by_key = {h: s for s in b.sounds for h in s.hashes}
    h = elf_hash(name)
    if h in by_key:
        s, n = by_key[h], 0
    else:
        n = 0
        while elf_hash(RANDOM % n, h) in by_key:
            n += 1
        if not n:
            return None, 0
        s = by_key[elf_hash(RANDOM % 0, h)]
    f = b.files[b.samples[s.u16(0)].u16(0)]
    return b.file_bytes(f), n


def test_voice_dir_swaps_the_first_m_folder_suffix():
    assert simlookup.voice_dir('zork_m') == 'zork_v'
    assert simlookup.voice_dir('Zo_mb_m') == 'zo_mb_v'          # only a '_m' that ends the folder name
    assert simlookup.voice_dir('plain') == 'plain'               # no '_m': the engine looks in the folder itself
    assert simlookup.voice_dir('') == ''


def test_xml1_voice_folders_reads_both_stats_and_the_event_table():
    with tempfile.TemporaryDirectory() as td:
        loose, assets = Path(td) / 'loose', Path(td) / 'assets'
        (loose / 'data').mkdir(parents=True)
        (assets / 'data').mkdir(parents=True)
        (loose / 'data' / 'herostat.eng').write_text(
            '<characters><stats name="Zork" sounddir="zork_m"/><stats name="Nodir"/></characters>')
        (assets / 'data' / 'herostat.eng').write_text('<characters><stats name="Old" sounddir="old_m"/></characters>')
        (assets / 'data' / 'npcstat.eng').write_text('<characters><stats name="Qux" sounddir="qux_m"/></characters>')
        (loose / 'data' / 'shared_sounds.xml').write_text('<SOUNDTABLE><sounds snd_a="ouch" snd_b="gloat"/></SOUNDTABLE>')
        dirs, events = P2.xml1_voice_folders(loose, assets)
    assert dirs == ['qux_v', 'zork_v']          # loose herostat wins over the assets copy
    assert events == ['gloat', 'ouch']


def test_merge_lets_the_shadowed_names_answer_with_the_added_bank():
    taunt, win = elf_hash('char/zork_v/taunt'), elf_hash('char/zork_v/win')
    other = elf_hash('char/blip_v/taunt')
    with tempfile.TemporaryDirectory() as td:
        base = _bank(Path(td) / 'base.zss', [(taunt, b'B1B1'), (elf_hash(RANDOM % 0, win), b'B2B2'),
                                             (elf_hash(RANDOM % 1, win), b'B3B3'), (other, b'B4B4')])
        add = _bank(Path(td) / 'add.zss', [(taunt, b'A1A1'), (elf_hash(RANDOM % 0, win), b'A2A2')])
        plain, shadowed = str(Path(td) / 'plain.zss'), str(Path(td) / 'shadowed.zss')
        r0 = merge_zsnd.merge(str(base), str(add), plain)
        r1 = merge_zsnd.merge(str(base), str(add), shadowed, shadow=[taunt, win])
        # control: without the rule the base bank's entries win every shared name
        assert _answer(plain, 'char/zork_v/taunt') == (b'B1B1', 0)
        assert _answer(plain, 'char/zork_v/win') == (b'B2B2', 2)
        assert r0['shadowed_keys'] == 0 and r0['appended_sounds'] == 0
        # the rule: the added bank answers, and the base's extra random variant no longer joins the draw
        assert _answer(shadowed, 'char/zork_v/taunt') == (b'A1A1', 0)
        assert _answer(shadowed, 'char/zork_v/win') == (b'A2A2', 1)
        assert _answer(shadowed, 'char/blip_v/taunt') == (b'B4B4', 0)          # other folders untouched
        assert r1['shadowed_keys'] == 3 and r1['appended_sounds'] == 2
        m, b = zsnd.load(shadowed), zsnd.load(str(base))
        assert [s.raw for s in m.sounds[:len(b.sounds)]] == [s.raw for s in b.sounds]   # base indices kept
        # the validator's view: the answer's file index is past the base bank's files
        files = VSND.sound_files(shadowed)
        assert VSND.answer_file(files, 'char/zork_v/taunt') >= VSND.file_count(str(base))
        assert VSND.answer_file(VSND.sound_files(plain), 'char/zork_v/taunt') < VSND.file_count(str(base))
