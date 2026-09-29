"""Assemble research/sweep/inventory.json from the component results."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import collections, json, os

S = _REPO + r'/research/sweep'


def J(n):
    return json.load(open(os.path.join(S, n)))


zones = J('zones.json')
graph = J('graph.json')
agg = J('aggregate.json')
coll = J('collisions.json')
parse = J('parse_results.json')
extra = J('parse_extra.json')
sf = J('script_functions.json')
calls = J('script_calls.json')
movies = J('movies.json')
ui = J('ui_inventory.json')
fbc = J('fb_conflicts.json')
syn = J('script_syntax.json')
reach = graph['reachable_from_new_game']
reach_set = set(reach)
order = {z: i for i, z in enumerate(reach)}
cfiles = coll['files']

per_zone = {}
for z, r in sorted(zones.items()):
    chars = sorted(set(c.lower() for c in r.get('chr_characters', []) + r.get('spawner_characters', [])))
    cd = agg['characters']['detail']
    w = r.get('world') or {}
    kept_diff = [k for k in r.get('kept_xml2', []) if cfiles.get(k, {}).get('status') == 'different']
    empty = [n for n, v in fbc['empty_entries'].items() if n.startswith('maps/' + z + '.')]
    sc = r.get('scripts') or {}
    per_zone[z] = {
        'category': r['category'],
        'reachable_from_new_game': z in reach_set,
        'new_game_order': order.get(z),
        'convert': r['convert'],
        'convert_error': r.get('error'),
        'zone_xml': r.get('zone_xml'),
        'files_written': r.get('written'),
        'world': {k: w.get(k) for k in ('mission', 'soundfile', 'zonescript', 'automap_texture', 'automap_offset',
                                         'level', 'skybox') if w.get(k) is not None},
        'characters': chars,
        'characters_missing_in_xml2_stats': [c for c in chars if not cd.get(c, {}).get('in_xml2_stats')],
        'sound_bank': (r.get('sounds') or {}).get('soundfile'),
        'sound_bank_in_xml1': agg['sound_banks']['zone_soundfiles'].get(((r.get('sounds') or {}).get('soundfile') or '').lower(), {}).get('in_xml1'),
        'sound_bank_in_xml2': agg['sound_banks']['zone_soundfiles'].get(((r.get('sounds') or {}).get('soundfile') or '').lower(), {}).get('in_xml2'),
        'music': (r.get('sounds') or {}).get('music'),
        'sound_ref_count': (r.get('sounds') or {}).get('refs'),
        'movies': r.get('movies'),
        'script_files': sc.get('files'),
        'script_files_missing': sc.get('missing_files'),
        'inline_scripts': sc.get('inline'),
        'script_functions_missing_in_xml2': sc.get('missing_in_xml2'),
        'script_signature_changed': sc.get('signature_changed'),
        'links_out': sorted({l['target'] for l in r.get('links', []) if l.get('target') and l['kind'] != 'prevzone'
                             and (l['kind'] != 'zonelink' or l['instanced'])}),
        'prevzones': sorted({l['target'] for l in r.get('links', []) if l['kind'] == 'prevzone' and l.get('target')}),
        'missions_begun': sorted({l['raw'] for l in r.get('links', []) if l['kind'] == 'mission'}),
        'zone_successors_via_scripts_convs_dialogs': graph['zone_edges'].get(z, []),
        'refs_missing_everywhere': r.get('refs_missing'),
        'refs_status_counts': r.get('refs_status_counts'),
        'xml2_version_kept_but_different': kept_diff,
        'empty_source_files': empty,
    }

text_fail = {k: v for k, v in parse.items() if not v['ok']}
inv = {
    'generated_by': 'research/sweep/*.py (sweep.py, graph.py, collisions.py, aggregate.py, ui_inventory.py, movies.py, '
                    'script_table.py, stubs.py, fb_conflicts.py, verify_parse.py, script_syntax.py)',
    'summary': {
        'map_bundles': len(zones) + len(ui['menu_packages']),
        'zones_converted': len(zones),
        'zones_convert_errors': sum(1 for r in zones.values() if r['convert'] != 'ok'),
        'zones_by_category': dict(collections.Counter(r['category'] for r in zones.values())),
        'zones_reachable_from_new_game': len(reach),
        'missions_reachable_from_new_game': len(graph['reachable_missions']),
        'characters_needed': agg['characters']['total'],
        'characters_missing_from_xml2_stats': sum(1 for d in agg['characters']['detail'].values() if not d['in_xml2_stats']),
        'xml1_engine_functions_absent_in_xml2': sum(1 for k in calls['xml1_missing_in_xml2']
                                                     if k.lower() in {x.lower() for x in sf['xml1']}),
        'xml1_calls_to_absent_engine_functions': sum(v['calls'] for k, v in calls['xml1_missing_in_xml2'].items()
                                                     if k.lower() in {x.lower() for x in sf['xml1']}),
        'text_xml_files_scanned': len(parse),
        'text_xml_stock_parser_failures': len(text_fail),
        'empty_source_files': len(fbc['empty_entries']),
    },
    'new_game': {
        'xml1': {'menu': 'ui/menus/main.eng item button1 usecmd="newgame"',
                 'handler': 'default.xbe 0x18d0b0 (registered at 0x18e217) -> console "beginmission alison" '
                            '(0x18d118; "beginmissionhack demo" if [0x498db0] != 0)',
                 'mission': 'data/missions/alison.eng scriptstart="missions/alison"',
                 'script': 'scripts/missions/alison.py: startMovie("r102"); loadMap("nyc/alison/nyc1_1_1")',
                 'start_zone': graph['new_game']['start_zone'], 'first_movie': 'r102'},
        'xml2': {'menu': 'UI/menus/main.engb item label_option04 usecmd="newgame"',
                 'handler': 'XMen2.exe 0x5f3610 (registered at 0x5f491d) -> difficulty dialog -> '
                            '"runscript startFirstMission()" (0x5f3d19) -> startFirstMission handler 0x4a7b10',
                 'start_zone': 'act0/tutorial/tutorial1 (zoneinfo state="2" is unique to it; tools/build_test.py relies on it)'},
    },
    'graph': {k: graph[k] for k in ('reachable_from_new_game', 'reachable_missions', 'unreachable_by_category',
                                    'unresolved_zone_refs', 'movies_reachable', 'zone_edges')},
    'missions': graph['missions'],
    'mission_start_zones': graph['mission_start_zones'],
    'text_xml': {
        'stock_parser_failures': {k: {'err': v['err'], 'context': v.get('context')} for k, v in text_fail.items()},
        'strict_parser_failures_fixed_by_amp_escape': sorted(k for k, v in parse.items() if v['strict_err'] and v['ok']),
        'stray_tail_text': extra['text_nodes'],
        'attr_case_collisions': extra['attr_case_collisions'],
        'multi_root_files': len(extra['multi_root_files']),
        'high_byte_histogram': extra['high_bytes_by_ext'],
        'empty_files': fbc['empty_entries'],
        'fix': 'research/sweep/sweeplib.py normalise_text_xml(): verified on all 3989 files by verify_parse.py',
    },
    'collisions': {'summary_by_category': coll['summary_by_category'], 'data_tables': coll['data_collisions'],
                   'skipped_fre_ger': coll['skipped_fre_ger'],
                   'different_files': sorted(k for k, v in cfiles.items() if v['status'] == 'different'),
                   'identical_files': sorted(k for k, v in cfiles.items() if v['status'] == 'identical')},
    'script_functions': {
        'xml1_table_size': len(sf['xml1']), 'xml2_table_size': len(sf['xml2']),
        'record_layout': '{handler, name, ret_sig, arg_sig}; XML1 table VAs 0x3d0b8c.., XML2 0x68a90c..',
        'xml1_calls_absent_in_xml2': calls['xml1_missing_in_xml2'],
        'signature_changes': {k: [sf['xml1'][k]['args'], sf['xml2'][k]['args']] for k in sf['xml1']
                              if k in sf['xml2'] and sf['xml1'][k]['args'] != sf['xml2'][k]['args']},
        'xml2_stub_functions': sorted(k for k, v in sf['xml2'].items() if v.get('stub')),
        'per_zone_counts': agg['scripts'],
        'syntax_features': {'xml1': syn['xml1'], 'xml2': syn['xml2']},
    },
    'characters': agg['characters'],
    'actors_skins': agg['actors'],
    'sound': agg['sound_banks'],
    'movies': {'xml1': movies['xml1'], 'xml2': movies['xml2']},
    'ui': ui,
    'fb_bundle_conflicts': {'conflicting_names': list(fbc['conflicts']), 'demo_variant_kept': fbc['demo_variant_kept']},
    'kept_xml2_versions': agg['kept_xml2_versions'],
    'zones': per_zone,
}
json.dump(inv, open(os.path.join(S, 'inventory.json'), 'w'), indent=1, sort_keys=True)
print(json.dumps(inv['summary'], indent=1))
print('inventory.json bytes', os.path.getsize(os.path.join(S, 'inventory.json')))
