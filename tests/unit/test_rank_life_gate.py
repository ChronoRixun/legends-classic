"""Synthetic later-rank effects must never apply an infinite zero-life attachment."""
import xml.etree.ElementTree as ET
from xml1build import heroes as H, mind_control as MC


def fixture(kind='powerup', first=3):
    root=ET.Element('PowerStyle')
    for rank in range(1,6):
        m=ET.SubElement(root,'FightMove',name=f'cast{rank}', **({'inherit':f'cast{rank-1}','fallback':f'cast{rank-1}'} if rank>1 else {'animenum':'ea_power1','icon':'0'}))
        ET.SubElement(m,'require',cat='talent',item='invented',level=str(rank))
        if rank==first:
            ET.SubElement(m,'trigger',name=kind,tag='8',life='9',powerup='fear',apply_chance='0.75')
    sc=H.StyleCollapse('frost',root,H.Values(ET.Element('values')),{'invented':{'power':'0','levels':5}},set())
    style=sc.run(); assert not sc.report['errors']
    talents=ET.Element('talents');talent=ET.SubElement(talents,'talent',name='invented',maxlevel='5')
    for name,table in sc.talentvalues['invented'].items():
        for rank,value in table.items():ET.SubElement(talent,'talentvalue',name=name,level=str(rank),value=value)
    return style,talents


def resolve(talents,ref,rank):
    if not ref.startswith('%'):return float(ref)
    return float(next(x.get('value') for x in talents.iter('talentvalue') if x.get('name')==ref[1:] and x.get('level')==str(rank)))


def test_later_rank_effect_gates_application_and_preserves_authored_active_values():
    for kind in ('powerup','taunt'):
        style,talents=fixture(kind);t=next(style.iter('trigger'))
        for rank in range(1,6):
            assert resolve(talents,t.get('apply_chance','1'),rank)==(-1 if rank<3 else 0.75)
            assert resolve(talents,t.get('life'),rank)==(0 if rank<3 else 9)
        assert not MC.zero_life_problems(style,talents)


def test_zero_life_validator_checks_every_rank_and_requires_exact_negative_one():
    for gate in (None,'0','1','-0.5'):
        style,talents=fixture();t=next(style.iter('trigger'));t.set('life','%invented_life')
        t.attrib.pop('apply_chance',None)
        if gate is not None:t.set('apply_chance',gate)
        for r,v in ((1,'0'),(2,'9'),(3,'0'),(4,'9'),(5,'9')):ET.SubElement(talents,'talentvalue',name='invented_life',level=str(r),value=v)
        errors=MC.zero_life_problems(style,talents)
        assert len(errors)==2,errors
        assert 'rank 1' in errors[0] and 'rank 3' in errors[1]
    t.set('apply_chance','-1');assert not MC.zero_life_problems(style,talents)


def test_zero_life_validator_resolves_ranges_and_missing_gate_references():
    style,talents=fixture();t=next(style.iter('trigger'));t.set('life','0 8');t.set('apply_chance','%missing')
    assert MC.zero_life_problems(style,talents)
    t.set('life','9');t.attrib.pop('apply_chance');assert not MC.zero_life_problems(style,talents)
