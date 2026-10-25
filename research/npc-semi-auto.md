# NPC weapon brain metadata (rule 16 revision 10)

`tools/xml1build/semi_auto.py` exports the metadata contract for XML2 Fix's NPC
weapon brain (`[Game] NpcSemiAuto=xml1`). It reads the owner's source NPC,
weapon and style trees; it does not contain a table of game assets or alter the
trees. Since 0.4.0-beta.6 every XML1 build enables it by default: the
characters stage records `_build/semi_auto.json` (`build_contract`) and
`fix_ini.port_keys` writes the keys from it (`build_semi_auto`), as it writes
`NpcPowerRule=xml1`. The officer's live acceptance (six range/energy cells at
60 fps against the original) passed with the companion revision 10.

XML1's handler sets an actor-wide deadline on move entry. PC does not register
that handler, and the existing weapon conversion gives firing moves generic
AI metadata. Per-slot `aireusetime`, armed during selection, is not equivalent
to the shared deadline. Increasing the delay or stretching the authored burst
animation is therefore not a faithful data-only restoration.

The exporter currently selects discrete non-bullet weapons without warm-up and
requires the primary move's original semi-auto handler. It reports exclusions,
preserves exact binary32 recoil, range and burst-duration bits, rejects duplicate
identities and exports canonical schema-2 INI records:
`actor|recoil_bits|range_bits|burst_bits|leader`. Each word is eight lowercase hex digits;
the final word is integer zero or one, preserving the source leader flag and its
weapon-brain combo level. The PC stats conversion does not preserve that flag.
Omitted source burst duration defaults to 1 second, as in the original prototype
constructor. The runtime selects the ranged brain independently of the NPC class
and keeps all weapon moves out of the generic power lottery. The original input
gate selects the primary shot, while explicit scripted burst moves remain intact.

The all-holder audit found 20 weapon brains and eight melee-weapon exclusions.
Seventeen weapon brains use range 550 and three flamethrower brains use 275.
The supported plain-projectile contract currently contains one source NPC.
Bullet aiming, warm-up, continuous firing and the pistol's different handler are
explicit exclusions, not silently treated as the officer's firing model.

`contract(stats_tree, weapons_tree, styles_by_stem)` builds the records and
`ini_sections(contract)` the xml2-fix.ini export; `build_contract(ctx, names)`
is the characters-stage wrapper (rows for actors the build does not carry
become exclusions). The keys require the companion `NpcSemiAuto=xml1`
implementation (XML2 Fix 1.8.0-beta.6) and `NpcPowerRule=xml1`. That
implementation is gameplay-agreement rule 16 **revision 10** (`{1,1,1,metadata
fingerprint}`; the fingerprint covers all four source parameters of every row),
one revision shared with the reaction-spent combo steps. Revisions 5-9 were
unreleased candidates (5 a withdrawn role-refresh experiment, 6 the failed
generic-picker candidate, 7 synthesized gun capabilities, 8 the burst/pause
brain, 9 the held-fire brain) and are refused, as are the released revisions 3
and 4. The current refresh filters its already resolved move table; the
exporter rejects source-authored gun AI metadata. Without a contract or rows
the builder writes no weapon-brain keys and the officer keeps the stock PC AI
(rule 16 `{1,1,0,0}`); with the keys absent the DLL installs no weapon hooks.
No save format is changed; the generated game files are unchanged (only
xml2-fix.ini and `_build` metadata).

Synthetic checks: `python tests/unit/run.py -k semi_auto` (contract, export,
the characters-stage wrapper and port_keys). The remaining weapon families
(bullet aiming, warm-up, continuous fire, the pistol handler) need their own
acceptance before they join the contract.
