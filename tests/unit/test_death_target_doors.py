"""Synthetic destruction delivery and preservation of original smart door state."""
import copy
import xml.etree.ElementTree as ET
from xml1build import common as C, death_targets as D, x1schema as XS, settle as SE
from xml1build import scripts_transform as ST, validate as V
from lcsave.binds import numbered_entities
from lcsave.zonecompat import attest

ZONE='invented/bay'

def zone():
    return ET.fromstring("""<world>
    <entinst type="hatch"><inst name="first" pos="900 0 0"/><inst name="second" pos="1800 0 0"/></entinst>
    <entinst type="console"><inst name="console" pos="1000 2000 0"/></entinst>
    <entinst type="relay"><inst name="relay" pos="50 50 0"/></entinst>
    <entinst type="old_gate"><inst name="old_gate" pos="60 60 0"/></entinst>
    <entinst type="other"><inst name="other" pos="70 70 0"/></entinst>
    <entity name="hatch" classname="doorent" actonuse="false" toggleonact="true" actcountdisable="1" autoclosedelay="0"/>
    <entity name="old_gate" classname="doorent" smartent="false"/>
    <entity name="other" classname="doorent" actonuse="false" toggleonact="true" actcountdisable="1"/>
    <entity name="relay" classname="actionent"/>
    <entity name="console" classname="physent" actondeath="true" acttargets="first relay" deathtargets="other" deathspawn="stump" health="100"/>
    <entity name="stump" classname="physent" structure="2" nogravity="true" mass="0"/>
    </world>""")

def defs(root):return {e.get('name'):e for e in root.iter('entity')}
def changed(root):
    scripts={};count=D.convert(root,ZONE,scripts);return count,scripts

def test_original_door_console_and_placements_are_unchanged():
    root=zone();before=copy.deepcopy(root)
    assert changed(root)[0]==1
    for name in ('hatch','console','other','relay','old_gate'):
        assert defs(root)[name].attrib==defs(before)[name].attrib
    groups=root.findall('entinst')
    assert [C.xmlb.encode(g) for g in groups[:5]]==[C.xmlb.encode(g) for g in before.findall('entinst')]
    assert defs(root)['hatch'].get('smartent') is None
    assert defs(root)['stump'].get('smartent')=='false'
    assert len(D.names(root))==2 and not D.problems(root,ZONE)

def test_listener_shares_only_instance_name_and_worker_uses_native_schedule():
    root=zone();changed(root);ds=defs(root)
    listener=ds['lc_dt_listen_first'];poller=ds['lc_dt_poll_first']
    assert listener.get('classname')==poller.get('classname')=='actionent'
    assert 'setGameFlag' in listener.get('actscript')
    assert poller.get('firstact')==poller.get('actrescheduledelay')=='0.25'
    assert not listener.get('acttargets') and not poller.get('acttargets')
    tail=root.findall('entinst')[-2:]
    assert tail[0][0].get('name')=='first' and tail[1][0].get('name')=='lc_dt_poll_first'

def test_worker_does_not_activate_until_the_death_flag_is_latched():
    root=zone();_,scripts=changed(root)
    text=scripts[D.PREFIX+ZONE+'/first'];trace=[];flags={}
    ST.run_pack_ops(text.splitlines(),flags,trace=trace)
    assert not trace
    assert D.FLAG_BIT==1
    flags[(D.flag(ZONE,'first'),D.FLAG_BIT)]=1
    ST.run_pack_ops(text.splitlines(),flags,trace=trace)
    assert trace==[('act','"first", "first"')]
    assert ':' not in text and 'endif' in text  # Raven conditions, not Python blocks


def test_listener_and_worker_use_the_same_valid_native_flag_bit():
    root=zone();_,scripts=changed(root);flags={};trace=[]
    ST.run_pack_ops([defs(root)['lc_dt_listen_first'].get('actscript')],flags)
    assert flags=={(D.flag(ZONE,'first'),1):1}
    ST.run_pack_ops(scripts[D.PREFIX+ZONE+'/first'].splitlines(),flags,trace=trace)
    assert trace==[('act','"first", "first"')]

def test_stump_recovery_checks_all_three_coordinates():
    root=zone();_,scripts=changed(root)
    text=scripts[D.PREFIX+ZONE+'/stump_stump']
    for point,wanted in [((1000,2000,0),True),((1009,2000,0),False),((1000,2009,0),False),((1000,2000,9),False)]:
        flags={};funcs={name:(lambda args,value=value:value) for name,value in zip(('getPosX','getPosY','getPosZ'),point)}
        ST.run_pack_ops(text.splitlines(),flags,funcs=funcs)
        assert bool(flags.get((D.flag(ZONE,'first'),D.FLAG_BIT)))==wanted


