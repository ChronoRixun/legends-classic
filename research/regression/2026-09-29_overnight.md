# Overnight regression runs, 2026-09-29 (integration build `_int1`)

Build under test: `build/_int1` = main at 2d87da5 (tonight's merges: allinone starts, joinHero joins, NPC doubles
SPEC 18.1, automaps SPEC 26, front end without the difficulty prompt + Play Online item + credits fixes, save texts),
`--no-movies --frontend xml1`, validator 0 errors. DLL xml2-fix 00b2646 (scratchpad `dll/dinput_00b2646.dll`, md5
7879b351: Discord presence, virtual pads, window title, [Online] GameVersion, 8-item menu, one ini-comment rule,
NewGamePlus, XInput off the game thread). Harness: `harness.py install <build> --limits --dll <DLL> --pipe-name reg`
(test save folder "X-Men Legends (port tests)", `[Discord] Enabled=0`). Every tool reached the game through
`XML2FIX_PIPE=reg`; all of them go through `fixinput.PIPE`, which reads that variable, so no tool needed a change.

One game window at a time. The tools were run through a wrapper (`build/reg_scripts/regwrap.py`, from the session
scratchpad) that only narrows `current_zone.game_pid()` and `tour_runner.kill_game()` to the
build's own XMen2.exe (by default they take the first XMen2.exe / kill every XMen2.exe, and other agents had builds of
their own tonight). No file under `tools/` was edited. The walk re-runs used the wrapper's keep-alive modes (below).

## Summary

| run | baseline | tonight (as the tool runs it) | tonight (hero kept alive) | verdict |
|---|---|---|---|---|
| zone tour, one session | 154/154 ok, 1 session (`build/tour_limits`) | 149 ok, 2 ok-no-hud, 2 load-failed, 3 sessions, 0 crashes (`build/reg_tour`) | **154/154 ok, 1 session, 0 crashes** (`build/reg_tour_inv`) | no zone regression |
| campaign walk, 73 starts | 55 ok, 14 bounced, 3 party-mismatch, 4 skipped, 1 restore-failed; sides 5/6 (`build/walk1`) | 53 ok, 14 bounced, 3 party-mismatch, 4 skipped, 2 load-timeout, 1 conv-stuck; sides **6/6**; 0 crashes (`build/reg_walk`) | **56 ok, 14 bounced, 3 party-mismatch, 4 skipped, 0 failures; sides 6/6** (`build/reg_walk_inv` + `build/reg_walk_chain`) | no regression; astral_sk fixed |
| power sweep, 16 heroes | 64/64 (powers_all 51 + powers_redo / powers_nb2 re-runs) | 59/64 default options (`build/reg_powers`); the 5 boosts re-run with the redo options: 20/20 (`build/reg_powers_redo`) | - | **64/64**, no regression |

Crashes: none in any run (every gamedbg log ends in `EXIT code 0x1` = the harness's taskkill).

The one behaviour change that shows up in every unattended run: **NPC attacks now hurt** (SPEC 24 NPC power values,
5e3b9cc, and SPEC 22.7 NPC powerups, fdafc3e - both newer than the tour and walk baselines, which ran when XML1 NPC
attacks read 0 damage). An idle hero now dies in hostile zones, and the tools don't protect it: the tour's HUD test
reads a low health bar as "no HUD", and a dead party leaves the game on the game-over dialog. That is
intended game behaviour, not a regression - but the tour and the walk need the hero kept alive to test what they
are meant to test (see "Tool follow-ups").

## 1. Zone tour

The tour needs a `--tour` build, and `_int1` is a normal build, so a tour variant was built from main HEAD
(7e40eb1): `build_xml1.py --out build/_int1_tour --no-movies --frontend xml1 --xp-curve xml1 --tour 12` (290 s,
validator 0 errors). Since 2d87da5 only `tools/harness.py` and docs changed, so its content is `_int1`'s plus the tour
hooks; its 162 stops are the baseline's (`build/xml1_tour/_tour.json`) in the same order. Harness as above.

### Run A - as the tool runs it (`build/reg_tour`)
149 ok, `weapon_x/wfb/wx1_3` and `mastermold/mastermold2` ok-no-hud, `nuke_plant/nuke/nuke1_2` and
`astroid_m/visit1/asteroid2_3` load-failed, `nuke_plant/nuke/nuke1_1` not recorded; sessions started 01:03:38,
01:20:08 (index 68) and 01:41:25 (index 160); no crash. All four failures are Wolverine (level 1, alone) dying:
- the last frame of the run (`build/reg_tour/shots/_last_live_mastermold2.png`, mastermold2) is "All X-Men have been
  eliminated. Load Game / Main Menu" with Master Mold behind it; the dialog pauses the tour stop's `waittimed`, so the
  next stop never loads (asteroid2_2 -> 2_3 stalled the same way; its HUD shot shows an Acolyte walking up,
  `shots/158_astroid_m_visit1_asteroid2_2.png`).
- replay of the first stall from a fresh game (`build/reg_scripts/tour_repro.py`, `build/reg_tour/repro_wx1_2`):
  wx1_2 -> nuke1_1 -> wx1_3 -> nuke1_2 -> danger_room -> nuke1_3 -> nuke1_4 all load; in nuke1_1's 12 s the guards
  take the health bar from 68 px to 40 px (frames 005-010). With the damage carried from 65 earlier zones, Wolverine's
  bar fell below the HUD test's threshold in nuke1_1 (`tour_runner.hud_visible` looks for red fill in 16-26 % of
  the width, so a low bar = "no HUD": nuke1_1 never counted) and he died in wx1_3.
