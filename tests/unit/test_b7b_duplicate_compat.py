"""Synthetic regression for the reviewed identical-definition compatibility case."""
import copy
import xml.etree.ElementTree as ET
import xmlb
from lcsave import zonecompat as Z
from lcsave.binds import BindError, numbered_entities
from xml1build import offset_residents as O

def fixture(conflict=False):
 r=ET.Element('world');e=ET.SubElement(r,'entity',name='mm_damagestraight_mm',classname='physent',smartent='false',model='synthetic/box')
 other=copy.deepcopy(e)
 if conflict:other.set('synthetic_value','different')
 r.append(other);g=ET.SubElement(r,'entinst',type=e.get('name'));ET.SubElement(g,'inst',name='old_fixture',pos='1 2 3');return r

def test_b7b_identical_old_duplicates_attest_to_unique_current():
 old=fixture();new=copy.deepcopy(old);new.remove(new.findall('entity')[1]);e=ET.SubElement(new,'entity',name='tail_fixture',classname='physent',smartent='false',model='synthetic/tail');g=ET.SubElement(new,'entinst',type=e.get('name'));ET.SubElement(g,'inst',name='new_fixture',pos='4 5 6')
 row=Z.attest('synthetic/zone',xmlb.encode(old),xmlb.encode(new))
 assert row is not None and row['placements']==[0]
 assert row['digest']==Z.prefix_digest(Z.resident_prefix(new)[0][:1])

def test_b7b_conflicting_duplicate_still_refuses():
 try:Z.resident_prefix(fixture(True))
 except BindError:pass
 else:raise AssertionError('conflicting definitions were accepted')

def test_b7b_scoped_output_dedup_preserves_placements_and_ordinals():
 r=fixture();before=numbered_entities(r);placed=[ET.tostring(e) for e in r.findall('entinst')]
 assert O.dedupe_identical_mastermold2(r,'synthetic/other')==0 and len(r.findall('entity'))==2
 assert O.dedupe_identical_mastermold2(r,'mastermold/mastermold2')==1
 assert len(r.findall('entity'))==1 and numbered_entities(r)==before and [ET.tostring(e) for e in r.findall('entinst')]==placed
 assert O.dedupe_identical_mastermold2(r,'mastermold/mastermold2')==0

def test_b7b_scoped_output_conflict_refuses_without_mutation():
 r=fixture(True);before=ET.tostring(r)
 try:O.dedupe_identical_mastermold2(r,'mastermold/mastermold2')
 except ValueError:pass
 else:raise AssertionError('conflicting output definitions were silently deduplicated')
 assert ET.tostring(r)==before
