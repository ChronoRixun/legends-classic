# Classic menu conversion contracts

The builder converts artwork from the player's disc at build time. Public tests
use invented palettes, scene graphs and glyph images. Generated scenes, font
atlases, menu definitions and screenshots do not belong in the repository.

The release 0.2.5 frontend is the baseline: 63 colours, 22 styles, seven entries
in each PC/HD font map. Native capacities are 75 colours and 32 styles. The
medium/big English overrides already contain classic printable glyphs and PC
control/extended fallback glyphs. HUD/digital indices retain their existing maps.
Appearance work does not change stat values, save fields or gameplay rules.

## Reusable layer

`xml1build.menu_theme.allocate` translates requested legacy styles into modern
colour fields. It preserves native IDs and unrelated styles, reuses exact colour
and pulse matches, and allocates deterministically. New screen families reserve
eight colour entries and four style entries. Allocation returns private copies;
overflow is an error before any table is written. The established main styles
use the same allocator with their original capacity contract.

`xml1build.menu_conversion.convert_scene` reuses the main restoration's camera
and row-spacing conversion. It brings native modal/text depths into view while
keeping the artwork's composition and aspect centring. `rename_aliases` changes
the transform and both serialized aliases together, including names with different
lengths. It rebuilds object records while preserving reference numbers and every
memory block. Missing aliases, unsupported owners and destination collisions fail.

`package_for` collects scene, helper and nested focus-model resources while
retaining the native package's dynamic precaches. `widget_problems` checks scene
anchors, focus-event targets, closed navigation cycles and safe-area positions.
Screen adapters must also validate model dimensions, widget rectangles and dynamic
class contracts; a static focus check does not prove mouse or pad behaviour.

`menu_scene.attach` combines native anchor/animation data and the converted artwork
in one scene. Native reference numbers stay stable. The serializer unions compatible
metadata, relocates typed object references and reference arrays, preserves numeric
animation keys, indices, UVs and pixel blocks, and retains one root scene and camera.
It refuses incompatible schemas, pool tables, external tables, unsupported references
and nonempty primary camera/texture resources. This is a bounded menu importer, not
a general merger for actor or world files. Splitting PDA text/widgets between menu
render layers failed live; they must share the primary scene.

`fit_flat_panel` maps source frame geometry onto native content bounds. Corner bands
and atlas UV quadrants stay fixed; tiled fills retain their density. Culling bounds
use the same map. An explicit opaque variant prevents labels underneath a native
subpanel bleeding into its list and textbox. Selection tinting preserves native
geometry, alpha and hit rectangles while taking its colour from the disc palette.

`main_fonts` owns global menu font conversion. Reuse its atlas/metric pairs and
the medium/big indices rather than importing another global font table. Its
synthetic asymmetric-atlas test samples mapped glyph pixels in both the classic
and fallback halves to detect a wrong UV quadrant or atlas offset.

## Screen adapter boundary

Keep the native class, named service items, mode selectors and action commands.
Translate only appearance fields and scene bindings. Menu definition halves must
stay paired; packages must include helpers and all focus models. Secondary modes
need their own scene contracts even when the first visible panel is a simple list.

Integration acceptance requires a full owned-input build, frontend validator and
self-tests, matched screenshots, real keyboard/pad/mouse navigation and modal
accept/back, and a save/reload cycle. Report static checks and runtime observations
separately. The release integrator owns the content-version bump.

## Pause pilot

`pause_appearance` keeps `PDA_MENU`, its item roles, secondary modes and action
commands. The classic stack retains eight PC entries. Objectives/Players keep
their native timeline and bindings. The Players list and help textbox use the
disc's frame fitted to their existing content bounds. Shared modal dialogs use
the same frame converter and native selection rectangles. Two legacy decorative
anchor names already missing from the retail scene retain their native fallback.

