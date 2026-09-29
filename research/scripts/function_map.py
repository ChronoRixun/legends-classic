"""Emit function_map.json: every XML1 script function that XMen2.exe does not register (or registers
differently), with the XML2 replacement used by rewrite_scripts.py and the evidence behind it."""
import json, os, collections
HERE = os.path.dirname(os.path.abspath(__file__))
A1 = json.load(open(os.path.join(HERE, 'xml1_api.json')))
A2 = json.load(open(os.path.join(HERE, 'xml2_api.json')))
SA = json.load(open(os.path.join(HERE, 'script_analysis.json')))
IN = json.load(open(os.path.join(HERE, 'inline_scan.json')))
use = collections.Counter()
for c in ('xml1_loose', 'xml1_assets_only'):
    use.update(SA[c]['S']['func'])

M = {
 'screenFade': ('cameraFade(a, b)', 'XML1 registers screenFade and cameraFade to the same function (xbe 0x98ec0); XML2 cameraFade 0x49df70 has identical body'),
 'getMissionVar': ('packed getGameFlag bits / getZoneVar (see var_storage.json)', 'XML1 mission store == XML2 zone store (xbe 0xcac70/0xcb780 vs exe 0x4d6840/0x4d7060, 32 names, <12 chars) but XML2 clears it on every zone load (0x49fe70) while XML1 clears only on map-directory change (xbe 0x99b90 + dir compare 0x824c0)'),
 'setMissionVar': ('packed setGameFlag bits / setZoneVar', 'as getMissionVar; XML2 has no int game-var setter, game vars are only reachable bit-wise (setGameFlag 0x4a0120 -> 0x4d7130)'),
 'getMissionFlag': ('getGameFlag(name, bit)', 'identical bit code (xbe 0x98cb0 vs exe 0x4a0190: bit 1..32, returns 0/1); same name kept so conversation conditions disallowResponseOnVar(name,bit) keep working (exe 0x49da20 checks game store first)'),
 'setMissionFlag': ('setGameFlag(name, bit, value)', 'identical bit code (xbe 0x98d20 vs exe 0x4a0120)'),
 'getGameVar': ('packed getGameFlag bits in x1g* game vars', 'XML1 game store (xbe 0xcacd0, 16 names) ~ XML2 game store (0x4d68a0, 100 names) but XML2 exposes it only through get/setGameFlag'),
 'setGameVar': ('packed setGameFlag bits in x1g* game vars', 'see getGameVar'),
 'createPopupDialog': ('createPopupDialogXml("x1/pNNN") + generated Dialogs/x1/pNNN.XMLB/.engb', 'XML2 only has XML-file dialogs (createPopupDialogXml 0x4a6890); dialog XML schema identical in both exes (attrs text/cancancel/autohide/scriptok/scriptcancel/filter/hud, <option text script>)'),
 'addPopupDialogOption': ('<option text=.. script=..> in the generated dialog', 'option scripts run as console "runscript %s" (xbe 0x1877e0, exe 0x5eb8e3) -> must be one whitespace-free token'),
 'canCancelDialog': ('cancancel="true|false" attribute', 'xbe 0x99350 sets popup->vtbl+0x34(bool)'),
 'showPopupDialog': ('(part of createPopupDialogXml)', ''),
 'beginMission': ('setCurrentAct(act) + objective resets + scriptstart body / loadMapKeepTeam(mapload) (scripts/x1/missions/begin_<m>.py)', 'XML2 beginMission (0x4a0af0) queues console "beginmission %s" but no such command is registered in XMen2.exe (only format string at 0x68d2e8); XML1 handler xbe 0x18da90 loads data/missions/<m> then runs scriptstart'),
 'beginMissionHack': ('as beginMission', 'same; console command not registered'),
 'beginSideMission': ('begin block of the side mission', 'XML1 "beginsidemission" = pushsidemission + beginmission (xbe 0x18dd70); XML2 only pushes via extractionPointChange (0x4a7020)'),
 'endSideMission': ('setCurrentAct(parent act) + loadZone(caller zone, "")  (fallback restorelastzone)', 'XML2 restorelastzone handler 0x5f4580 is the XML1 endsidemission handler (xbe 0x18df20) renamed; without a pushed side mission it has nothing to restore, so returns are resolved statically'),
 'setInCampaign': ('unlockCharacter(hero, "")', 'XML1 0x99460 and XML2 0x49f520 both call registry->vtbl+0x2c(registry->vtbl+0x3c(name)); "FALSE" is a no-op in XML1'),
 'addHero': ('unlockCharacter + extractionPointLite(_ACTIVE_HERO_,true,false,false) (team menu)', 'XML1 0x99a00 game->vtbl+0x110(name); no XML2 script function reaches the party-add method'),
 'exitSoloMode': ('removed', 'no XML2 solo-mode script API (XML1 0x9ef70)'),
 'enterSoloMode': ('removed (inline data only)', 'no XML2 solo-mode script API (XML1 0x9eef0)'),
 'setPowerStatus': ('removed', 'no XML2 per-power enable/disable (XML1 0x9db60)'),
 'removeFromGroup': ('removed', 'no XML2 equivalent (XML1 0x9fbd0)'),
 'destroyMultipartPiece': ('setSegmentVisible(e,hideSkin,"0"); setSegmentVisible(e,showSkin,"1"); spawnEffectBone(e,bone,effect)', 'npcstat <Multipart> of Juggernaut: hideSkin 3401_helmet, showSkin 3401_head, effectOnDeath explode/JuggernautHelmet, bone Bip01 Head'),
 'xtremeConversationLight': ('removed', 'no XML2 equivalent (XML1 0x9e310)'),
 'displayEx': ('removed', 'XML1 stub: xbe 0x2123a0 = xor eax,eax; ret'),
 'magnetoBall': ('removed', 'XML1 stub: xbe 0x2123a0'),
 'mission': ('comment (blackbird-menu mission state)', 'XML1 0x99420 -> mission manager vtbl+8(name,state); XML2 has no mission-list state'),
 'loadMap': ('loadMapKeepTeam(map)', 'XML1 loadMap sends "loadmap %s" (xbe 0x9a850, extra args default 0 0); XML2 loadMap sends "loadmapaddteam %s" (no such command registered) and loadMapKeepTeam sends "loadmap %s 0 0" (0x4a0cc0)'),
 'extractionPointLite': ('first 4 args kept', 'XML1 sig asssss (xbe 0x9f4a0) vs XML2 asss (0x4a6d80); mapping of the flags unverified'),
 'restartMission': ('(unused by XML1 content)', 'XML1 0x9a6e0 clears mission vars + "beginmission <current>"'),
}
out = {}
for n, (rep, ev) in M.items():
    out[n] = {'xml1_sig': (A1.get(n, {}).get('ret', '?') + '(' + A1.get(n, {}).get('args', '') + ')') if n in A1 else None,
              'xml2_sig': (A2[n]['ret'] + '(' + A2[n]['args'] + ')') if n in A2 else None,
              'xml1_script_calls': use.get(n, 0), 'xml1_inline_data_calls': IN['calls'].get(n, 0),
              'xml2_replacement': rep, 'evidence': ev}
json.dump(out, open(os.path.join(HERE, 'function_map.json'), 'w'), indent=1)
for n, v in out.items():
    print(f"{n:24} {str(v['xml1_sig']):10} -> {str(v['xml2_sig']):10} scripts {v['xml1_script_calls']:4} inline {v['xml1_inline_data_calls']:4}  {v['xml2_replacement'][:70]}")
