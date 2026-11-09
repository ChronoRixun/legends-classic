"""Synthetic data/script activation graphs and conservative stream-distance warnings."""
import xml.etree.ElementTree as ET


def module():
    from xml1build import streamed_unlocks
    return streamed_unlocks


def world():
    return ET.fromstring('''<world>
      <entity name="switch" classname="gameent" actonuse="true" acttargets="relay"/>
      <entity name="relay" classname="enabletargetent" acttargets="door" enable="true"/>
      <entity name="door" classname="doorent" startenabled="false"/>
      <entinst type="switch"><inst name="switch" pos="0 0 0"/></entinst>
      <entinst type="relay"><inst name="relay" pos="1950 0 0"/></entinst>
      <entinst type="door"><inst name="door" pos="2000 0 0"/></entinst>
    </world>''')


def test_data_relay_uses_original_firing_position_instead_of_relay_position():
    D=module();rows=D.audit(world(),lambda ref:None)
    assert len(rows)==1 and rows[0]['target']=='door' and rows[0]['distance']==2000,rows
    assert rows[0]['sources']==['switch']


def test_all_possible_sources_must_be_far_and_boundary_is_strict():
    D=module();r=world();g=r.find('entinst')
    ET.SubElement(g,'inst',name='second',pos='1350 0 0')
    assert not D.audit(r,lambda ref:None)
    g[-1].set('pos','1349 0 0');assert D.audit(r,lambda ref:None)[0]['distance']==651


def test_authored_residency_and_valid_durable_relay_cover_targets():
    D=module();r=world();r.findall('entity')[-1].set('smartent','false')
    assert not D.audit(r,lambda ref:None)
    r=world();assert not D.audit(r,lambda ref:None,covered={'door'})
    # Resident actionents are not accidentally treated like streamed physents.
    r.findall('entity')[-1].set('classname','actionent');assert not D.audit(r,lambda ref:None)


def test_script_chains_and_inline_scripts_share_runner_origins():
    D=module();r=world();e=r.find('entity');e.attrib.pop('acttargets');e.set('actscript','invented/start')
    scripts={'invented/start':'runscript("invented/finish")', 'invented/finish':'setEnable("door", "TRUE")'}
    rows=D.audit(r,scripts.get);assert len(rows)==1 and rows[0]['distance']==2000,rows
    e.set('actscript','act("relay", "relay")');rows=D.audit(r,scripts.get)
    assert len(rows)==1 and rows[0]['target']=='door'


def test_script_unlock_and_death_targets_include_all_placements_and_break_cycles():
    D=module();r=world();e=r.find('entity');e.attrib.pop('acttargets');e.set('deathscript','invented/finish')
    scripts={'invented/finish':'unlock("door")\nrunscript("invented/finish")'}
    assert D.audit(r,scripts.get)[0]['distance']==2000
    e.attrib.pop('deathscript');e.set('deathtargets','relay');e.set('classname','physent')
    assert D.audit(r,scripts.get)[0]['distance']==2000


def test_unknown_zone_script_origin_is_reported_without_inventing_distance():
    D=module();r=world()
    rows=D.audit(r,lambda ref:'act("door")',zone_script='invented/entry')
    assert any(row['distance'] is None and row['source']=='script:invented/entry' for row in rows),rows


def test_conversation_callback_inherits_caller_position_and_packaged_scripts_are_scanned():
    D=module();r=world();e=r.find('entity');e.attrib.pop('acttargets');e.set('actscript','invented/talk')
    scripts={'invented/talk':'startConversation("invented/conversation")',
             'invented/choice':'setEnable("door", "TRUE")'}
    conv=ET.fromstring('<conversation><option script="invented/choice"/></conversation>')
    rows=D.audit(r,scripts.get,read_conversation=lambda ref:conv)
    assert len(rows)==1 and rows[0]['distance']==2000,rows
    e.attrib.pop('actscript')
    rows=D.audit(r,scripts.get,extra_scripts=['invented/choice'])
    assert any(row['distance'] is None for row in rows),rows


def test_zone_entry_origin_remains_unknown_when_same_script_has_a_nearby_caller():
    D=module();r=world();e=r.find('entity');e.attrib.pop('acttargets');e.set('actscript','invented/entry')
    r.find('entinst')[0].set('pos','1900 0 0')
    rows=D.audit(r,lambda ref:'act("door")',zone_script='invented/entry')
    assert len(rows)==1 and rows[0]['distance'] is None,rows
    assert 'switch' in rows[0]['sources'] and any('entry' in s for s in rows[0]['sources'])


def test_enabling_a_nearby_manual_switch_does_not_fire_its_activation_chain():
    D=module();r=world();r.find('entinst')[0].set('pos','1900 0 0')
    rows=D.audit(r,lambda ref:'setEnable("switch", "TRUE")',zone_script='invented/entry')
    assert not rows,rows
    # Enabling the far physical door itself still needs a review of zone-entry position.
    rows=D.audit(r,lambda ref:'setEnable("door", "TRUE")',zone_script='invented/entry')
    assert len(rows)==1 and rows[0]['distance'] is None,rows