The output uses 63 colours and 24 styles, leaving 12 colour entries and eight
style entries. PC/HD font maps still have seven entries. V-TBD checks both menu
halves, lookup/focus closure, native actions/modes, retained animation references,
camera/modal depth and palette headroom. The frontend self-test also regenerates
the combined scene and compares its bytes. No new engine hook is required.

Prompt expansion remains native and device-aware. Preserve every native `text`
and `desctext*` value in its matching localization half, including root help,
focused-row hints and Players help. Keep `$MENU_BACK`/`$MENU_ACCEPT` tokens and
localization references intact; neither literal pad glyphs nor literal keyboard
labels can follow input-device changes or remapped bindings. Conversion and
V-TBD reject changed text. Runtime acceptance captures the same pause and modal
with keyboard, pad, and keyboard again to verify both transitions.

Objectives now uses the full virtual screen in native PDA mode 1. Its title,
description, steps and seven selector roles retain native state and input. The
placement converter updates transforms and bounds together and detaches only
their animation links; sequence objects and numeric keys remain unchanged.
The native refresh dynamically selects its own objective-selector model, so that
specific resource is converted too. Decorative hinges use the hidden model as
well as visibility flags, because native mode changes can restore visibility.
No additional colours or styles are needed for this screen.

Loading now retains `LOADING_MENU`, its native helper and lifecycle, with original
loading chrome and the disc's animated spinner attached into one scene. Camera
selection retires one checked graph-path list while retaining all native objects
and reference numbers. Its live status text uses a foreground anchor so the
loading artwork cannot occlude it. This consumes no additional palette/styles.

Options retains every native setting, game variable, action, directional command
and device token. Its ten rows use classic disc panels with native focus roles.
Static panel geometry can be instanced at named anchors while keeping one selected
camera. Model-local material pumps are retired and opacity frozen before that
attachment; registering those pumps as global menu animation is unsupported.

The PC Advanced panel is a separate BXIG interface. `menu_raster` converts the
disc's flat frame mesh/UVs/textures into its native PNG state cells. Atlas sizes,
state order, control rectangles and alpha remain native. Player tabs, the binding
table, graphics/display settings and capture/confirmation callbacks remain native;
controller/mouse device icons and unbound-binding text are retained. No additional
colour IDs, font indices, styles or engine hooks are allocated.

Later adapters must preserve native classes and callbacks and reuse these palette,
font, scene, frame and sprite contracts rather than replacing global tables or
transplanting unsupported console classes.

`dialog_appearance` owns the shared native dialog frame, selection tint and two
generic styles. Save/load lists/messages and yes/no/ok confirmations continue to
use native strings, commands and input ownership. Its validator checks the fixed
native rectangle and modern PC font/colour bindings. This family is independent
of the pause adapter and consumes no additional style/palette entries.

The PC image viewer already supplies classic-compatible flat chrome and three
paging hints. Its adapter retains that scene and all native image-selection,
previous/next, any-input and return attributes. Shared camera conversion and
foreground anchor placement keep device-aware hints visible over the picture.
This is separate from the personal-picture adapter and allocates no font/style
entries. Review's category/list restoration remains a later phase.

Native PDA refresh can restore decorative models and visibility independently of
the XML flags. Retired panel hinges and selector brackets/lights therefore also
have their anchors placed outside the view, with their animation link detached.
Keep the interactive selector, current-state and focus anchors in their native
roles. Serialized placement validation covers both the live and retired anchors.

Credits and end credits already use disc-authored scenes and the native rolling
class in the release baseline. Phase 2 retains that restoration and validates
both variants: clear the menu manager's previous picture, preserve native endgame
callbacks, and keep the camera's text-overlay depths visible. Standard and ending
credits share existing fonts/styles; ending/campaign-unlock runtime acceptance is
separate from static frame validation.

