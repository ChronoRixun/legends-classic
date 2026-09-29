# Button prompts: why XML2 shows keyboard keys, the power wheel's [Esc], pad prompts

Static research, 2026-09-28, retail XMen2.exe (md5 b34f0baf1058d518f55b3cefb3fccc5f, image base 0x400000,
no relocations; the copy in research/characters/ghidra is the same file as the stock game's and
build/_heroes'). The fix is on xml2-fix branch `pad-prompts` (src/pad_prompts*.{hpp,cpp}, tests in
test/xml2_test.cpp `check_pad_prompts_rules`). Nothing here was checked in game yet.

## TL;DR

- Every prompt ("[E] Talk to Jean", the skills screen's power wheel, the menus' hint bar, tutorial/hint
  text) is a `$TOKEN` in text, turned into a label by one function, **0x619e30**, whose only caller is
  CStrings::get at **0x4bd739**.
- That function shows the first bound binding slot in the order **2, 0, 1, 1** (slot 3 is never read -
  a stock slip). Slot 0 is the registry's `<Action>1`, slot 1 `<Action>2`, slots 2/3 are fixed menu keys
  the game writes into the menu binding rows at start. So player 1's pad (slot 1) can never show while a
  keyboard key is bound, and in a menu the fixed menu key always wins.
- **The wheel's [Esc]**: the skills screen lives in the "team" menu, which runs on binding row 3. At start
  0x61b030 gives player 1's row 3 the menu keys LowAttack=J, HighAttack=**Esc**, Jump=Space, Guard=E,
  Ally=O, TargetLock=P, Pause=Enter (+KP Enter). The wheel's labels are the tokens $ATTACK, $SMASH,
  $GUARD, $MOVE (LowAttack, HighAttack, Guard, Jump), so it shows [J] [Esc] [E] [Space]: Esc is the menus'
  back key, which HighAttack doubles as in menus (MENU_BACK and SMASH both map to HighAttack). Top/left
  only look right because Space and E happen to be the default Jump1/Guard1. **Stock XML2 shows exactly
  the same**: nothing in xml2-fix touches rows 1-4 or 0x619e30 (pad_bindings only fills slot 1 of row 0).
- The same row-3 keys explain the hint bar: "[P] Assign" = `$MENU_DROP` (TargetLock, P), "[O] Details" =
  `$MENU_DETAILS` (Ally, O), "[Esc] Accept" = `$MENU_BACK Accept` (built by 0x5deb60 from string 1063
  "$MENU_OK Accept" with its first 9 characters replaced by "$MENU_BACK ").
- The game has **no "last device used" tracking**. It does know each binding map's pad (map+0x964, the
  device of its first pad binding; 0x61a460 = player's pad index, used by CInput 0x551009/0x55147b/0x55490b,
  i.e. rumble), and the input object keeps current + previous keyboard/mouse/pad states every frame.
- XML2's text renderer supports inline colours (`~NN` ... `~~`), but **not inside a token's label**: the
  renderer reads a `~NN`'s digits from the surrounding text, not from the substituted label. It does draw
  a **one-character label in colour 41 (white)** - the console path for button glyphs. The fix makes that
  colour depend on the character, so A/B/X/Y draw as a single letter in the Xbox colours (colors.xmlb 14
  green, 16 red, 15 blue, 17 yellow - these four ids are exactly the Xbox palette).
- Real Xbox button **icons exist in XML1's Xbox font** (font_xmen_med_xbox, 0xA0-0xB2) but not in any font
  XML2 PC uses. Feasible later as a font asset job (see "Icons" below); not done.

## The chain, with addresses

### 1. Text tokens -> UI codes (font manager, CFontMgr vtable 0x69d69c)

- vt+0x3c = **0x5972d0**, the token parser: reads `$NAME` / `${NAME}` (uppercased, [A-Z0-9_]), looks the
  name up in the controller name map (`FUN_00551ed0()->vt+0x88`), else its own list, and returns
  `code - 0x1000` = **0xF000 + code** with type 1 (a CStrings id), or type 0 (one glyph char; e.g. $AR/$HP
  icons via the table at 0x81d270).