- Baseline tour: NPC attacks did no damage (before SPEC 24), so nobody died.

### Run B - hero invulnerable (`build/reg_tour_inv`)
Each tour stop script got `waittimed(0.5)` + `setInvulnerable("_ACTIVE_HERO_", "TRUE")` + `waittimed(11.5)` (same
12 s dwell; the build's tour scripts were put back afterwards).
Checked first on nuke1_1 -> wx1_3 -> nuke1_2: health stays 68 px (`build/reg_tour/repro_invuln_nuke1_1`).

**154/154 ok in ONE session** (01:49:16 - 02:27:30), identical zone set and statuses to the baseline, no crash.
Actor-table peak 28/127 at `mansion/man4/mansion4_1` - the baseline's peak, same zone (`slots.csv`). xml2-fix.log
(`build/reg_tour_inv/xml2-fix.log`): no warnings or errors; XInput ready "after 0 ms on thread ... (its own, not the
game's)"; title "X-Men Legends"; frame rate 59.9 at the cap. The HUD small map (automaps) is in every shot.

Zone change -> HUD: median 1.3 s (baseline 1.2 s, run A 1.2 s). 14 zones took 3.4-6.5 s in run B only (acts 6-8
riot / sewer / mansion zones with enemies at the start, e.g. `nyc/riots/nyc3_1_2` 6.5 s; run A 0.0 s for the same
zone on the same build) - measurement noise (most likely hits flashing the invulnerable hero's bar, or the sound agent's
conversion jobs running at the time), not a load regression.

## 2. Campaign walk (73 mission starts)

`campaign_walk.py build/_int1 build/reg_walk` (defaults, as walk1). The baseline ran on `build/_nb` (09-28 ~13:00,
before SPEC 22.7/24, forced-party fixes e6fb724, XPCurve, the XML1 front end).

### As the tool runs it (`build/reg_walk`, 02:28 - 03:42, 5 launches, 0 crashes)
Status counts: ok 53, bounced 14, party-mismatch 3, skipped 4, load-timeout 2, conv-stuck 1 (baseline ok 55, bounced
14, party-mismatch 3, skipped 4, restore-failed 1). The 14 bounced briefings, the 3 party-mismatches
(astral_wx_briefing / astral_briefing / asteroid_briefing: the next mission's forced party after the briefing) and the
4 cut missions are the baseline's, mission for mission, zone for zone. Launches 2-5: 3 x "2 failed starts in a row"
(bounced briefings, as in the baseline) and 1 after conv-stuck.

Better than the baseline: **astral_sk restore-failed -> ok, side mission restored** (e6fb724's push ahead of the r504
movie): side missions **6/6** restored (jug_fb, dr_mag1, sent_fb, wx_fb_start, muir2_reboot, astral_sk).

Worse than the baseline - one chain in launch 3, all from one death:
| # | mission | baseline | tonight | evidence |
|---|---|---|---|---|
| 44 | sentinels_mansion | ok, magma lv 1 | ok, magma **lv 5**, fighting the Sentinels | `shots/044_sentinels_mansion.png`: "MAGMA LEVELED UP!" x2, "Press [F1] to Level Up", Sentinels hit |
| 45 | sentinel_mansion | ok (conversation, 17 presses) | **load-timeout**, party empty | `shots/045_sentinel_mansion.png`: the blackbird team menu with 4 empty slots; Enter can't accept an empty party; getPartyMember 0-3 all "" (log 03:04:24) |
| 46 | mansion5 | ok | ok, but ... | `shots/046_mansion5.png`: the no-save-data message = the walk's Enter chose Load Game on the game-over dialog |
| 49 | rescue_healer | ok | **load-timeout**, party empty | `shots/049_rescue_healer.png`: same empty team menu |
| 50 | mount | ok, magma | ok, **party empty** (a false pass: keep start) | `shots/050_mount.png`: black zone, empty portrait |
| 51 | mansion6 | ok | **conv-stuck** | `shots/051_mansion6_conv.png`: the game-over dialog over Frost's conversation |

Cause: Magma (alone) was killed by the Sentinels in `mansion/man5/mansion_front5` while the walk idled through
sentinels_mansion / sentinel_mansion (SPEC 24: Sentinel attacks now do XML1's damage; XPCurve=xml1's kill XP levelled
her to 5 on the way). The blackbird team menu then drops the dead hero (empty party, no Accept), and each later
`seatParty("magma", ...)` in that session re-seated the dead Magma -> the game-over dialog at once.
Launch 4 (fresh game) ends it: every start after it matches the baseline.

### Hero kept alive (`build/reg_walk_inv`)
Two re-runs, because the first keep-alive was not enough:
- `regwrap.py walkinv` = campaign_walk with `setInvulnerable("_ACTIVE_HERO_","TRUE")` sent after every settle
  (`build/reg_walk_inv`, 04:01 - 05:10, 4 launches, 0 crashes): ok 54, bounced 14, party-mismatch 3, skipped 4,
  rescue_healer load-timeout, mansion6 conv-stuck, mount a false pass (party empty). sentinel_mansion is ok now, but
  Magma reached it at "MAGMA NEEDS HEALTH!", level 4 (`shots/045_sentinel_mansion.png`): the damage came in before the
  protection took hold (sentinel_mansion reloads the zone she is in, and the reload's new actor is unprotected until
  the next settle). By mansion5 she was dead, and the same chain followed ("No X-Men Legends save data
  present" = Enter on Load Game in the death dialog, `shots/046_mansion5.png`).
- mansion5 by itself from a fresh game (`build/reg_walk_inv/repro_mansion5`, `console runscript
  x1/missions/begin_mansion5`): HUD up in 2 s and for the next 45 s, Magma alive. mansion5 is fine; it only
  inherited the dead party.
- `regwrap.py walkinv2` (`setInvulnerable` + `restoreHealth("_ACTIVE_HERO_",10000)` before every start and after every
  settle), `--from end_astral --to mansion6` on a fresh game (`build/reg_walk_chain`, 05:17 - 05:25): end_astral bounced
  (as in the baseline), then sentinels_mansion, sentinel_mansion, mansion5 (20 s, baseline 19.8 s),
  healer_briefing, rescue_healer, mount (magma) and mansion6 all **ok**, with the baseline's party and zone.

Merged (reg_walk_inv, with reg_walk_chain for missions 43-51): **ok 56, bounced 14, party-mismatch 3, skipped 4, no
failure**. Every mission's status, party and final zone match the baseline except astral_sk (restore-failed -> ok,
restored). Side missions 6/6. The seated parties (41 seat starts) are XML1's, as in the baseline.

## 3. Power sweep (16 heroes, 64 slots)

`power_sweep.py build/_int1 build/reg_powers` (defaults, as powers_all), one launch, no crash: **59 fired, 5
no-energy-change** (baseline powers_all with the same options: 51 fired, 13 no-energy-change). The 5 are all boost
slots (left, power3): Beastial Feats, Bait (Jubilee), Telekinetic Shield (Phoenix), Psychic Defense (Psylocke),
Bullet Proof (Rogue) - the same kind the baseline re-ran. The post-burst frame is read while the HUD still shows the lost energy as a grey trail, so the
"after" energy is unreadable ("-"); the saved post frame shows the drop (`build/reg_powers/_beast_left_hud_zoom.png`:
pre / last burst frame / post). Re-run of those 5 with the baseline redo's options (`--frames 30 --frame-gap 0.06
--post-wait 2.5 --keep-full`, as powers_redo / powers_nb2): **20/20 fired** (`build/reg_powers_redo`; boosts 1.00 ->
0.44 / 0.61 / 0.66 / 0.44 / 0.31).

Combined: **64/64 fired** - Magma's Lava Fissure fires (1.00 -> 0.82 after), every Xtreme by its banner. Slots the
baseline only passed on a quick-power fallback or not at all now fire from the wheel (frost Fear, ProfXAstral Psychic
Smash, ProfXGladiator Psychic Defense). Energy drops per slot differ from the baseline only by capture timing (the
lowest burst frame vs the after frame); no power lost its cost or its effect.

## Regressions

**None found in the port content or the DLL.** Every tour zone loads in one session (154/154, the baseline's peak of
28 actor slots), every mission start gives the baseline's zone and party (plus astral_sk fixed), every hero power
fires (64/64), and no crash: 19 launches between 01:03 and 05:25, every gamedbg log ends in the harness's taskkill.

Differences that are not regressions:
- **Unattended heroes die now** (SPEC 24 NPC power values 5e3b9cc / SPEC 22.7 NPC powerups fdafc3e, intended). It
  broke the tour as the tool runs it (4 stops, 2 restarts) and the walk (sentinel_mansion, rescue_healer, mansion6 +
  mount's false pass). Hostile starts seen: nuke1_1's guards take about 40 % of a level-1 Wolverine's health in 12 s;
  `mansion/man5/mansion_front5`'s Sentinels kill a lone, idle Magma within one to two minutes (she levels 1 -> 4-5 from the kill XP on
  the way, XPCurve=xml1). In real play the player fights, and that mission's party comes from the team menu.
- Power sweep default options: 5 boost slots read as no-energy-change (a measurement limit that the baseline's
  default run also had, with 13 slots); with the redo options they fire.
- Tour run B: 14 zones reached the HUD 3.4-6.5 s after the zone change (run A: 0-1.2 s on the same build) -
  measurement noise, see section 1.
- New in the frames as expected: the automap mini map in the HUD, the window title "X-Men Legends", Begin Story
  starting without a difficulty prompt (every New Game took one Enter; the baseline walk took two).

## Needs Owen

Nothing blocking. Not covered by these runs: movies (a `--no-movies` build), Discord presence (off in test installs),
online, real pads, save / load, and playing the fights themselves. One thing worth a look when you play: the
act 5-6 Sentinel attack in front of the mansion (`sentinels_mansion` / `sentinel_mansion`) is now a real fight - a
lone Magma who stands still loses it within one to two minutes.

## Tool follow-ups (done 2026-09-29 morning: 0f87f43 + edff8a3; `regwrap.py` is no longer needed)

The list as the night left it, each with what was done. Checks ran on `_int1` / `_int1_tour` with the harness
re-installed as `--limits --pipe-name tools` / `--pipe-name tools_tour` (DLL 00b2646, Discord off); results in
`build/tools_*` (below).

- DONE - tour stops keep the hero alive: `tour_runner.py` (not `testhooks.py`: the tour builds stay as they are) sends
  `setInvulnerable("_ACTIVE_HERO_","TRUE")` + `restoreHealth("_ACTIVE_HERO_",10000)` through the pipe whenever the
  HUD comes up in a zone; `--mortal` turns it off; each zone record says `keep_alive: ok`. With the hero at full
  health, the low-bar "no HUD" reading can't happen. New `--count N` runs a slice (`--start-index 64 --count 5` =
  wx1_2, nuke1_1, wx1_3, nuke1_2, danger_room, the stretch where run A lost Wolverine):
  keep-alive **5/5 ok, health 1.00 in every stop shot** (`build/tools_tour_slice`, again with a warm file cache in
  `build/tools_tour_slice_warm`); `--mortal` 5/5 ok but health 1.00 -> **0.74** in nuke1_1 -> **0.54** from wx1_3 on
  (`build/tools_tour_slice_mortal`). Zone change -> HUD with keep-alive (warm) 1.3 / 3.3 / 1.3 / 1.5 / 0.0 s, mortal
  1.7 / 1.4 / 3.5 / 1.6 / 0.0 s: the keep-alive costs no load time (the first slice's 8.0 / 5.2 s were a cold file
  cache; a probe with an invulnerable hero in nuke1_1 saw no HUD-test flicker, `build/tools_tour_slice/invuln_hud.log`
  - so run B's 3.4-6.5 s zones were most likely the cache or other jobs, not hits on the bar). The probe also showed
  that invulnerability set in wx1_2 still held in nuke1_1 after a loadMapKeepTeam (health 1.00 for 14 s).
- DONE - `campaign_walk.py` keeps the hero alive by default: the same two statements before every start and after
  every settle (`walkinv2`'s approach, `Walker.keep_alive`; `--mortal` opts out; campaign.md says "Keep-alive: on").
  New status **party-empty**: every getPartyMember reads "" after the start (a dead or dropped party) - mount's
  keep start with an empty party kept is no longer ok - and any start whose party reads empty restarts the game
  before the next mission. Check: `--from end_astral --to mansion6` on a fresh game (`build/tools_walk_chain`,
  06:02-06:09, one launch): end_astral bounced (as in the baseline), **sentinels_mansion, sentinel_mansion, mansion5
  (19.8 s), healer_briefing, rescue_healer, mount and mansion6 ok, party magma throughout, Magma's health 1.00 in
  every shot** (level 5 among the Sentinels in `shots/003_sentinel_mansion.png`) - the chain that died in `reg_walk`;
  17 keep-alive lines in xml2-fix.log, none failed. Offline, the recorded walks re-graded with the new rules:
  `reg_walk` mount ok -> party-empty, and its sentinel_mansion / rescue_healer (load-timeout with an empty party) now
  restart the game at once, so mansion5 would have started on a fresh game; `walk1`, `reg_walk_chain` unchanged.
- DONE - `power_sweep.py` defaults are the redo options: `--frames 30 --frame-gap 0.06 --post-wait 2.5` (`--keep-full`
  stays opt-in: it only changes what is kept, not what is measured - 1.1 GB for 5 heroes). Check `--heroes
  beast,rogue` with the defaults (`build/tools_powers`): **8/8 fired, each on the first try**, the two boosts
  included (Beast left 1.00 -> 0.36 after, Rogue left 1.00 -> 0.44 lowest) - both were no-energy-change in
  `reg_powers`.
- DONE - one build's game only: `current_zone.game_pid(build)` returns only `<build>\XMen2.exe` (folders compared
  with junctions resolved, case folded), `current_zone.kill_build(build)` kills by pid; without a build: the one
  game, or with several the one whose xml2-fix.ini serves `XML2FIX_PIPE` (None rather than a guess).
  `tour_runner.kill_game(build)`, campaign_walk / power_sweep (Walker) and the probes (`actor_slots.py`,
  `conv_probe.py`, `hero_xp.py`: `--build DIR`) use it; nothing kills by image name any more. The build-driven tools
  also take the build's own pipe from its xml2-fix.ini (`fixinput.use_build`: no `XML2FIX_PIPE` needed; one naming
  another game's pipe is refused), and the Walker tools stop if another folder's game serves the same pipe name.
  Check: `_int1`'s game (pid 63032, pipe tools) left idle and a pre-launched `_int1_tour` game running, then the
  tour slice on `_int1_tour`: its first kill took only the pre-launched tour game, its end kill only its own; pid
  63032 was in all 64 process samples and still ran afterwards (`build/tools_tour_slice/two_games.log`; same in the
  mortal and warm runs). With both games up, `game_pid()` gave None (neither serves the default pipe), with
  `XML2FIX_PIPE=tools` 63032. The power sweep ran on `_int1` with the `_int1_tour` game idle beside it (before, the
  Walker stopped whenever tasklist listed the other game first).
- DONE (not on the night's list; HANDOFF TODO) - `xml1build/validate.py` in junctioned worktrees: validate
  resolve()d its XML1 roots but not the registry sources, so a worktree build (inputs = junctions to the main tree)
  had no XML1 sources and the inherited V7 man1a/1_2_37 disallowResponse warning became an error. `PathRoots`
  compares both spellings of both sides (edff8a3). Proof: a temp junction test (10 cases) and `_int1` validated with
  its XML1 roots and 4649 sources moved behind junctions: the old logic reproduces the error (x1_sourced_files 2486
  -> 0), the new one equals the main-tree run in every check. `validate_selftest --skip-tour`: rc 0, restored ==
  positive.

## Artefacts

- `build/_int1_tour` (tour build, harness installed, tour scripts original; pipe `tools_tour` since the morning),
  `build/_int1` (harness reg; pipe `tools` since the morning).
- Morning tool checks: `build/tools_tour_slice` (+ `two_games.log`, `invuln_hud.log`), `build/tools_tour_slice_warm`,
  `build/tools_tour_slice_mortal`, `build/tools_walk_chain`, `build/tools_powers`.
- `build/reg_tour` (run A: `tour_results.json`, `shots/`, `slots.csv`, `repro_wx1_2/`, `repro_invuln_nuke1_1/`),
  `build/reg_tour_inv` (run B + its xml2-fix.log), `build/reg_walk` (+ `xml2-fix_launch5.log`), `build/reg_powers`
  (+ xml2-fix.log, `_beast_left_hud_zoom.png`), `build/reg_powers_redo`.
- `build/reg_walk_inv` (+ `repro_mansion5/`), `build/reg_walk_chain`.
- `build/reg_scripts/`: `regwrap.py` (pinning wrapper; `tour`, `run`, `walkinv`, `walkinv2` modes), `tour_repro.py`,
  `step_repro.py`, `cmp_tour.py`, `cmp_walk.py` (the comparisons in this file).