XMen2.exe draws each PDA objective picture at a fixed virtual-screen point, not at
its selector: slot n (0..6) is centred at (36, 346 - 45 n), 34 units square
(0x5cda36..0x5cda84; the selector only supplies its depth). Each selector, focus and
current anchor therefore sits on its slot's picture centre with a 44-unit square
frame and hit box, including the native dynamically loaded selector resource. The
beta 5 column (36-unit spacing from z 306) matched the pictures only at slot 3: slot
1's picture covered the title and slot 7's hung below its frame. The title sits to
the right of the column. The panel's bottom strip and the prompts rise off the
screen edge towards the first game's Back bar (prompts 23..43 above the
bottom). `objectives_layout_problems` and the selector validator check the layout
and the serialized frame vertices; picture, objective state and input stay native.
With XML2 Fix's `[Game] ClassicObjectives=1` the slots hold only visible objectives
(no hole for a hidden one), in the act file's order (objectives carry `order`), and
the page opens on the current objective, as the first game's list does.

Review retains the native four-category service, its tab order, unlock filtering,
movie callbacks, list and viewer return. Disc-authored list chrome surrounds a
narrower list; four classic category panels retain native tab roles and mouse
rectangles. The disc's four prop scenes share one perspective camera. A native
model helper uses that camera and category focus events select its prop resource.
Packages include each event's model and helper definition. Root/item prompts,
classes, modes, commands and directional bindings are checked independently from
the appearance provider. No palette/style entries or engine hooks are allocated.

Embedded Review chrome needs its own native depth conversion: moving its camera
and widget anchors leaves the authored meshes near the far clipping plane.
`foreground_chrome` preserves screen coordinates/UVs and maps only mesh/culling
depths into the native panel layer, behind the separately placed native text.
It refuses transformed meshes; UI-alias bounds remain local to their untouched
anchors. Row selection frames use the native row-left origin and a positive local
depth behind the glyph plane, rather than the dialog frame's foreground depth.
Static material alpha/pump state is frozen through the shared opacity converter.

Codex reuses its disc-authored foreground and actor backdrop/platform. The native
text-only list, detail mode, biography widget, actor helper item roles, unlocks and
filter callbacks remain in the PC service. Foreground anchors and bounds move
together into the original panes. The native no-icon whole-row selection resource
keeps its identity with classic frame artwork. Validation checks both definition
halves, list/detail modes, device tokens, placement and the unchanged actor helper.
Its embedded panes and row highlight use the same foreground/row-origin depth
contracts as Review, so the 3D backdrop cannot hide the chrome and the highlight
cannot cover the selected biography name.

The builder enables `[Game] ClassicCodex=1` with XML2 Fix 1.9.1 or later. Back
from a biography uses the native detail-to-list mode transition and retains the
selected row. Back from the list keeps the native menu-close action. The hook
checks the retail Codex action slot and mode helpers before changing memory.
Details refreshes the native biography from the currently selected row before
entering detail mode, including when the row was navigated without pressing
Accept. The retail path updated the biography on Accept alone. Biography text,
character IDs and preview resource selection continue to use the native service.

Forge and Healer share the native shop shell. Their classic frames use the root
culling rectangles of the native panels; list, prices, inventory, service gates,
tabs and input callbacks keep their existing coordinates and semantics. Only
decorative hinges/tracks/lights move outside view. The shop's dynamic tab models
also receive the same classic chrome. The validator compares all nonvisual root,
item and event attributes, including unrecognized economic/permission fields, and
checks each generated frame against its native bounds. Xtraction's choices reuse
the shared classic dialog family; point services and revival pricing stay native.
Depth is part of those bounds: replacement geometry is fitted into the native
model's Y range as well as its X/Z rectangle. Keeping the dialog's local depth
can cover inventory counters or Trivia text even when the frame fits on screen.

Danger Room reuses the same bounded shell conversion for its native course,
roster, description and option panels, with the original perspective backdrop.
Dynamic panel variants and both native list-selection models share the classic
palette. The adapter leaves the course data, grades, rewards, ownership, eligibility
and party-selection callbacks unchanged; those are separate gameplay contracts.

