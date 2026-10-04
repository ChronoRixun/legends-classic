# Issue #8 validation

The builder preserves completion descriptions without adding, regrouping or reordering
objectives. The XML2 Fix 1.3.2 companion selects them in both native journal renderers
from the existing completion bit. No save-format change is introduced.

## In-game before and after

A controlled test entered an isolated HAARP build, enabled the existing `find_blob`
objective and completed it using the native objective script command. This deliberately
checks journal behavior without claiming to have completed its encounter.

With ObjectiveDescriptions disabled, the completed objective still displayed its
original instruction. With the final companion enabled in a fresh process, the same
objective displayed its source completion wording. Reversing completion restored the
original wording. Native objective observations confirmed the state in each case.
Screenshots and state samples remain local in ignored build directories.

The first live test exposed separate primary and secondary journal rendering paths.
Both are now guarded and hooked; the final primary display was retested successfully.
A five-step counted objective reached count 5/5 and native completion without a direct
COMPLETE command, but its journal display was not established by this test.

The normal native PDA was opened with keyboard input. The legacy `openmenu objectives`
console route points to a missing menu in this build and was unsuitable for this test;
no menu files were changed to obtain the result.

## Checks and limits

210 synthetic unit tests pass. The full owned-input build reports zero errors, and
scripts self-tests T1-T7 pass. Native selection/reset tests and all executable guards
pass. Independent review found no remaining actionable defect.

The existing optional-objective conversion already maps required=false to major=false
for primary/secondary display. This change makes no broader claim about XML1 mission
progression semantics and does not invent new progression enforcement.

Fresh-process save reload, act transitions, multiplayer and the secondary/count-complete
journal display remain unverified. This is a draft with controlled UI evidence, not a
campaign playthrough. New engine functionality targets 1.3.2; 1.3.1 stays reserved for
FightStyles and geometry sharing.
