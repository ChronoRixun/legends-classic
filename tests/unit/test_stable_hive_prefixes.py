"""Hash-only historical save contracts through the stable Hive resident append."""
import hashlib,json,os,unittest
from pathlib import Path
from lcsave import zonecompat as Z
from lcsave.binds import Binds
import xmlb

ZONE='hive/h_int/hive2_2_4'
VIA='8ad060f723c200d81dc3f6584b77d9b5634297cb'
CURRENT='c992fe2fb33ba6d961a6112fd295db39cd9588b0'
EARLIER=('5e89e6510cc0db0eeecbeb201b80334698d850d7',
         '6752853e6e89a4f9a7dc6108c483e6935856d88a',
         'ca508dac45115a073339ade5ba8edabd1ace6806')

def contract(old):
    rows=json.loads((Path(Z.__file__).with_name('data')/'zone_prefixes.json').read_text(encoding='utf-8'))
    rows=[r for r in rows if r['zone']==Z.zone_hash(ZONE).hex()]
    before=next(r for r in rows if r['old']==old and r['current']==VIA)
    after=next((r for r in rows if r['old']==old and r['current']==CURRENT),None)
    assert after is not None,('historical Hive progress would lose its direct current-map attestation',old)
    assert {k:v for k,v in after.items() if k!='current'}=={k:v for k,v in before.items() if k!='current'}

def test_stable_hive_oldest_prefix_preserved():contract(EARLIER[0])
def test_stable_hive_intermediate_prefix_preserved():contract(EARLIER[1])
def test_stable_hive_equivalent_prefix_preserved():contract(EARLIER[2])

def test_stable_hive_built_rows_attest_the_actual_resident_prefix():
    out=os.environ.get('XML1_BUILT_OUT')
    if not out:raise unittest.SkipTest('requires the stable built-output suite')
    binds=Binds(out);raw=Path(binds.zone_file(ZONE)).read_bytes()
    assert hashlib.sha1(raw).hexdigest()==CURRENT
    entries,_=Z.resident_prefix(xmlb.decode(raw))
    numbering=binds.zone_numbering(ZONE)
    for old in (*EARLIER,VIA):
        row=Z.match(Z.load(out),ZONE,bytes.fromhex(old),numbering)
        assert row is not None,('actual current map refuses its historical prefix',old)
        assert Z.prefix_digest(entries[:len(row['placements'])])==row['digest']
