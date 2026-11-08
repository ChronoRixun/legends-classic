"""Synthetic save-safe unlock delivery and old-save recovery."""
import copy
import xml.etree.ElementTree as ET
from xml1build import common as C, scripts_transform as ST
from lcsave.binds import numbered_entities
from lcsave.zonecompat import attest


def module():
    from xml1build import progression_relays
    return progression_relays


def world(target='exitdoor1'):
    r=ET.Element('world');ET.SubElement(r,'entity',name=target,classname='doorent',startenabled='false',actcountdisable='1')
    g=ET.SubElement(r,'entinst',type=target);ET.SubElement(g,'inst',name=target,pos='2000 1000 0')
    ET.SubElement(r,'entity',name='original',classname='actionent')
    g=ET.SubElement(r,'entinst',type='original');ET.SubElement(g,'inst',name='original',pos='0 0 0')
    return r


def run(text,objectives=None,flags=None,opened=0,loaded=123,enabled=1,alive=2,panel_loaded=123):
    trace=[];flags={} if flags is None else flags
    funcs={'getObjective':lambda args:(objectives or {}).get(args[0].strip(chr(34)),0),
           'getID':lambda args:panel_loaded if args[0].strip(chr(34))=='trigger_use02' else loaded,'getOpened':lambda args:opened,
           'getEnable':lambda args:enabled,'alive':lambda args:alive}
    ST.run_pack_ops(text.splitlines(),flags,funcs=funcs,trace=trace)
    return trace,flags


def test_sewer_exits_require_both_saved_objectives_and_only_enable_loaded_closed_door():
    D=module()
    for z,target,a,b in [('sewers/grso/sewers3_1_1','exitdoor1','ladders','porters'),('sewers/grso/sewers3_1_2','exitdoor2','ladders2','porters2')]:
        r=world(target);scripts={};assert D.convert(r,z,scripts)==1
        text=scripts[D.PREFIX+z+'/'+target]
        for av,bv,want in [(0,0,False),(1,0,False),(0,1,False),(1,1,True)]:
            trace,_=run(text,{a:av,b:bv})
            assert any(x[0]=='setEnable' for x in trace)==want,trace
        for kwargs in ({'opened':1},{'loaded':-1},{'loaded':0}):
            trace,_=run(text,{a:1,b:1},**kwargs);assert not any(x[0]=='setEnable' for x in trace)


def test_healer_catches_death_event_and_old_save_recovers_only_at_guard_volume():
    D=module();r=world('healer_door')
    ET.SubElement(r,'entity',name='ss_morlockclawb09',classname='monsterspawnerent',monster_name='scripted_grunt')
    g=ET.SubElement(r,'entinst',type='ss_morlockclawb09')
    for y in (100,200):ET.SubElement(g,'inst',name='guard',pos=f'0 {y} 0')
    scripts={};D.convert(r,'sewers/healer/sewers2_1_4',scripts)
    ds={e.get('name'):e for e in r.iter('entity')}
    listener=next(e for e in ds.values() if e.get(D.MARKER)=='listen')
    group=next(g for g in r.findall('entinst') if g.get('type')==listener.get('name'))
    assert group[0].get('name')=='trigger_enabler'
    recovery=next(e for e in ds.values() if e.get(D.MARKER)=='recover')
    assert recovery.get('classname')=='gameent' and recovery.get('actontouch')=='true'
    recovery_text=scripts[recovery.get('actscript')]
    assert not run(recovery_text,alive=1)[1]
    flags=run(recovery_text,alive=0)[1];assert flags=={(D.flag('sewers/healer/sewers2_1_4','healer_door'),1):1}
    poll=scripts[D.PREFIX+'sewers/healer/sewers2_1_4/healer_door']
    assert not run(poll)[0]
    assert any(x[0]=='setEnable' for x in run(poll,flags=flags)[0])
    assert run(listener.get('actscript'))[1]==flags


def test_nuke_used_panel_recovers_both_optional_doors_and_untouched_panel_stays_closed():
    D=module();r=world('blastdoor_nuke_n04')
    g=ET.SubElement(r,'entinst',type='blastdoor_nuke_n04');ET.SubElement(g,'inst',name='blastdoor_nuke_n05',pos='0 2000 0')
    scripts={};assert D.convert(r,'nuke_plant/nuke/nuke2_2',scripts)==2
    for text in scripts.values():
        assert not run(text,enabled=1)[0]
        assert any(x[0]=='act' for x in run(text,enabled=0)[0])
        assert not run(text,enabled=0,opened=1)[0]


def test_relays_are_idempotent_append_only_and_do_not_change_smart_door_aliases():
    D=module();r=world();before=C.encode_xmlb(r);old,errors=numbered_entities(r);assert not errors
    scripts={};assert D.convert(r,'sewers/grso/sewers3_1_1',scripts)==1
    after=C.encode_xmlb(r);new,errors=numbered_entities(r);assert not errors and new[:len(old)]==old
    assert not next(r.iter('entity')).get('smartent')
    assert D.convert(r,'sewers/grso/sewers3_1_1',{})==0 and C.encode_xmlb(r)==after
    row=attest('sewers/grso/sewers3_1_1',before,after)
    assert row and not row['fresh_aliases'] and not row['ambiguous_aliases']
    assert not D.problems(r,'sewers/grso/sewers3_1_1')
    bad=copy.deepcopy(r);next(bad.iter('entity')).set('health','99')
    assert attest('sewers/grso/sewers3_1_1',before,C.encode_xmlb(bad)) is None
    marked=next(e for e in r.iter('entity') if e.get(D.MARKER))
    marked.set('actrescheduledelay','10');assert D.problems(r,'sewers/grso/sewers3_1_1')


def test_hive_under_650_candidates_and_unrelated_maps_are_unchanged():
    D=module()
    for zone in ('hive/h_int/hive1_2_2','hive/h_int/hive2_2_4','invented/zone'):
        r=world();before=C.encode_xmlb(r);assert D.convert(r,zone,{})==0 and C.encode_xmlb(r)==before


def test_relay_validator_rejects_unknown_marker_and_orphan_action():
    D=module();r=world();D.convert(r,'sewers/grso/sewers3_1_1',{})
    ET.SubElement(r,'entity',name='invented_extra',classname='actionent',**{D.MARKER:'poll'})
    g=ET.SubElement(r,'entinst',type='invented_extra');ET.SubElement(g,'inst',name='invented_extra',pos='0 0 0')
    assert D.problems(r,'sewers/grso/sewers3_1_1')


def test_nuke_missing_panel_fails_closed_even_if_optional_door_is_loaded():
    D=module();r=world('blastdoor_nuke_n04');scripts={};D.convert(r,'nuke_plant/nuke/nuke2_2',scripts)
    for text in scripts.values():
        trace,_=run(text,enabled=0,panel_loaded=-1)
        assert not any(x[0]=='act' for x in trace),trace