- Name map, registered by **0x5538b0**: MOVE_X 0, MOVE_Y 1, CAMERA_X 2, CAMERA_Y 3, ATTACK 4, SMASH 5,
  MOVE 6 (jump), POWER 7, GUARD 8, ALLY 9, SOLO 10, NEXT 0xb, PREV 0xc, TARGET_LOCK 0xd, TARGET_NEXT 0xe,
  MAP_TOGGLE 0xf, INC_AGGR 0x10, DEC_AGGR 0x11, MENU 0x12, PAUSE 0x13, MENU_OK 0x14, MENU_BACK 0x15,
  MENU_ACCEPT 4, MENU_SUBTRACT 8, MENU_OTHER 0x18, MENU_NEXT 0x16, MENU_PREV 0x17, MENU_DROP 0xd,
  MENU_DETAILS 9, ROLL_LEFT/RIGHT 0x19/0x1a, SPIN_LEFT/RIGHT 0x1b/0x1c, SCREENGRAB 0x1d, DPAD_UP 0xb,
  DPAD_DN 0xc, DPAD_RT 0x10, DPAD_LF 0x11, NEXT_FS 0x10, PREV_FS 0x11, P1 0xb, P2 0x10, P3 0x11, P4 0xc,
  MCHEAT 0xf, MCHEAT_SWITCH1 7, MCHEAT_SWITCH2 0x1d.
- Parser's own list (0x5972d0, when the map has no entry): POWER01..POWER11 0x29..0x33 (POWER1..4 too),
  RUN/WALK 0x23, ATTACKOBJ 0x22, SWTHERO 0x25, MAPTOGGLE 0xf, BINDPOWER 0x27, USEQKPOWER 0x28, ROTCAMERA
  0x26, MOVE_UP 1 / MOVE_DOWN 0x1f / MOVE_LEFT 0 / MOVE_RIGHT 0x1e, CAMERA_UP 3 / DOWN 0x21 / LEFT 2 /
  RIGHT 0x20, **GUAR1..4 0x34..0x37, SOL1..4 0x4c..0x4f, GUAR9 0x50, ATTAC9 0x51, SMAS9 0x52, SOL9 0x53**
  (0x59794e..0x5979c9; strings 0x69d6f4..). No stock data file uses GUAR9/ATTAC9/SMAS9/SOL9.