def test_two_stumps_only_latch_the_gate_at_their_own_origin():
    root=zone();second=copy.deepcopy(defs(root)['console']);second.set('name','console2');second.set('acttargets','second');root.append(second)
    group=ET.SubElement(root,'entinst',type='console2');ET.SubElement(group,'inst',name='console2',pos='1000 4000 0')
    _,scripts=changed(root);text=scripts[D.PREFIX+ZONE+'/stump_stump']
    for point,target in [((1000,2000,0),'first'),((1000,4000,0),'second')]:
        flags={};funcs={name:(lambda args,value=value:value) for name,value in zip(('getPosX','getPosY','getPosZ'),point)}
        ST.run_pack_ops(text.splitlines(),flags,funcs=funcs)
        assert flags=={(D.flag(ZONE,target),1):1}

def test_native_actondeath_precedence_is_not_a_union():
    root=zone();assert [x['target'] for x in D.links(root)]==['first']
    defs(root)['console'].set('acttargets','');assert [x['target'] for x in D.links(root)]==['other']
    defs(root)['console'].set('actscript','made/up');assert D.links(root)==[]

def test_ineligible_and_authored_residency_are_preserved():
    for name,key,value in [('hatch','smartent','true'),('hatch','smartent','false'),('hatch','autoclosedelay','1'),('hatch','actcountdisable','0'),('hatch','actonuse','true'),('hatch','startenabled','false'),('hatch','actleader','true'),('hatch','requirekey','made/up'),('stump','spawnscript','made/up'),('stump','structure','0')]:
        root=zone();defs(root)[name].set(key,value);before=C.encode_xmlb(root)
        assert changed(root)==(0,{}) and C.encode_xmlb(root)==before

def test_repeated_conversion_is_byte_identical():
    root=zone();count,scripts=changed(root);before=C.encode_xmlb(root)
    again,second=changed(root)
    assert count==1 and again==0 and scripts==second and C.encode_xmlb(root)==before

def test_prefix_attestation_does_not_discard_original_smart_door_aliases():
    root=zone();before=C.encode_xmlb(root);old,errors=numbered_entities(root);assert not errors
    changed(root);new,errors=numbered_entities(root);assert not errors
    assert new[:len(old)]==old
    assert [t for t,_,_ in new[len(old):]]==['lc_dt_listen_first','lc_dt_poll_first']
    row=attest(ZONE,before,C.encode_xmlb(root))
    assert row is not None and not row['fresh_aliases'] and not row['ambiguous_aliases']

def test_attestation_rejects_unrelated_edits_even_with_valid_relays():
    root=zone();before=C.encode_xmlb(root);changed(root)
    for name,key,value in [('hatch','health','99'),('console','health','99'),('stump','model','made/up/other')]:
        bad=copy.deepcopy(root);defs(bad)[name].set(key,value)
        assert attest(ZONE,before,C.encode_xmlb(bad)) is None

def test_relay_collision_and_corrupt_placement_fail_closed():
    root=zone();changed(root);defs(root)['lc_dt_poll_first'].set('actrescheduledelay','0')
    assert D.problems(root,ZONE)
    root=zone();changed(root);root.findall('entinst')[-1][0].set('pos','1 2 3')
    assert D.problems(root,ZONE)

def test_validator_rejects_missing_recovery_and_early_resident_tail():
    root=zone();assert D.problems(root,ZONE);changed(root)
    defs(root)['stump'].set('smartent','true');assert D.problems(root,ZONE)
    root=zone();changed(root);group=root.findall('entinst')[-1];root.remove(group);root.insert(0,group)
    assert any('ordinals' in s for s in D.problems(root,ZONE))

def test_old_tail_guards_allow_only_the_new_resident_actions():
    root=zone();defs(root)['relay'].set('xml1settle','true');defs(root)['old_gate'].set('xml1settle','true');defs(root)['old_gate'].set('xml1embeddedfloor','true');defs(root)['other'].set('xml1hazardbounds','true')
    changed(root)
    assert not SE.numbered_tail_problems(root,XS.post_settle_names(root,'maps/'+ZONE+'.eng'))
    assert not XS.hazard_bounds_tail_problems(root)

def test_output_validator_checks_both_localized_variants():
    root=zone();good=copy.deepcopy(root);changed(good)
    class Validator:
        def converted_zones(self):return [ZONE]
        def tree(self,rel):return good if rel.endswith('.xmlb') else root
    check=V.Check('test','delivery');V.Validator.death_target_doors(Validator(),check)
    assert check.errors and any('.engb' in s for s in check.errors)

def test_flags_are_case_stable_and_separate_between_targets_and_zones():
    assert D.flag(ZONE,'FIRST')==D.flag(ZONE.upper(),'first')
    assert len({D.flag(ZONE,'first'),D.flag(ZONE,'second'),D.flag('another/bay','first')})==3
    assert len(D.flag(ZONE,'first'))==8
