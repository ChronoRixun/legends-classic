# Online saves: who saves, whose campaign, what the joiner keeps (2026-09-29 00:00-00:32)

Question (Owen): "how will save files work online - is it no save for the non-host, or does it load your save
file for characters as it joins?"

## Answer

Neither. XML2's engine, and so the port, uses a **host-owned session with a save copy for every player**:

1. **The session runs on the host's campaign.** When the host starts a *Load Saved Campaign* game, its save (the
   full 195,584-byte game state: roster, levels, XP, powers, equipment, costumes, unlocked heroes, mission and
   side-mission state) is streamed to every joiner ("Sending game information..." / "Retrieving game
   information...") and loaded there. The joiner plays a hero from the **host's** roster at the host's level.
   A *Campaign* (new game) session starts from the new-game state on every machine.
2. **The joiner's own save is never used online.** *Load Saved Campaign* is only in the host's Game Options. The
   join screen's Game Type is just a search filter (Any / Campaign / Danger Room). The pause menu's *Load Game*
   is skipped for everyone while 2+ players are connected. It becomes selectable again once the host is alone.
3. **Saving is not host-only.** When **anyone** picks *Save Game* at an Xtraction Point, **every** player gets their
   own "Save A Game" dialog. The dialog lists that player's own slots, and each player writes a copy of the shared
   session into their **own** save folder (new slot, overwrite with confirmation, or Esc to skip). A "Waiting for
   Other Players..." barrier then holds everyone until all are done. The Xtraction Point menu belongs to the hero
   who activated it, host or joiner.
4. **The joiner's copy is a normal save.** It loads in single player (verified: the joiner loaded its copy
   solo and got Wolverine + Cyclops at nyc1_1_3). The joiner's own campaign slots are untouched unless the
   joiner overwrites one on purpose (verified byte-identical).
5. **Profile (settings.dat).** The joiner keeps its own profile. A client skips the profile block of the host's
   save (load mode 2). Each machine's save embeds that machine's own profile. The joiner's settings.dat is written:
   - on the online name screen's Ready;
   - with every save the joiner makes (a new Review bit earned in the session was included);
   - never with the host's unlocks.

Tonight's "host-only" first evidence was an artifact of the earlier test. The host's slots there came from
single-player `console savegame`, and nobody saved during an online session. The joiner's settings.dat came from
the online name screen's Ready (section 5).

## 1. Static research (XMen2.exe retail, md5 b34f0baf1058d518f55b3cefb3fccc5f)

Ghidra 12.1.3 headless on a copy of research/characters/ghidra/proj (DecompAt.java). Decompiles and helper scripts
are in scratchpad `osave/` (d1..d17.c, xr.py, calls.py, sfn.py).