- Shared codes worth knowing: ATTACK = MENU_ACCEPT (4), GUARD = MENU_SUBTRACT (8), ALLY = MENU_DETAILS (9),
  TARGET_LOCK = MENU_DROP (0xd), NEXT = DPAD_UP (0xb). Unique: SMASH 5 (menus' back is MENU_BACK 0x15),
  MOVE 6 (menus' "other" is MENU_OTHER 0x18).

### 2. Rendering (CStrings id -> label)

- Menu/HUD text renderer **0x5ef2e0** (the only renderer that expands tokens; widths: 0x596df0, wrap
  0x597c90; plain expansion 0x5968f0, used once at 0x5e9edb). Codes it builds per character: `~NN` ->
  1000+NN (colour NN of Data/colors.xmlb), `~~` -> 2000 (end colour), `#NNN` -> 3000+N, `|c` literal c,
  0x92 and '`' -> apostrophe.
- Token type 1 (0x5ef735): label = `CStrings::get(0xF000+code)`. If the label is **one character** (not
  0xbd/0xbe/0xf8) it pushes colour **0x411 = 1041 = colour 41 (white)** before it and 2000 after it
  (0x5ef777) - so console button glyphs keep their own colours. Multi-character labels are drawn in the
  text's colour. The rest of the label's characters go through the same switch, but a `~` inside a label
  reads its digits from the outer string -> **colour codes can't live in a label**.
- CStrings (vtable 0x68e990; data/strings.xmlb + strings_svs.xmlb) vt+8 = **0x4bd720**: ids with
  `id & 0xF000 == 0xF000` -> `0x619e30(id & 0xff)` at **0x4bd739** (the function's only call site); if
  that returns " " it falls back to STRING_166 / STRING_4135 / STRING_4199 or the table.

### 3. The label function 0x619e30 (cdecl, code -> const char*)

1. `[0xa6abfc]` (the input object) null -> " " (0x684868).
2. Pre-map: 0x34..0x37 -> code 8 (Guard), column = code-0x34; 0x4c..0x4f -> 10 (Solo), column = code-0x4c;
   0x50/0x51/0x52/0x53 -> 8/4/5/10 in **row 0**; else column 0 in the current row.
3. action = **0x619c40**(code) (table: 0 MoveLeft, 1 Forward, 2 CameraLeft, 3 CameraUp, 4 LowAttack,
   5 HighAttack, 6 Jump, 7 Power, 8 Guard, 9 Ally, 0xa Solo, 0xb NextHero, 0xc PreviousHero, 0xd TargetLock,
   0xe -, 0xf MapToggle, 0x10 IncreaseHeroAggr, 0x11 DecreaseHeroAggr, 0x12 Stats, 0x13/0x14 Pause,
   0x15 HighAttack, 0x16 Power, 0x17 Solo, 0x18 Jump, 0x19-0x1c -, 0x1d SreenGrab, 0x1e MoveRight,
   0x1f Backward, 0x20 CameraRight, 0x21 CameraDown, 0x22 AttackObject, 0x23 Walk, 0x24 Talk, 0x25 SwtHero,
   0x26 RotateCamera, 0x27 BindPower, 0x28 UseQuickPower, 0x29..0x33 QuickPower01..11); -1 -> " ".
4. map = `[0xa68f40 + (row*4 + column)*4] + 0x18`, row = `[0xa6ac04]` (or 0).
5. Slots tried **2, 0, 1, 1** via 0x6294b0 (record = map + 4 + (action*4 + slot)*12: device, control, value).
   None bound -> "[???]" (0x6a4e6c).
6. `0x6281f0(input, device, control)` (thiscall, ret 8) names it: keyboard -> the DIK name table
   (0x627a50 builds it through igct.bnx: ESC=Esc, SPACE=Space, KP4...), mouse, pads "Btn %s" / "PoV %s" /
   "Axis %s" (igct GamepadBtn/GamepadPoV/GamepadAxis). Result `"[%s]"` in the static 0xa68c18.

### 4. Binding rows and players

- Controller configurations: **0xa68f40**, 5 rows x 4 players of pointers (0x980-byte objects, map at
  +0x18: +0 action count, +4 records (4 slots x 12 bytes per action), +0x964 pad device).
- Row selection **0x61c3b0** (every 5th input update; also 0x61c300 from the frame at 0x402875):
  [0xa53ee8] -> 4; 0x5eb300()->vt+0x78 -> 1; no menu open -> 0; menu "text_entry" -> 2; menu "team" -> 3;
  other menus -> 1. 0x619bd0(row) activates a row for all four players.
- Loaded by **0x61b030** (settings load): row 0 from `Controls\PlayerN\<Action>1/2` (player 1's keyboard
  defaults from a local table; players 2-4 default 0); rows 1 and 3 copied from row 0 (0x629490); every
  player's rows 1 and 3 lose the keyboard keys Up Down Left Right Enter Space Esc Del KPEnter (row 1) /
  KPEnter Esc Enter Space arrows E J O P (row 3) (0x6297f0 clears a device/control from every action);
  then player 1 only gets fixed keys in slot 2 (slot 3 for KP Enter):
  - row 1 (0xa68f50): Forward Up, Backward Down, MoveLeft Left, MoveRight Right, LowAttack Enter (+KP Enter
    slot 3), Pause Space, HighAttack Esc, Jump Del;
  - row 2 (0xa68f60): Pause Enter, HighAttack Esc;
  - row 3 (0xa68f70, the team menu): Pause = HighAttack's own keyboard key, then overwritten with Enter
    (+KP Enter slot 3), HighAttack Esc, Jump Space, Guard E, LowAttack J, arrows, Ally O, TargetLock P.
- Pad bindings in rows 1 and 3 are row 0's (copied), so a pad's buttons are the same in play and menus.

### 5. Where the prompts come from

- Power wheel: skills screen (team menu, CMenuItemSkills) draw **0x5dd520**: `[0x6e76d8 + slot*4]` =
  "$ATTACK" "$SMASH" "$GUARD" "$MOVE" (read at 0x5dd7aa; the AI power list 0x5dfb10 formats string 1125
  "%s (%s)" with the same table at 0x5dfd58).
- Hint bar: string ids through CStrings, e.g. 1068 "$MENU_DROP Assign", 1099 "$MENU_DETAILS Details",
  0x5deb60's "$MENU_BACK Accept".
- Interact prompt: **0x42eaf0** builds "$GUARD Talk to %s" / "Open door" / "Use %s" / "Pick up %s"
  (strings 100-139) and, unless 0x610d20(), rewrites "$GUARD" to "$GUAR1".."$GUAR4" for the player
  (codes 0x34..0x37), then hands it to the HUD (CHud vtable 0x69dca4, vt+0x34 0x59c760).
- Hints/tutorials: igct.bnx / Dialogs *.engb text with $ATTACK, $SMASH, $GUARD, $MOVE, $POWER, $ALLY,
  $TARGET_LOCK, $DPAD_*, $MENU*, $POWER1..3, $BINDPOWER, $USEQKPOWER, $SWTHERO, $ATTACKOBJ, $MAPTOGGLE.

### 6. The input object ([0xa6abfc], 0x12a10 bytes, per-frame poll 0x6285c0 called at 0x61c479)

- +4 keyboard IDirectInputDevice8 (the game's own DI8), state +0x25e4 (256), previous +0x26e4.
- +8 mouse, DIMOUSESTATE +0x4bc (buttons +0x4c8), previous +0x4d0 (buttons +0x4dc).
- +0xc: 10 pad devices; DIJOYSTATE2 +0x4f0 + i*0x110, previous +0x4f0 + 0xaa0 + i*0x110; +0x129cc bit i =
  pad i read this frame. Binding device d (3..12) reads pad d-3 (0x6276d0 -> 0x627650).

## Fonts and glyphs

- fonts_pc.XMLB: X2F_med_PC (eng/spa/ita/rus/pol), X2F_thin_PC (fre/ger), X2F_big, X2F_hud_PC,
  font_XMEN_digital. Textures in Textures/fonts/*.IGB (PC: 256x256 RGBA8, 262144 bytes at the end of the
  file; stored bottom-up).
- X2F_med_PC / X2F_thin_PC glyphs 0xA4-0xAC, 0xAE-0xB3 (22x22) are **PC HUD icons** (numbered gold power
  badges 1-5, red lightning/skull circles...), not controller buttons; used e.g. by options.engb
  label_button01..12. **0x80-0x9F are empty** in both.
- The console font XML2 still ships, x2f_med (unused on PC, DXT5 256x256), has **PS2 glyphs**: 0xA4 cross,
  0xA5 square, 0xA6 circle, 0xA7 triangle, 0xA8 R1, 0xA9 L1, 0xAA R2, 0xAB L2, 0xAE select, 0xAF start,
  0xB0 D-pad, 0xB1 right stick.
- **XML1 Xbox**: xml1_assets/ui/fonts/font_xmen_med_xbox.xml + textures/fonts/font_xmen_med_xbox.igb
  (DXT5 256x256 with mips; the top level is the **last** 65536 bytes of the file; stored bottom-up;
  decode e.g. PIL `Image.frombytes('RGBA',(256,256),data[-65536:],'bcn',(3,))` then flip). Glyphs
  (num: s t s2 t2, width x height, advance):
  - 0xA0 LX, 0xA1 LY, 0xA2 RX, 0xA3 RY (stick captions, ~28x19)
  - 0xA4 **A** (green), 0xA5 **B** (red), 0xA6 **X** (blue), 0xA7 **Y** (yellow) - 22x21, adv 19
    (A: 0.84375 0.09375 0.9296875 0.17578125; B: 0.4921875 0.17578125 0.578125 0.2578125;
    X: 0.5859375 0.17578125 0.671875 0.2578125; Y: 0.6796875 0.17578125 0.765625 0.2578125)
  - 0xA8 Black, 0xA9 White, 0xAA L trigger, 0xAB R trigger, 0xAC R3, 0xAD L3, 0xAE Back, 0xAF Start,
    0xB0 D-pad, 0xB1 right stick, 0xB2 play arrow; 0xB3-0xBC UI frame boxes; 0xBD (c), 0xBE (r), 0xBF TM.
  - No LB/RB: the original Xbox pads had Black/White instead. font_xmen_big_xbox / hud_xbox have no
    button glyphs (hud: accented capitals at 0xC0-0xDF).
- Colours: Data/colors.xmlb ids 14 (0 0.713 0), 15 (0 0.271 0.788), 16 (0.8 0 0), 17 (0.808 0.608 0) are
  the Xbox A/X/B/Y colours. XML1's colors.xml differs (14 green, 15 blue, 16 magenta, 17 yellow); the port
  currently ships XML2's colors.XMLB (same md5), so the ids hold.

### Icons (not done; what it would take)

1. Put A B X Y (+ LT RT Back Start D-pad sticks; LB/RB need new art) from font_xmen_med_xbox into the
   port's X2F_med_PC / X2F_thin_PC (and whatever font the HUD prompt and the wheel use - style 9 at
   0x5dd7c3, unverified) at free code points 0x80-0x9F (avoid 0x92: the renderer turns it into an
   apostrophe), i.e. write new IGB textures + glyph tables (tools/xml1build has no IGB image writer yet).
2. In xml2-fix, a PromptIcons option returning that single character as the label: the renderer draws a
   one-character label in colour 41 = white, i.e. the icon in its own colours (with the fix's colour table,
   leave those code points at 1041).
Without the glyph in the font actually used, the prompt would be blank - so this must stay opt-in.

## What the fix does (xml2-fix `pad-prompts`)

`[Input] Prompts=auto|pad|keyboard|off` (unset = auto), `PromptColors=1|0` (unset = 1).

- 0x4bd739: `call 0x619e30` -> the fix's label function (same maps/rows/actions; guards cover 0x619e30,
  0x619c40, the record getter/setter 0x6294b0/0x6297a0, 0x6295a0, 0x6281f0).
  - pad shown: first slot bound to a pad (0..3), named from xml2-fix's Dual Action profile: buttons 1-12
    X A B Y LB RB LT RT Back Start LS RS, hat = D-pad, X/Y left stick, Z/Rz right stick ("LS Up",
    "RS Left"...); none bound in this row -> the keyboard's label (truthful: e.g. text entry has no pad).
  - keyboard shown: first keyboard/mouse slot in 2, 0, 1, 3, else the first bound (a pad-only player).
  - $SMASH (5) and $MOVE (6) always read row 0 (the buttons of play).
- 0x6e76d8..: the wheel's $ATTACK $SMASH $GUARD -> Raven's row-0 tokens **$ATTAC9 $SMAS9 $GUAR9** ($MOVE
  stays, row 0 via the rule above). Keyboard wheel becomes [KP4] [KP6] [E] [Space] (the keys that fire
  the powers), pad wheel A B X Y.
- 0x61c479: `call 0x6285c0` -> poll, then sample: new key or mouse button -> keyboard; new pad button,
  D-pad change or stick past half way on a read pad -> that pad. auto per player: no pad binding ->
  keyboard; no keyboard binding (players 2-4) -> pad; pad not read (unplugged) -> keyboard; nothing
  pressed yet -> pad; else the later of the two. The log says "prompts: player N's prompts show the pad".
  The test pipe's keys count as keyboard input (they are OR-ed into the game's keyboard state).
- 0x5ef777 (10 bytes, `mov word [esp+esi*2+0x80], 0x411`) -> `call stub; nop5`; the stub stores
  `table[bl]` (1041 except 'A' 1014, 'B' 1016, 'X' 1015, 'Y' 1017). Only one-character labels reach it;
  stock labels are always "[...]", so nothing else changes colour.
- Prompts=off: nothing patched. Any guard mismatch: nothing patched, logged.

## Verifying in game (harness)

The harness can't press pad buttons and its keys count as keyboard input, so force the pad:

    [Input]
    Prompts=pad
    PromptColors=1

in build/_heroes/xml2-fix.ini (with the usual [Test] InputPipe=1 / windowed settings). Expected in
xml2-fix.log at start: `prompts: button prompts show the pad ([Input] Prompts=pad) - ...`, and on the first
prompt `prompts: player 1's prompts show the pad`. Then:
1. Walk up to a talkable NPC / usable object: the prompt reads "X Talk to ..." / "X Use ..." with X blue.
2. Open the team menu -> skills, start assigning a power: the wheel shows Y (top, yellow), X (left, blue),
   B (right, red), A (bottom, green; if not covered). Hint bar: "[LB] Assign", "[RB] Details",
   "B Accept".
3. Tutorial hint (e.g. combat_hint): a hint naming the normal and the heavy attack button
4. Prompts=keyboard: the wheel shows [KP6] on the right (not [Esc]), [KP4] at the bottom, [E], [Space];
   the hint bar keeps the menu keys ([P] Assign, [O] Details, [Esc] Accept).
5. Prompts=auto with Owen's pad: pad names until a key is pressed, keyboard names after, pad again after
   a pad button (the log shows each switch).
