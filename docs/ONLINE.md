# Play online in 0.6

Player guide for Legends Classic **0.6.0-beta.3** with XML2 Fix **1.11.0-beta.3**. Online co-op now runs from the
game's own **Play Online** screen. This is a beta. Co-op was tested on one PC (up to four copies) and on two PCs at
home, with two, three and four players, including fights. Not verified yet: playing through the relay (networks where
a direct connection fails), players on different home networks, three or four separate PCs, long sessions, and joins
over slow connections ([known issues](KNOWN-ISSUES.md#online)). The session runs at the host's frame rate; your own
setting comes back when you leave.

Up to four players can share a campaign. Everyone needs the same build - builder 0.6.0-beta.3 with XML2 Fix
1.11.0-beta.3 - with the same gameplay settings and Test mode off; a different build or setting is refused with the
reason on both PCs. beta.1 and beta.2 games cannot join beta.3, and a 0.5 game cannot join a 0.6
game. To update, use Ultimate Legends' **Beta** channel: update XML2
Fix and the builder, then **Rebuild**, then **Play**.

## Open Play Online

From the main menu choose **Play Online**. The screen shows your online screen name and whether the online service is
connected, and offers four choices:

- **Host** - open a room for your campaign.
- **Join by code** - join a friend's room with the code they send you.
- **Browse** - pick a public room from a list.
- **Other ways** - the original online menus: LAN search, Connect by IP and the rest of X-Men Legends II's online
  screens. These do not need the online service.

Mouse, keyboard and controller all work on these screens. If you build with `--online-menus off`, the game keeps the
original online menus instead.

These screens need the connection setting `[Online] Transport=gns` in `xml2-fix.ini`. The builder writes it with them,
and a **Rebuild** adds it to an older install; without it Play Online shows the online service as unavailable.

## Host a game

1. Choose **Host** and set up the room:
   - **VISIBILITY** - **Private** (only people with the code can join) or **Public** (also listed in Browse).
   - **ROOM NAME** - shown in Browse when the room is public. Up to 32 plain letters, digits, spaces and simple
     punctuation; no `;` or `"`.
   - **CAMPAIGN** - a new campaign or a saved one, chosen in the game's own options.
   - **DROP-IN** - **ON**: friends can join after the game has started and come in at your next area. **OFF**: no
     joining once the game starts.
2. Open the room. The **ROOM CODE** appears as soon as the room is open; **Copy code** copies it to share.
3. The **lobby** shows everyone who joins. Players mark themselves **Ready**; when you are happy, press **Start**. You
   can also start alone and let friends join later (with DROP-IN on).

A code has eight letters and digits, sometimes shown with a dash in the middle. It never contains 0, O, 1, I or L.
Anyone with a private room's code can join, so share it only with the people you want to play with. Codes are
temporary: ask for the current one after the host opens a new room.

## Join by code

1. Choose **Join by code** and paste or type the code. Lower case, spaces and dashes are fine.
2. Join. You arrive in the host's lobby; mark yourself **Ready** and wait for the host to start.

If the game has already started, you join it in progress (below) - or, when the host's DROP-IN is off, you are told
that the session has started and to ask the host to start a new session.

## Browse public games

**Browse** lists public rooms: the host, the campaign, the player count and whether drop-in is on. Pick a room and
join it; **Refresh** checks again, and the page buttons move through longer lists. An empty list says so - host a
public game yourself or ask a friend for a code. A room missing from the list may still be joinable by code. Private
rooms are never listed.

## Join a game in progress

**Joining a game in progress is on by default** (`[Online] LateJoin=1`; the host's **DROP-IN** row turns it off for
one room). When you join a running game with a free place, you wait on **Joined Game** while the others keep playing.
At the host's **next area load** everyone, the host included, reloads that area together from the host's campaign, so
that load takes a little longer - then you are in, controlling a free hero. You do not appear in the middle of the
current area. The party needs a free hero for you. If you set `LateJoin=0` yourself in `xml2-fix.ini`, a rebuild or
repair keeps your choice. It works with two, three and four players, at any exit and in areas with enemies; two
friends who are waiting at the same time both come in at the same exit.

While you get the host's game, the host and the other players wait up to 10 seconds on **A player is joining...** (or
**2 players are joining...**) instead of playing on and then replaying that moment. The wait is the
`[Online] JoinHoldSeconds` setting in `xml2-fix.ini`: default 10, up to 15, and `0` turns it off. Each PC
uses its own value, and it does not have to match between players. If a join takes longer than the wait (a slow
connection), play continues and you come in moments later.

During a solo story segment, players without a hero stay connected and watch. The game says **Solo story segment -
you rejoin when it ends**; when the story restores a larger party you get a hero back (your previous one when the
group has not changed). Wolverine's opening and Magma's mansion tour are examples. Keep the watching PC connected.

## The Party screen

During play, the pause menu's **Party** row opens the Party screen: who is in the game and what each player is doing
(playing, loading, waiting for the next area, watching a story segment), the room code to invite more friends, and
**Leave**. The host can also **Kick** a player.

## Leaving and lost connections

Use **Leave** (or the game's normal quit) when you can. The host keeps playing, the departed player's hero returns to
computer control, and someone can join again at the next area.

If a guest freezes, crashes or loses their connection in a game of three or more, the remaining players agree when to
remove that player and carry on together. The departed player can join again by code. With only a host and one
guest, the host keeps hosting after the guest leaves.

**If the host leaves, freezes or loses connection, the session ends for everyone else.** Guests see **THE HOST LEFT**
with **Host again** (continue from a save on your own PC) and **Back to Online**. There is no host migration or
automatic reconnection yet (planned for 0.8). A sudden host crash can take about ten seconds to be noticed. A failed
shared-campaign restore can also mean hosting again.

If the online service becomes unavailable during a game, existing players stay connected but new players cannot join.
A service restart loses its rooms: host again for a new code. Slow PCs may show LAG warnings; the slow-player drop is
disabled.

## Messages and what to do

The in-game Play Online screens name the cause and the next step of every failure, one message at a time, on the screen
you are on. Host and Join stay open; nothing here restarts the game. **Retry** appears only where trying the same thing
again can help, and waits (with a countdown in the corner of the message) for the online service's request spacing.
The small grey text beside a message is a redacted diagnostic (`join: room_full`): it never contains codes, addresses or
service text, so it is safe to quote in a report.

| Message | Cause | What to do |
|---|---|---|
| Code not found. Ask the host for the current code. | The service has no open room for that code. | Edit the code or ask the host; Back leaves the screen. |
| That room closed. Ask the host for a new code. | The room closed before you got in. | Ask the host to host again; Edit the code. |
| That game is full. Try another game or ask for a new code. | All four places are taken. | Browse another game. |
| This session has started. Ask the host to start a new session. | The host's DROP-IN is off and the game has started. | Ask the host to start a new session, or to turn DROP-IN on for the next room. There is no Retry. |
| Not taking players right now. Try again soon. | The room exists but is not taking players at the moment (it is loading, its places just changed, or the list could not confirm that the game has started). | Retry (spaced by the service limit) or Browse. |
| Different game version. Update to the same build. | The host's build differs; the grey line names both builds (`LC36 vs your LC37`). | Update together, then try again. |
| Too many requests. Wait a few seconds, then retry. | The service limit; the grey line counts down. | Wait; Retry and Refresh stay off until it ends. |
| The online service did not answer. Try again. | A timeout, or Host > Open while the service never answered (nothing was lost: no room existed yet). | Retry. |
| Can't reach the service. Retry; LAN and IP still work. | No connection to the service. A running game is not affected. | Retry, or use Other ways to play. |
| The online service refused this game. Update the game. | The service rejected this build or its sign-in. | Update the game and launcher. |
| Online service not verified. Check its setting or update. | The service's certificate is not the one this build trusts. | Update; check for connection interception. There is no bypass. |
| TestMode is on, so online play is off. Turn it off. | `[TestMode]` blocks online play. | Turn TestMode off and restart through Host/Join. |
| Online needs a complete install. Use Other ways to play. | A required install guard failed (rooms, save format, native lists), or `xml2-fix.ini` lacks `[Online] Transport=gns`. | Verify Files and Rebuild; or play by LAN/IP. |
| The network link is busy. Wait a moment, then repeat. | The previous connection is still closing. | Wait a moment, then press the screen's own button again (Done, Open the room, Refresh); there is no Retry button for this one. |
| Room name must be 1-32 plain characters. Go Back. | The room name has characters the service does not accept. | Shorten it; no `;` or `"`. |
| Online service request failed. Retry or go Back. | Anything else (the diagnostic names the operation). | Retry; report the diagnostic if it repeats. |
| Could not find the host's game. Go Back and try again. | The host's game did not answer the lobby search. | Go Back and join again. |
| The host's game refused you. Check build and settings. / Refused. Settings possibly differ: {rules} | The host's game refused admission. The rule names are possibly (they share summary buckets). | Match builds and settings, then join again. |
| Took too long to connect. Go Back and try again. | A native step timed out. | Go Back and join again. |
| Lost the online service during setup. Try again. | The service dropped while the lobby was being set up. | Try again. |
| Game setup or admission failed. Go Back and try again. | Any other native setup step failed. | Go Back and try again. |
| Could not open the clipboard. Type the code instead. / No code on the clipboard. Copy the 8-symbol code first. | The clipboard could not be opened / holds no text or no code (an empty clipboard or an image reads as "no code"). | Type the code; a valid typed code is never erased. |
| {Name} left or lost connection. The party continues; they can rejoin with the code. | A guest left the lobby (six seconds, then it clears). | Nothing; the code still works. |
| Online service lost. Players here stay connected; new players cannot join. | The service dropped while your room was open. | Keep playing; host again later for a new code. |
| THE HOST LEFT: Host again to continue from a save on this PC. | You were a guest and your connection to the host ended. The 0.6 game ends; there is no takeover. | **Host again** opens Host setup (choose a new or saved campaign); **Back to Online** closes the panel. It shows only when the game's connection to the host ended (a lost or crashed host, or the 10 s watchdog); other ways a session can end (a normal host quit, removal by the host) are not claimed as host loss and show only the game's own message. |

## The online service and privacy

The project's **broker** is a small service that introduces the players and maintains temporary rooms and codes. The game tries a direct connection and can use a relay when the networks need it (successful relayed play is not verified yet; relay-only mode refuses an unavailable relay instead of falling back to a direct connection). Code-based online play needs no port forwarding or router changes. The relay passes encrypted game traffic between players; the broker is not a server that runs your campaign.

Public games connect players directly, so players can see each other's internet address. Use a private code to play only with friends; a private code does not hide your address from the friends in your session.

The broker allows at most **two public rooms** and **two seats in other people's rooms per internet address**. Players sharing a router or hotspot share these limits. If a limit is reached, leave unused rooms and retry rather than repeatedly starting games.

Rooms and memberships live in memory and disappear when closed, expired or the service restarts. Public rooms share their room name, online screen name, level, mode, version and player count with the browser. Private rooms stay out of that list.

No personal account is required. Operational logs include network connection details, an installation identifier and join codes. The deployment keeps a limited amount of logs; a room's disappearance does not erase its log entries. Use a screen name and room name you are happy to share. Keep active private codes out of public reports.

## Messages in Ultimate Legends' Online panel (0.4 and 0.5)

Up to 0.5, online play started from the launcher's Online panel. These are its English messages, including input checks, disabled controls and public-browser failures. Values in braces vary. If a message includes **Details**, keep that text with your report after removing private connection details.

| Message | What to do |
|---|---|
| Can’t reach the online service | Check the internet connection, close the game and try hosting/joining again. If it continues, try later; the service may be unavailable. |
| This game version can’t go online | Update and Rebuild the game in the Build section. Online rooms need XML2 Fix 1.8.0 or later. |
| Code not found | Check the current code with the host and make sure they have opened Play Online and kept the room running. |
| Code expired | Ask the host to open a new room and share its new code. |
| The game is full | All four places are taken (`room_full`); wait for a place. |
| That game can't take new players right now. Try again in a moment. | The room exists but is temporarily not accepting players (`room_closed`, contract v1.5). Wait and retry; it need not be full. |
| Different game version | Everyone should Rebuild to 0.4.0 and use matching game content/settings. 0.2.x cannot join 0.4.0. Browse games compares the room token with your build's GameVersion (`LC33`); matching builds should have Join enabled when a place is available. |
| Test mode is on | Turn Test mode off, close the game and host/join again. |
| The online service could not be verified | Update the game and launcher, check for connection interception on the network, and report persistent failures. Do not bypass the check. |
| Something went wrong | Close the game and retry. If repeated, collect `xml2-fix.log`. |
| The game reported a problem ({id}) | Keep the complete message and collect `xml2-fix.log`; close the game before retrying. |
| Type the code your host sent you first. | Paste the current code into Join a game. |
| A code has 8 letters and digits; this one has {count}. Check it with your host. | Copy the whole code again. Spaces and dashes are ignored. This covers both short and long codes. |
| A code has only letters and digits, never 0, O, 1, I or L: “{characters}” is not part of one. Check it with your host. | Ask the host to copy the code rather than guessing the characters. |
| Use up to 32 letters, digits, spaces and simple punctuation (no ; or "). | Shorten the room name and remove accented letters, emoji, semicolons and double quotes. |
| The code could not be copied: it is {code}. | Copy or type the displayed code yourself. |
| Online play needs XML2 Fix 1.8.0 or later; this folder has {version}, which can’t host or join. Use Verify Files on this page to update it. | Use Verify Files before trying again. |
| Set up X-Men Legends first (Set up, above) to play online. / Set up X-Men Legends first. | Complete Set up on this game page. |
| Build the game first (Build section below) to play online. | Complete the game build. |
| Install the {fix} first (Verify Files on this page) to play online. / Install the XML2 Fix first (Verify Files on this page). | Use Verify Files to install the fix. |
| A build is running: host or join when it has finished. / A build is running in the game folder: host or join when it has finished. | Let the build finish before hosting or joining. |
| The XML2 Fix is being installed or updated: host or join when it has finished. | Wait for installation to finish. |
| Another game is updating: host or join when it has finished. | Wait for the launcher's update work to finish. |
| Test mode is on, and the XML2 Fix turns online play off while it is. Turn it off to play online. / Test mode is on: turn it off, then host or join again. | Use Turn test mode off, then restart through Host or Join. |
| X-Men Legends is running. Close it to host or join a game. / X-Men Legends is already running. Close it, then host or join again. | Close the running game first. |
| This game has no online play here. | Use the X-Men Legends page and a launcher with the 0.4.0 online panel. |
| The game has not finished building. | Finish or resume the build before trying again. |
| The launcher sent the game a request it does not know: {error} | Update the launcher; report the full error if it repeats. |
| The online settings could not be saved: {error} | Close the game, check that its folder can be written to and retry. Keep the full error if it repeats. |
| The game did not start. Try again; if it keeps happening, start it with Play to see why. | Try normal Play and record the explanation it gives. |
| The list was refreshed too often. It refreshes again in a moment. | Wait about 30 seconds before refreshing again. |
| The online service is busy. The list refreshes again in a moment. | Wait about 30 seconds; do not repeatedly press Refresh. |
| The game list could not be read. It tries again in a moment; if it keeps happening, update the launcher. | Allow the next refresh, then update/report if it persists. |
| Full | All room places are occupied, including waiting players. Wait for someone to leave. |
| Can’t join right now | The room is temporarily refusing joins. Wait and refresh; it need not be full. |
| Rebuild to play online | The launcher cannot find this folder's game version. Rebuild the game. |
| No public games right now – host one and turn on List my game publicly. | This is an empty list, not a connection error. Host publicly or ask a friend for a code. |
| Open Play Online in the game – your code appears here. / Open Play Online → Join Game in the game. | Follow the named in-game menu. Waiting at the main menu will not finish connecting. |
| Found it. In the game: Play Online → Join Game, pick the game. | Select the host in the game's list to complete joining. |
| The online game has ended. / The game was closed. | The run has finished. Start Host or Join again for another run. This message alone does not diagnose a crash. |

When reporting a problem, include the exact message, the step that failed, everyone's game/fix versions, whether anyone used a hotspot, and each affected PC's `xml2-fix.log` and `online-status.json`. Copy them before the next launch. Review copies for private details before sharing; do not attach game files, saves, disc images or online identity keys.

Beta.3: solo-host pause and Team Management close with one B or Esc press; Enter IP has eleven keys (0-9 and dot).
A newcomer lost during the hold no longer produces a false lost-sync alarm. If lost after the restart begins,
the standard dropped-players message can still appear once (cosmetic; wording fix planned).

Beta.4 closes the cosmetic named-leave wording issue for a newcomer lost after restart begins. Same-PC RC1
checks observed named notices, matching frames and movement; ordinary in-play host drop wording is unchanged.
The newer RC2/RC3 agent probes did not re-accept native online-host Load Saved Campaign (online unavailable).
Normal main-menu campaign loading passed separately. beta.1/2/3 saves remain compatible; online peers need beta.4.
