# Grab lifecycle and collision (rule 45)

`tools/build_xml1.py --grab-carry xml1` - the default since 0.4.1-beta.1 (beta 8), like Rogue's decide - writes
`[Game] Xml1GrabCarry=xml1` for the companion DLL's grab/pickup/recovery and flying-charge collision implementation
(XML2 Fix 1.9.0-beta.1, rule 45 revision 2, mask 7).
`--grab-carry xml2` (A/B builds) writes no key; rebuilding with it removes a stale owned key.
An existing companion DLL lacking the key is refused. The content option is
recorded in build metadata, restored by `args_for_out`, and invalidates the
characters module when changed. No release/content identity is assigned here.

This stage preserves all authored victim nodes and triggers. In particular,
`juggrabthrowforwardvictim` is distinct from the handler entry's
`grabattackvictim` lookup. The entry may normally be inert if that latter
move is absent. Juggernaut's authored sequence is one hit then release, not
a repeated pound. The DLL restores the large hold exception, attack entry,
shared victim retention and ground cleanup behavior. It also restores ally-throw
constraint setup, pickup admission/cancellation, thrown-land recovery and
flying-charge collision acquisition without the added PC nonactor Z filter.
Damage producers belong to the separate shared-handler work and are unchanged.

Flying carry and fix7 flight admission/cancellation remain deferred together. This option does not restore the missing
`ea_flyingcarry_*` or `ea_jug_grab_*` animation enums, change XML2's flying
moveset precedence, add carry handlers, or alter converted flight energy
powerups. The existing animation warnings remain meaningful: ground-rule
completion is not a claim of full victim-pose parity.

Verify with `python tests/unit/run.py`, plus the companion DLL's
`xml2_xml1_grab_carry_test` and `xml2_xml1_grab_carry_install_test` fixtures.
The unit tests check option/INI coupling, stale-key removal, unchanged OFF INI
bytes and refusal of an older companion DLL. Source game content is never
embedded in these tests.

Live checks remain: loaded `grabattackvictim` resolution, large/nonlarge holds,
authored one-hit throw and distances, invalid-handle/interruption cleanup,
EntityCapacity, and co-op rule 45 agreement. No game or xemu was launched.
