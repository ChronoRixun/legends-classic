# Saves

Saves live in `Documents\Activision\X-Men Legends`, separate from X-Men Legends II's (Documents may be redirected,
for example to OneDrive). Builder 0.2.0 moved the port, once, to a save format of its own (`SaveLC\saveslot<N>.lcsave`,
`profile.lcsave`) so that later updates can add and change content without turning older saves into broken ones.

## Updating

- **Your saves come with you.** The first time the rebuilt game starts, XML2 Fix (1.4 or later) converts every save
  it finds in `Documents\Activision\X-Men Legends\Save`, and the profile, once, into the new `SaveLC` folder beside
  it. The old folder is never touched. Saves of every earlier builder carry over: heroes, levels, stats, talents,
  inventory, mission progress, unlocks, heard conversations and trivia answers. `SaveLC\legacy-import.txt` says what
  happened to each file. Where a zone changed between versions, only that zone's remembered state starts fresh (a
  notice says so), and a few conversations can play again.
- **Rebuild and update the fix together.** The format needs the rebuilt game *and* the matching XML2 Fix (1.4.0 or
  later; 1.5.0 for builder 0.2.2; the minimum for every builder is in [COMPATIBILITY.md](COMPATIBILITY.md)): the
  launcher does both (Rebuild, then Play). The new DLL alone doesn't make the save tables the format checks at every
  start.
- **0.5 makes the saves bigger.** The first time 0.5.0-beta.1 (or later) saves your campaign it writes a bigger
  layout of the same format: room for 1024 item definitions (was 160), 4096 item bonus records (was 512) and more
  objectives, talents and world items per save, for the first game's items and for heavier mods later. Existing saves
  load and are converted. Beta 8 (0.4.1) and the stable 0.4.0 cannot load a save written by 0.5: they refuse it
  ("this save needs a newer version of XML2 Fix") and do not damage it. 0.6 keeps the 0.5 layout unchanged.
- **Builder 0.2.2 catches old saves up once.** The first time a save from an earlier builder is loaded, every hero
  gets the fifth-level points of the first game's rules (1 skill point and 4 stat points for each fifth level already
  passed) and has its automatic stat growth recomputed with the first game's tables, comic rewards kept. The next save
  records it, so it happens only once.

## Going back

- **Back up before updating.** Copy the whole `Documents\Activision\X-Men Legends` folder (at least `SaveLC`)
  somewhere safe before updating if you might want to go back.
- **From 0.5 or later to 0.4.x:** play from that backup; 0.4.x refuses saves written by 0.5 (see above).
- **From 0.2.2 to 0.2.1** needs the copy of your saves made before the update: XML2 Fix 1.4.0 keeps a save 1.5.0
  wrote as `.lcsave.newer` rather than overwrite it, and can refuse to save the profile.
- **No way back with new saves before 0.2.0.** Builders before 0.2.0 can't read `.lcsave` files: going back to
  0.1.12 plays the old `Save` folder as it was before the update, without later progress.

## Safety

- **Backups.** Every save keeps the one before it as `.lcsave.bak`, and a damaged save loads from it. A save made by a
  newer version is never overwritten by an older one: it is kept as `.lcsave.newer`.
- **A refused save or load keeps your file.** The game says why, and the save on disk stays as it was (so the latest
  progress was not saved). Keep the `SaveLC` folder as it is and report it with `xml2-fix.log` and
  `SaveLC\legacy-import.txt` (look them over first: they can contain folder paths).

## Mods and co-op

- **Mods.** Cosmetic, UI and script mods work as before. A mod that replaces save-bound data (numbered objects, map
  placements, the items and talents a save refers to) is refused with its file name, because saves could not be read
  back correctly with it. Details: XML2 Fix's
  [save format](https://github.com/ChronoRixun/xml2-fix/blob/main/docs/save-format.md) and
  [save guards](https://github.com/ChronoRixun/xml2-fix/blob/main/docs/save-guards.md).
- **Optional settings that change saves.** A save written with the optional 96-actor limit on (`[Limits] Actors=96`)
  needs it on to load; 0.5 with it off says so and asks you to turn `Actors=96` back on.
- **Co-op.** Everyone in an online game needs the same builder version, the same XML2 Fix and the same settings.
  The game compares the builds and their gameplay rules when a player joins and refuses a mismatch, with the reason
  on both PCs, instead of letting the two games drift apart.
