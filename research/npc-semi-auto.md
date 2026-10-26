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

The exporter selects every gun primary of the original weapon brain and
exports canonical schema-3 INI records:
`actor|recoil_bits|range_bits|burst_bits|leader|warmup_bits|flags`. Each word is
eight lowercase hex digits. Recoil, range, burst duration and warm-up keep their
exact binary32 source bits; leader is zero or one (the PC stats conversion does
not preserve that flag); flags carry the original prototype's type enum in bits
0-1 (bullet 0, flame 1, projectile 2, beam 3), its continuous-beam (0x10) and
rapid-fire (0x20) bits and 0x40 when the source primary uses the default handler.
Omitted source burst duration defaults to 1 second, as in the original prototype
constructor. A `ch_weapon_semi_auto` primary of any type qualifies: discrete,
with a warm-up before every shot, or a continuous beam that warms up once. Zero
recoil is admitted only for a continuous beam (the lightning gun). A primary with
no handler qualifies only as a discrete weapon without warm-up (the pistol); any
other handler, a missing style, source-authored gun AI metadata on a gun move,
melee weapons and invalid timings are reported exclusions. The runtime selects
the ranged brain independently of the NPC class and keeps all weapon moves out
of the generic power lottery. The original input gate selects the primary shot,
while explicit scripted burst moves remain intact.

The all-holder audit found 20 weapon brains and eight melee-weapon exclusions;
the exporter now emits all 20 (seventeen at range 550, the three flamethrowers at
275). The original's held-fire branch and input gate are shared by every type;
the companion gate restores the warm-up deadline (started once fire is admitted,
cleared after every discrete shot and on release), the continuous play flag and
the default-handler path; it also restores the bullet line-of-sight drop and
the branches for an empty near-target query (including the continuous-beam aim
sweep).

`contract(stats_tree, weapons_tree, styles_by_stem)` builds the records and
`ini_sections(contract)` the xml2-fix.ini export; `build_contract(ctx, names)`
is the characters-stage wrapper (rows for actors the build does not carry
become exclusions). The keys require the companion `NpcSemiAuto=xml1`
implementation (XML2 Fix 1.8.0-beta.7 for schema 3) and `NpcPowerRule=xml1`. That
implementation is gameplay-agreement rule 16 **revision 11** (`{1,1,1,metadata
fingerprint}` plus the rule's detail, the SHA-256 of the complete canonical rows;
word 3 is that digest's first four bytes; schema 2 tables are refused), one
revision shared with the rest of `NpcPowerRule=xml1`; 1.8.0-beta.6's officer-only
brain was revision 10, refused by revision. Revisions 5-9 were
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
the characters-stage wrapper and port_keys). The new families (warm-up,
continuous fire, flame, the pistol handler, line of sight) still need their live
acceptance against the original.
