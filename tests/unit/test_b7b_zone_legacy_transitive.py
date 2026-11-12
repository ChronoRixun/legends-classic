"""Published stable/beta.4-era and beta.6 zone ordinal contracts through the beta.7 append.
Only hashes and placement indices are retained; no game content or save bytes.
"""
import hashlib,json,os,struct,unittest
from pathlib import Path
from lcsave import zonecompat as Z
from lcsave.binds import Binds
import xmlb
PINS = [{'zone': 'mansion/man2/subbasement2', 'old': 'e9466d3a1c203c154ad7cf9570af346084f31aa8', 'via': '3d596ceb9d117c004d4db6db34a1fcbd54a28a92', 'current': '05b19e5f234242dd30a1fb6b7c5e5ad4e5137099', 'old_ordinals': 36, 'old_mapping_sha256': '80e958306a761497564fb9080ab1f74e98e2a84e1c8ae5c4187419a1b6a15980', 'beta6_ordinals': 36, 'beta6_mapping_sha256': '80e958306a761497564fb9080ab1f74e98e2a84e1c8ae5c4187419a1b6a15980'}, {'zone': 'nyc/alison/nyc1_1_1', 'old': 'cf0698cda26d303f111425d0cccfb54e2db82b79', 'via': '45667e8e950e7ed2675baab95a43443afd5a4754', 'current': '412c622453769a67eab8fb327a4cf016f856df09', 'old_ordinals': 30, 'old_mapping_sha256': '126a8d44f9a71a831844cecff8e2726c67a2a16f61c1a49ec9164aa1f2c9c9c0', 'beta6_ordinals': 30, 'beta6_mapping_sha256': '126a8d44f9a71a831844cecff8e2726c67a2a16f61c1a49ec9164aa1f2c9c9c0'}, {'zone': 'nyc/alison/nyc1_1_2', 'old': '32f033cae78370450a67520b26055ae2a413f787', 'via': 'b9fde24d15d7130fc6339a0e94daaafcd1459b79', 'current': '544bf394f749acdd26615bde085e055ed1fbfa0d', 'old_ordinals': 99, 'old_mapping_sha256': '4eac354d573f9a0734666331dd82ed756a451f5e9b09f7f8065cc3899f76f7c2', 'beta6_ordinals': 99, 'beta6_mapping_sha256': '4eac354d573f9a0734666331dd82ed756a451f5e9b09f7f8065cc3899f76f7c2'}]

def rows():
 return json.loads((Path(Z.__file__).with_name('data')/'zone_prefixes.json').read_text(encoding='utf-8'))

def find(pin,old,current):
 return next((r for r in rows() if r['zone']==Z.zone_hash(pin['zone']).hex() and r['old']==old and r['current']==current),None)

def mapping_hash(row):
 p=row['placements'];return hashlib.sha256(struct.pack('<'+'I'*len(p),*p)).hexdigest()

def contract(pin):
 legacy=find(pin,pin['old'],pin['current']);assert legacy is not None,('missing older save chain',pin['zone'])
 direct=find(pin,pin['via'],pin['current']);assert direct is not None,('missing beta.6 append',pin['zone'])
 assert len(legacy['placements'])==pin['old_ordinals'] and mapping_hash(legacy)==pin['old_mapping_sha256'],('older save maps to wrong ordinals',pin['zone'])
 assert len(direct['placements'])==pin['beta6_ordinals'] and mapping_hash(direct)==pin['beta6_mapping_sha256'],('beta.6 save maps to wrong ordinals',pin['zone'])
 assert len(legacy['placements'])<=len(direct['placements'])
 # The older chain must retain eligibility for smart states promoted by this append.
 assert set(map(tuple,direct['fresh_aliases']))<=set(map(tuple,legacy['fresh_aliases']+legacy['ambiguous_aliases']))

def test_older_and_beta6_brig_ordinals():contract(PINS[0])
def test_older_and_beta6_nyc_first_ordinals():contract(PINS[1])
def test_older_and_beta6_nyc_second_ordinals():contract(PINS[2])

def test_built_older_and_beta6_rows_match_actual_current_prefixes():
 out=os.environ.get('XML1_BUILT_OUT')
 if not out:raise unittest.SkipTest('requires the built-output suite')
 binds=Binds(out);actual=Z.load(out)
 for pin in PINS:
  raw=Path(binds.zone_file(pin['zone'])).read_bytes();assert hashlib.sha1(raw).hexdigest()==pin['current']
  entries,_=Z.resident_prefix(xmlb.decode(raw))
  for old,key in ((pin['old'],'old'),(pin['via'],'beta6')):
   r=next((r for r in actual if r['zone']==Z.zone_hash(pin['zone']) and r['old'].hex()==old and r['current'].hex()==pin['current']),None)
   assert r is not None,('built sidecar missing chain',pin['zone'],old)
   assert len(r['placements'])==pin[key+'_ordinals'] and mapping_hash(r)==pin[key+'_mapping_sha256']
   assert Z.prefix_digest(entries[:len(r['placements'])])==r['digest'],('native prefix mismatch',pin['zone'],old)