TEAM keeps the PC roster, its four detail tabs and native actions. The disc's
character room is attached to the native helper scene, retaining native reference
numbers, actor/focus/lock roles and camera callbacks. A checked similarity mapping
between the two rooms' four actor anchors rotates/translates the native helpers;
the overview follows the room scale while detail-camera distance and actor size
stay native, including floating/tall previews. Static disc
podiums replace the second set of base models; native selection/lock markers use
disc models. The room replaces the native act-specific cave artwork.

Roster summaries and inventory/help frames fit the native model rectangles and
depths. Decorative tracks and hinges move outside view, keeping their native
animation objects. All nonvisual definition fields, device tokens, item roles,
unknown gameplay attributes and animation timings are compared in both halves.
The converter does not write stats, talents, equipment definitions or save data.
It allocates no palette/style/font entries and needs no new engine hook.

Trivia shares the classic frame conversion at its native question/answer/title
rectangles. Word wrapping, selection geometry, answer callbacks, acts, questions
and rewards remain native. Correct/incorrect indicator resources and their colours
remain meaningful feedback; the blue selection tint does not replace them.

Stats and the retained AI page use disc frames around the native detail bounds;
all four textual tabs keep their roles and selection geometry. Native stat/AI
highlights take their tint from the disc palette. Character panels collapse the
dialog artwork below its authored content seam, avoiding a duplicate empty help
strip. Positions/bounds move together; texture coordinates and indices stay intact.

Skills retains the native list/tree, rank indicators, category/locked icons, detail
mode and device-aware assignment wheel. Its panel and selected row use classic
chrome/tint at native bounds. The builder preserves talent IDs, requirements,
rank costs, assignment callbacks and native disabled/assigned state resources.

Gear retains the native three equipped slots, carried-inventory list, description,
stat comparisons, restrictions and count. Both its static and dynamically loaded
panel resources use disc chrome at native bounds/depths. List selection geometry,
icons and every equip/unequip/drop callback remain native. No item recipe, saved
instance, cost, quantity or enhancement is converted by this appearance adapter.
Gear's two list styles retain the native `allow_focus=true` policy; ordinary
labels retain their native nonfocusable policy. Validation checks these flags
against the native style table independently of the classic colour/font choice.
The primary TEAM scene also retains its native lighting policy for flat portrait
textures. Only the perspective room/actor helper enables its own lighting; a
shared service-shell lighting default must not darken unlocked roster portraits.

## Combined menu and HUD builds

The classic HUD uses a private atlas and scene resources. It does not allocate
menu palette colours or styles, and its conversion runs alongside the menu
adapters. The companion's `[Game] ClassicHud=xml1` enables the HUD only when its
complete versioned asset contract and retail byte guards match. An absent key,
`0`, or `off` retains the native HUD; a stale contract refuses the adapter.

Menu appearance is generated data: definitions, scenes, font maps and panels.
Deleting presentation keys from the INI does not undo those conversions. A
comparison with the earlier release's menu appearance needs that release's
generated data. Disabling the runtime HUD adapter alone is not a menu rollback.

Integration checks must keep these controls separate, preserve native gameplay
tables and save fields, and sample actual zone/menu transitions while observing
the IGB cache and actor-table counters. A verified build and unchanged gameplay
fingerprint do not establish long-session, boss, save/reload or co-op acceptance.
Release identity and the minimum released companion version remain release
integration gates; XML2 Fix 1.7.1 predates the classic HUD adapter.

The character-room cleanup also replaces `model_char_persp_exit.IGB` (an
external room reference) and the code-assigned `m_team_levelup.IGB` with the
existing invisible model. These retire the pulsing cones and helix rings while
the flat blue podium still visibly follows native keyboard and virtual-pad
selection. Private 4:3 and 16:9 checks confirmed that selection remains visible;
the cleanup does not require a new runtime hook or a replacement roster flow.
