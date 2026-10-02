# Issue 2: controlled boss phase probes

Use a separate generated build and save folder. Run only with the desktop session connected, windowed
1280x720, using `tools/harness.py` and `tools/gamedbg.py`. Never install the harness into the source XML2
installation. Point `BOSS_BUILD` at the test build and `BOSS_OUT` at an evidence directory **outside Git**;
`boss_common.py` reads that build's pipe name. Screenshots and saves are local-only game content.

From the main menu of a fresh process:

```powershell
$env:BOSS_BUILD = '<absolute isolated build path>'
$env:BOSS_OUT = '<absolute local evidence path outside Git>'
python research/regression/boss_fights/issue2_phases.py magneto
python research/regression/boss_fights/issue2_magneto_relays.py
```

Close that specific build with `current_zone.kill_build`, start a fresh process, then:

```powershell
python research/regression/boss_fights/issue2_review.py mastermold
```

Start another fresh process for:

```powershell
python research/regression/boss_fights/issue2_review.py shadowking
# In a separate fresh process:
python research/regression/boss_fights/issue2_shadow_shield.py --fresh
```

The original phase probes deliberately stage health, flags, AI and helper-relay inputs. They do not
establish a complete unaided encounter. `issue2_review.py mastermold` is the exception: it does not
assign health, phases or core prerequisites and never activates checkcore. It uses ordinary hero hits,
then named damage to cross the normal pain thresholds, and activates the actual switches. Master Mold's
spawn-shield conversion was removed; the core puzzle itself remains deferred. The earlier staged
core-control driver was removed because it concealed the progression dependency.

`issue2_review.py shadowking` captures early entry frames and lets the boss/party approach normally,
without teleporting either side. Use a fresh process for `issue2_shadow_shield.py --fresh` to isolate the shield with a solo hero.
The normal-entry probe leaves allied AI active, so it can advance the fight between commands. Its phase/health setup
isolates the existing timer after waiting out the separate generic-AI shield. Ordinary hero attacks
trigger the pain script and deliver the last first-form hit, with the last window/one HP staged.

The Magneto relay follow-on expects stage 2 to have completed in the first probe. A separate fresh
process running `issue2_review.py magneto` tests helpers dying before the threshold: three stage2 acts,
76% health, then ordinary hits, without activating shield1remover. The generated release now waits
0.1 seconds after each stage's pattern transition before clearing invulnerability.

These scripts collect evidence rather than return a pass/fail verdict. Inspect the PNGs: the first
measured title must actually name the boss. The measurement helper compares later title bands with that
reference and discards a changed target. Blue/red bars are both counted; a zero or absent bar alone is
not proof of a kill. Minions can steal the HUD target, and normal AI shields can overlap the scripted
ones. Confirm the second-form body/transition visually, not just the refilled bar.

SPEC 36 records the observed before/after values and the remaining fidelity/playthrough limitations.
The original audit drivers remain unchanged. The issue2 probes additionally assert the expected zone
and use successful fresh screenshots rather than the message-pump heuristic, which produced false
hang reports while loading on this machine.