### 1.1 Entry points
| what | address | notes |
|---|---|---|
| console `savegame` / `loadgame` | 0x5f2b10 / 0x5f2b70 | queue `saveloadProcess(4)` / `(3)` (registration list 0x5f490c-0x5f4c0e) |
| console `startloadedonlinegame` | 0x5f1ba0 -> 0x606fb0 | applies the received save (1.3) |
| script `saveloadProcess(i)` | 0x49ef60 | CSaveLoad singleton 0x75cbc0 (vtable 0x68db8c) vt+0x14 = 0x4aeb80; state machine 0x4af9e0 |
| script `extractionPoint(a)` | 0x4a6b50 | dialog title 0x7d0; options at 0x4a6c88-0x4a6d30: 0x7f8 `openmenu('worldmap')` (Xtract), 0x7d1 `extractionPointChange(%d,0)` (Change Team), 0x7d2 `saveloadProcess(4)` (Save Game). **No online check.** |
| dialog addOption | 0x5e97d0 (manager 0x8b13ec, vtable 0x6a332c) | args (text, script, script2, closes, resumes, disabled). Online, the dialog reads its buttons from one player's net input (0x5eb609-0x5eb638 -> 0x611250). In game: the activator's. |
| host Game Options, Game Type | 0x5b9110 | 0xff0 `SetGameType(1)` Campaign, 0xffd `SetGameType(2)` Danger Room (disabled while profile vt+0x3c() < 0x10), 0xffe `saveloadProcess(3)` = **Load Saved Campaign** (host's own slots) |
| online name screen Ready | 0x5cb150 | profile vt+0xb4(name), `runscript saveloadProcess(2)` (0x5cb3b4) -> **settings.dat written** |

### 1.2 Save to disk (every machine runs this)
- CSaveLoad write state 0x4b15b0: allocates 0x2fc78, game vt+0x208 = 0x46baf0 serialises the state, FileMgr
  (0x55e9a0) vt+0x64 writes `saveslot<n>.save` (0x2fc00 + a 0x84 header = 195,716 bytes), then vt+0x54 writes the
  profile (0x228 bytes) = **settings.dat with every game save**. Path `%s\Activision\X-Men Legends 2\Save\`
  (0x69ab14) + `saveslot%d%s` (0x69ab64), redirected by xml2-fix [Game] SaveFolder.
- **Online with more than one player** (0x4aebb6-0x4aec0a): process 4 clears every player's "saved" flag 0x400
  (0x611910, 50.0 s timer at +0x438), net-pauses (0x60c230(1)) and runs `openWaitingDialog()`. The dialog is
  the "Waiting for Other Players..." seen in game; the host's copy also offers Kick Player. The finish/abort
  (vt+0x44 = 0x4ae990) returns early while others are still saving. Otherwise it sends 0x4b (unpause, 0x60cf90)
  and 0x5b (0x611980). The 0x5b handler 0x6116d0 (registered via 0x60edb0 in 0x613d46's function) sets that
  player's flag 0x400. So the save is a **barrier across all machines, and each machine saves locally**.
- Nothing in CSaveLoad checks host/client (the only net calls are 0x4ae993-0x4aea12, 0x4aebb6-0x4aebfa,
  0x4aed34-0x4aedd7 and 0x4b13a3). The X-point option has no online flag.

### 1.3 Load online: host's save -> joiners
- Host picks a slot in Load Saved Campaign -> completion 0x4aed10. In a lobby (0xa3bc40[0] != 0), 0x608260 copies
  the 0x2fc78-byte buffer into lobby+0x2250 (+0x2294 = "saved stats" flag, process 5) and 0x608330 keeps the
  slot text. Otherwise (single player) game vt+0x20c loads it directly.
- Start Game with players != 1 (0x6094f0):
  - message 0x47 'G' {difficulty (game vt+0x268), flag, byte} to all;
  - 0x607fb0 streams 0x2fc00 bytes as message 0x48 'H', 200 bytes each, at most 5 queued per player;
  - 0x26 -> start (0x5f3c20(0)).
- Joiner 0x608630: 'G' allocates the buffer and sets the difficulty (game vt+0x26c); 'H' copies chunk n at n*200;
  at 0x2fc00 bytes it acks 0x4a.
- `startloadedonlinegame` 0x606fb0 -> game vt+0x20c = **0x46e2b0(buffer, mode)**, mode 1 = saved stats
  (New Game+), **0 = host, 2 = client**. 0x46e2b0 then loads, in order:
  - heroes (registry vt+0xa4: level/XP, powers, costumes, unlocked list);
  - game block 0xdc;
  - side-mission stack 0x4e0;
  - 0x4c9da0;
  - extraction points (0x4ae7e0 vt+8);
  - map/mission vt+0xb8(buf, mode);
  - **profile 0x48fdd0(buf, mode)**;
  - script vars (0x4a1670 vt+0x2c);
  - 0x468530 vt+0x1c.
- **0x48fdd0, mode 2: reads the host's 0x228-byte profile block into a temporary and discards it.** Other
  modes replace the profile but keep the local name (+7), then apply options (vt+0x50).
- Profile object 0x72c530 (vtable 0x689994), 0x228 bytes at +4:
  - name +7;
  - character-unlock bitset +0x1c0 (0x129 bits, vt+0x38 = 0x48f770, used by isCharacterUnlocked 0x49f610);
  - 5 x 90-bit Review bitsets +0x1e8 (vt+0x24 = 0x48f920);
  - hard-difficulty bit +0x229 (0x48f710);
  - byte +0x228 (vt+0x3c).
  settings.dat = a 0x84 header + those 0x228 bytes (684 bytes).

## 2. In-game test (two windows, local OpenSpy)

Setup:
- Build `build/_jh2` plus a junction copy `build/_jh2_b`, xml2-fix c17c158 (scratchpad snapshot).
- Harness: `--limits`, pipes port-host / port-join, `--online-server <host-address> --log-network`, save folders
  `X-Men Legends (osave host)` / `(osave join)`, plus `[Online] LocalIP=<host-address>`.
- Seeds: host slot 0 = the earlier "East Manhattan" nyc1_1_3 save. **Joiner slot 0 = a different campaign,
  "man1a" (Magma at the mansion)**, as its own single-player campaign.
- Both windows accepted a main-menu item before `openmenu online`, which avoids the known fresh-boot crash.

Screenshots are in scratchpad `osave/shots/` and logs in `osave/logs/`, with file snapshots in `osave/files/` (not
committed).

| # | step | result | shots |
|---|---|---|---|
| 0 | Host, single player: load slot 0, walk into the Cyclops trigger (joinHero reload), X-point, **Save Game** | menu "X-Jet Xtraction": Xtract / Change Team / Save Game; slot 1 written together with settings.dat (00:03:33.88 / .96) | h_p0e-h_p0g |
| 1 | Host: Play Online, Ready | host settings.dat rewritten 00:06:19 (the name save) | h_on1-h_on2 |
| 2 | Host: Host Game > Game Type | Campaign / Danger Room (grey) / **Load Saved Campaign** -> lists the host's slots -> "Saved Campaign" -> Post Game | h_on4-h_on9 |
| 3 | Joiner: Play Online, name "Playeroiner", Ready | joiner settings.dat rewritten 00:10:46 | j_on1-j_on6 |
| 4 | Joiner: Join > Search > Join, Ready; host Start Game | host **"Sending game information..."**, joiner **"Retrieving game information..."**; host log 195 packets of ~1,040 bytes to the joiner (00:13:54.586-00:14:56.607, 201,255 bytes; the first carries `[SAVEGAMEBEGIN: 00:09 - East Manhattan (Normal)]`), joiner log the same by recvfrom | h_start1, j_start1 |
| 5 | In game | both: 1P Wolverine lv 1, **2P Cyclops lv 1 = the host's campaign**. The joiner's own campaign (Magma) plays no part. | h_in1, j_in1 |
| 6 | Host activates the X-point | same menu on both; joiner's DOWN moves nothing, host's moves both | h_x1-h_x3, j_x1-j_x3 |
| 7 | Host picks **Save Game** | **both** get "Save A Game": host's list = its East Manhattan slots, joiner's = **its own** "Game 1 - man1a"; overlay "Player (Wolve): Not Ready / Playeroiner (Cyclo): Not Ready" | h_x4, j_x4 |
| 8 | Joiner moves its cursor and saves to a new slot | only the joiner's dialog moves; **joiner folder: saveslot1.save + settings.dat 00:17:28** | j_x5-j_x6 |
| 9 | Joiner Continue | joiner "Waiting for Other Players... [Quit to Main Menu]", joiner Ready, host still Not Ready | j_x7 |
| 10 | Host saves to a new slot, Continue | host folder: saveslot2.save + settings.dat 00:17:56; both resume ("Playeroiner is lagging" at ~9 fps) | h_x8-h_x9 |
| 11 | **Joiner's** Cyclops activates the X-point | menu on both; **joiner's input drives it**, the host's DOWN does nothing | j_y1-j_y4 |
| 12 | Joiner picks Save Game; host presses Esc | both get their own save list; host skips -> host "Waiting... [Quit to Main Menu, Kick Player]", host folder unchanged | h_y5-h_y6 |
| 13 | Joiner overwrites its slot 1 | the overwrite confirmation -> Yes -> joiner saveslot1 + settings.dat 00:20:14; resume | j_y7-j_y9 |
| 14 | Pause menu, 2 players | both see Objectives ... Players / **Load Game** / Quit Game; each player's cursor is its own; UP/DOWN **skip Load Game** on both | j_p1-j_p3, h_p3 |
| 15 | Joiner Quit Game | host shows the player-left message (name garbled); no file written by quitting | h_q2 |
| 16 | Host alone online | pause Load Game selectable again (Players <-> Load Game) | h_p5-h_p6 |
| 17 | Joiner, single player: Load Game | "Game 1 00:11 - man1a" + "Game 2 00:13 - East Manhattan" (its copy) | j_sp2 |
| 18 | Joiner loads Game 1 (own campaign) | Magma alone in Xavier's office, as before | j_sp3 |
| 19 | Joiner loads Game 2 (online copy) | single player, **Wolverine + Cyclops** at nyc1_1_3: a playable copy of the host's campaign | j_sp5 |
| 20 | Joiner: Join > Game Type | filter only: Any / Campaign / Danger Room; no Load Saved Campaign | j_jt1 |

Files at the end (size, mtime, md5 prefix):
```
host  saveslot0.save 195716 22:20:12 b2233ffe  (seed, untouched)
host  saveslot1.save 195716 00:03:33 3fff2024  (single-player X-point save)
host  saveslot2.save 195716 00:17:56 65b2bd27  "00:11 - East Manhattan" (online, host-triggered)
host  settings.dat      684 00:17:56 852de9b1
join  saveslot0.save 195716 22:22:06 63b9fe5e  "00:11 - man1a" - own campaign, byte-identical to the seed
join  saveslot1.save 195716 00:20:14 fed1bf37  "00:13 - East Manhattan" (online, joiner-triggered overwrite)
join  settings.dat      684 00:29:23          (last write = a later online-menu Ready)
```

The host's slot 2 and the joiner's first online copy (00:17:28) differ in only 14 of 195,716 bytes:
- one float at 0x325c in the mission record, likely a timestamp (they saved 28 s apart);
- the embedded profile at 0xefb5: the name ("Player" / "Playeroiner") and unlock bits.

Every machine embeds **its own** profile. The joiner's copy has no character-unlock bits, the joiner's own. The
host's has bits 4, 16, 56, 59, 84.

Joiner settings.dat through the session (profile bits decoded):
- boot: empty.
- online Ready: name plus 6 Review bits already set in memory by the main-menu visits before it (the first write since boot).
- first online save: +1 Review bit (category 0, bit 6), picked up during the session.
- second save: unchanged.
- The host's character bits never reached it.

After the session the joiner loaded both of its saves in single player. Its settings.dat, written at the next
Ready, then held its man1a campaign's unlock bits. Single-player loads replace the profile from the loaded save
(0x48fdd0, mode != 2). That is ordinary XML2 behaviour, not an online effect. The exact merge order across two
loads was not isolated (**UNVERIFIED**).

## 3. Options for the port

**A. Keep XML2's model as it is (recommended).**
- Pros:
  - Zero work, and it is what the engine's lockstep expects.
  - The host owns story progress, as in XML1, whose couch co-op had one console save.
  - Every player can keep a copy at each Xtraction Point save and continue that campaign solo later.
  - Joiners can't corrupt the session with their own saves.
  - A joiner's own campaign stays safe behind the overwrite prompt.
- Cons:
  - Joiner copies take slots in the joiner's list. They are labelled only "time - zone (difficulty)", like any
    other save, so "Game 2 - East Manhattan" is not obviously someone else's campaign.
  - A careless "Yes" on the overwrite prompt replaces the joiner's own campaign.
  - A joiner can't bring its own heroes or levels.

**B. A. plus a joiner-copy feature in xml2-fix (optional).**
- B1 (small): on a client, add the host's name to the save description, e.g. "00:13 - East Manhattan (Normal) -
  Player's game". The header text is built for `[SAVEGAMEBEGIN: %s]` (0x46bc7c). Only the text changes; the state
  and the barrier are untouched.
- B2 (medium): `[Online] JoinerSaves=ask|auto|off`:
  - ask: native.
  - auto: skip the slot dialog and write to a dedicated slot range or `Save\Online\` so it can't hit the player's
    own campaigns.
  - off: skip the save and just send the 0x5b "done".
  This hooks the CSaveLoad state machine (0x4af9e0) and FileMgr slot naming (0x55e963). The barrier message must
  still go out.
- Pros: clearer copies; no accidental overwrite of your own campaign.
- Cons: RE and test cost, plus new code in the online path that only two-machine tests exercise.

**C. "Bring your own hero" (the joiner's save supplies the joiner's character) - not recommended.**
- The engine has one shared state, the host's, identical on every machine (lockstep).
- Merging a joiner's hero record needs a new pre-start message and a registry merge run identically everywhere.
- It also conflicts with the port's faithful forced parties: XML1's scripted teams decide who is seated, not the
  players' rosters.
- High effort, desync risk, not faithful.

**D. Host-only saves (auto-skip the joiner's dialog) - not recommended.**
- Removes the joiner's only way to keep the campaign it helped play, for no gain.
- Still needs the B2 hook.

### Implications for the port's forced parties
- **All forced-party state is inside the save**, so any player's copy continues correctly solo:
  - the side-mission stack with the pushParty / joinHero records (0x4e0 bytes, written 0x46bcd4, read 0x46e3ec);
  - the seated names in the mission record;
  - zone and script vars.

  xml2-fix keeps only a transient de-dup guard (`queued_pop` in forced_teams.cpp), nothing persistent. Verified:
  the joiner's copy, saved after the online joinHero, loaded solo with Wolverine + Cyclops.
- A joiner on **standby** during a solo stretch (no hero) still gets the save prompt when someone else saves at an
  X-point. It can't open one itself: it has no hero to activate it. Its copy has the faithful forced party (e.g.
  Magma alone).
- Every machine must run the **same port build and the same xml2-fix [Game] settings** (ForcedTeams, JoinHero,
  XPCurve, NewGameTeam). The script functions and the XP curve run in lockstep on each machine. The planned
  `[Online] GameVersion` keeps other builds out of the lobby.
- Save copies are positional on the herostat roster, so they only load in a port install with the same roster.
  Nothing checks this for files. Put it in the release notes.
- The X-point menu belongs to the activator, so a **joiner can choose Xtract (world map) or Change Team for the
  whole group**. Change Team during forced stretches online is still open (see port_online_test.md, rec. 3).
- XML1's first real save point is nyc1_1_3. The Central Park X is extractionPointLite, with no save. A New Game
  online therefore gives joiners their first copy there.

### Recommendation
**Keep A.**
1. Tell players: "Online you play the host's campaign; when anyone saves at an Xtraction Point everyone is asked -
   pick a new slot to keep a copy, never your own campaign's slot."
2. Do B1 (host name in the joiner's save text) in the next xml2-fix batch if testers find the copies confusing.
3. Leave B2 unless the overwrite prompt proves insufficient.
4. Don't pursue C or D.

## 4. Not tested / open
- A 3-4 player session; the 50 s timer at +0x438 (what happens if a player never finishes the save dialog).
- Saving while a joiner is on standby (forced solo stretch).
- X-point Change Team online.
- Exactly where the pause menu disables Load Game online. Observed only; 0x5ce7f0, the online pause/ready logic,
  was read but not pinned down.
- New Game+ ("saved stats", process 5) online.
