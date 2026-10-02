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
python research/regression/boss_fights/issue2_phases.py mastermold
python research/regression/boss_fights/issue2_core_control.py
```

Start another fresh process for:

```powershell
python research/regression/boss_fights/issue2_phases.py shadowking
python research/regression/boss_fights/issue2_shadow_shield.py
```

Run the first probe against both baseline and fixed builds. The follow-on probes isolate later relays,
the core check and the shield timer. They deliberately stage health, flags, AI and relay inputs; they do
not establish that an unaided full encounter or core puzzle has been completed. Shadow King's isolated
probe uses ordinary hero attacks for the pain-script trigger and the final first-form hit, with the last
window/one HP staged. It waits out the separate generic-AI shield before testing the scripted one.

The core control first tests the spawn state, then explicitly enables the existing combat node as a
control. Only the unmodified core-check relay switches it off after its prerequisites are staged.
The Magneto follow-on expects stage 2 to have completed in the first probe.

These scripts collect evidence rather than return a pass/fail verdict. Inspect the PNGs: the first
measured title must actually name the boss. The measurement helper compares later title bands with that
reference and discards a changed target. Blue/red bars are both counted; a zero or absent bar alone is
not proof of a kill. Minions can steal the HUD target, and normal AI shields can overlap the scripted
ones. Confirm the second-form body/transition visually, not just the refilled bar.

SPEC 36 records the observed before/after values and the remaining fidelity/playthrough limitations.
The original audit drivers remain unchanged. The issue2 probes additionally assert the expected zone
and use successful fresh screenshots rather than the message-pump heuristic, which produced false
hang reports while loading on this machine.
