"""Drive a --tour build of the XML1 port through every zone and record what happens.

usage: tour_runner.py <tour_build_dir> <results_dir> [--start-index N] [--count N] [--stall-seconds S] [--resume]
                      [--mortal]
--start-index: the first stop (0-based, _tour.json order); --count: only N stops from there (a slice; the run ends
as soon as the slice's last stop is in).

Launches XMen2.exe under tools/gamedbg.py and starts a new game (Enter presses until the HUD shows).
The zone actually running is read from the game's memory (tools/current_zone.py), so every result
is labelled by the real zone name. Per zone it records the time it became current and saves one
screenshot once the in-game HUD is visible. Failure handling:
  - game process dies        -> the current zone is 'crash' (while loading if no HUD was seen yet)
  - the next tour zone does not become current within --stall-seconds after the current zone
    loaded                   -> the next zone is 'load-failed' (the chain stalls or loops)
After a failure the game restarts at the zone after the failed one (Scripts/menus/new_game.py).
Results: <results_dir>/tour_results.json, screenshots in <results_dir>/shots/. --resume keeps the results file
and adds to it (with --start-index: where to go on).

The hero is kept alive (since SPEC 24 NPC attacks do XML1's damage: an idle level-1 Wolverine loses ~40 % of his
health in nuke1_1's 12 s and dies a few stops later, which stalls the tour on the game-over dialog,
and a low health bar reads as "no HUD"): whenever the HUD comes up in a zone (a new zone = a new hero actor), the
pipe runs setInvulnerable("_ACTIVE_HERO_","TRUE") + restoreHealth("_ACTIVE_HERO_",10000) - the keep-alive of the
2026-09-29 regression runs (research/regression/2026-09-29_overnight.md: 154/154 in one session with it). Each
zone record says keep_alive ok / failed. --mortal: no keep-alive (the tour as it ran before SPEC 24).

Which game: only the XMen2.exe of <tour_build_dir> is watched and killed (current_zone.game_pid(build) /
kill_build(build)); other folders' games (a second test window, Owen's play build) are never touched. Keys, frames
and the keep-alive go through the pipe the build's xml2-fix.ini names ([Test] PipeName; fixinput.use_build: no
XML2FIX_PIPE needed, and one naming another game's pipe is refused).

Input and capture: with the xml2-fix harness installed in the build (tools/harness.py install: [Display]
Mode=windowed RunInBackground=1, [Test] InputPipe=1) keys go through the fix's pipe and frames are copied from
the game's back buffer (tools/fixinput.py), so the game never needs the focus and can sit behind other windows.
Without the pipe it falls back to SendInput (which brings the window forward) and screen grabs, with no keep-alive.
"""
import ctypes, ctypes.wintypes as w, json, os, subprocess, sys, time
from PIL import Image, ImageGrab

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gameinput  # noqa: E402
import fixinput  # noqa: E402
import current_zone  # noqa: E402

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()
TITLE = 'X-Men Legends 2'
LIVE_SHOT = None  # where the pipe's frame for the per-second HUD check lands (set in main)


def client_bbox():
    hwnd = user32.FindWindowW(None, TITLE)
    if not hwnd:
        return None
    rect = w.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    pt = w.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return (pt.x, pt.y, pt.x + rect.right, pt.y + rect.bottom)


def grab():
    if LIVE_SHOT and gameinput.use_pipe():
        # the frame the game just drew, from inside the game: works with the window covered or unfocused
        try:
            fixinput.screenshot(LIVE_SHOT)
            with Image.open(LIVE_SHOT) as img:
                return img.convert('RGB')
        except (SystemExit, RuntimeError, OSError):
            return None
    box = client_bbox()
    if not box or box[2] - box[0] < 100:
        return None
    try:
        return ImageGrab.grab(bbox=box, all_screens=True)
    except OSError:
        return None


def hud_visible(img):
    """Red health-bar fill in the bottom-left HUD (fractions of the client area)."""
    w_, h_ = img.size
    region = img.crop((int(w_ * 0.16), int(h_ * 0.868), int(w_ * 0.26), int(h_ * 0.884))).convert('RGB')
    px = list(region.getdata())
    red = sum(1 for r, g, b in px if r > 170 and g < 90 and b < 70)
    return red / max(1, len(px)) > 0.3


def kill_game(build):
    """End this build's XMen2.exe only (never another folder's game)."""
    current_zone.kill_build(build)
    time.sleep(2)


# the regression runs' keep-alive: invulnerable + a full heal, one pipe line (statements joined with \n\r)
KEEP_ALIVE = r'setInvulnerable("_ACTIVE_HERO_","TRUE")\n\rrestoreHealth("_ACTIVE_HERO_",10000)'


def keep_hero_alive():
    """'ok', or 'failed: <why>' (the pipe is down / busy, or the game didn't read its keyboard for 2 s)."""
    try:
        fixinput.script(KEEP_ALIVE)
        return 'ok'
    except (fixinput.PipeError, SystemExit, RuntimeError, ValueError, OSError) as e:
        return f'failed: {e}'


def set_new_game(build, zone):
    path = os.path.join(build, 'Scripts', 'menus', 'new_game.py')
    open(path, 'wb').write(('# tour_runner start\r\nsetCurrentAct(1 )\r\nloadMapKeepTeam("%s" )\r\n' % zone).encode())


def main(build, results, start_index=0, stall=75, keep_alive=True, count=0):
    global LIVE_SHOT
    build = os.path.abspath(build)
    pipe_name = fixinput.use_build(build)  # the build's own pipe (SystemExit if XML2FIX_PIPE names another)
    if keep_alive and pipe_name is None:
        print(f'note: {build} has no pipe harness ([Test] InputPipe=1): no keep-alive, the hero can die')
    os.makedirs(os.path.join(results, 'shots'), exist_ok=True)
    LIVE_SHOT = os.path.join(results, 'shots', '_live.bmp')  # .bmp: cheapest for the once-a-second HUD check
    order = json.load(open(os.path.join(build, '_tour.json')))['order']
    pos = {z: i for i, z in enumerate(order)}
    state_path = os.path.join(results, 'tour_results.json')
    state = {'zones': {}, 'attempts': [], 'events': []}
    if RESUME and os.path.exists(state_path):
        state = json.load(open(state_path))
        state.pop('finished', None)
    state.update(build=build, pipe=pipe_name, keep_alive=bool(keep_alive and pipe_name))

    def save():
        json.dump(state, open(state_path, 'w'), indent=1)

    def mark(zone, status, **extra):
        rec = state['zones'].setdefault(zone, {'index': pos.get(zone, -1)})
        if rec.get('status') == 'ok' and status != 'ok':
            rec.setdefault('later', []).append(status)
        else:
            rec['status'] = status
        rec.update(extra)
        save()

    last = min(len(order), start_index + count) if count else len(order)   # the stops of this run: [start, last)
    idx = start_index
    while idx < last:
        set_new_game(build, order[idx])
        kill_game(build)
        log = os.path.join(results, f'gamedbg_{idx:03d}.log')
        subprocess.Popen([sys.executable, os.path.join(HERE, 'gamedbg.py'), log, os.path.join(build, 'XMen2.exe')])
        state['attempts'].append({'start_index': idx, 'start_zone': order[idx], 'log': log,
                                  'time': time.strftime('%H:%M:%S')})
        save()
        t0 = time.time()
        pid = None
        current, since, hud_since, shot_done = None, time.time(), None, False
        presses, last_press = 0, 0
        next_idx = idx
        # progress = the furthest tour stop that reached the HUD in this attempt; a failed load bounces the
        # game back to the previous zone (the zone name flips back and forth), so stalls are measured from
        # the last time progress advanced, not from the last zone-name change
        best, progress_at = idx - 1, None
        kept, kept_zone, kept_at = {}, None, 0.0   # keep-alive: zone -> result; the zone / time of the last one
        while True:
            time.sleep(1.0)
            now_pid = current_zone.game_pid(build)  # this build's game only
            pid = pid or now_pid
            alive = now_pid is not None
            if not alive:
                if current and current != 'menu/main_back':
                    mark(current, 'ok-then-crash' if shot_done else 'crash-loading', log=log)
                    next_idx = pos.get(current, next_idx) + 1
                else:
                    mark(order[next_idx], 'crash-before-start', log=log)
                    next_idx += 1
                state['events'].append({'t': time.strftime('%H:%M:%S'), 'event': 'died', 'zone': current})
                save()
                break
            zone = current_zone.read_zone(pid) if pid else None
            img = grab()
            hud = img is not None and hud_visible(img)
            now = time.time()
            if zone != current:
                state['events'].append({'t': time.strftime('%H:%M:%S'), 'event': 'zone', 'zone': zone})
                current, since, hud_since, shot_done = zone, now, None, False
                if zone in pos:
                    next_idx = pos[zone] + 1
                save()
            # New Game was accepted but the start zone was rejected: the game returns to the menu
            # without ever showing a HUD. Record the start zone and move on to the next one.
            if current in ('', 'menu/main_back') and presses >= 2 and best < idx and now - last_press > 45:
                mark(order[idx], 'load-failed', log=log, note='rejected as New Game start zone')
                next_idx = idx + 1
                break
            # still in the front end: press Enter until the game starts (New Game, difficulty, any notice)
            if (current in (None, '', 'menu/main_back')) and not hud:
                if now - t0 > 35 and now - last_press > 5 and presses < 12:
                    try:
                        gameinput.focus()
                        gameinput.key('enter')
                    except SystemExit:
                        pass
                    presses, last_press = presses + 1, now
                if now - t0 > 240:
                    mark(order[idx], 'never-started', log=log)
                    next_idx = idx + 1
                    break
                continue
            if hud:
                if hud_since is None and state['keep_alive'] and (current != kept_zone or now - kept_at > 10):
                    # the HUD came up: the zone's hero actor exists (a new zone = a new, unprotected actor)
                    res = keep_hero_alive()
                    kept[current], kept_zone, kept_at = res, current, now
                    if res != 'ok':
                        state['events'].append({'t': time.strftime('%H:%M:%S'), 'event': 'keep-alive',
                                                'zone': current, 'result': res})
                hud_since = hud_since or now
                if not shot_done and now - hud_since > 3 and current in pos:
                    path = os.path.join(results, 'shots', f'{pos[current]:03d}_{current.replace("/", "_")}.png')
                    img.save(path)
                    extra = {'keep_alive': kept.get(current, 'not sent')} if state['keep_alive'] else {}
                    mark(current, 'ok', shot=path, loaded=time.strftime('%H:%M:%S'),
                         load_seconds=round(hud_since - since, 1), **extra)
                    shot_done = True
            else:
                hud_since = None
            if current in pos and pos[current] > best and (shot_done or now - since > 20):
                # reached a new tour stop (with HUD, or a HUD-less stop such as a briefing that stayed 20 s)
                best, progress_at = pos[current], now
                if not shot_done and current not in state['zones']:
                    mark(current, 'ok-no-hud')
                if count and best >= last - 1:
                    break                           # --count: the slice's last stop is in; no end-of-tour wait
            if progress_at is None and current in pos:
                progress_at = progress_at or since
            # stall: the stop after `best` should arrive about 12-15 s after `best` loaded
            if progress_at is not None and now - progress_at > stall:
                nxt = best + 1
                if nxt >= last:
                    break
                if best >= 0 and order[best] not in state['zones']:
                    mark(order[best], 'no-hud', log=log)
                mark(order[nxt], 'load-failed', log=log, stuck_in=order[best] if best >= 0 else current)
                next_idx = nxt + 1
                break
            if current not in pos and current not in (None, '', 'menu/main_back') and now - since > stall:
                mark(current, 'unexpected-zone', log=log)
                next_idx += 1
                break
        idx = next_idx
        if current in pos and pos[current] >= last - 1 and shot_done:
            break
    kill_game(build)
    state['finished'] = time.strftime('%H:%M:%S')
    save()
    counts = {}
    for z in state['zones'].values():
        counts[z['status']] = counts.get(z['status'], 0) + 1
    print('done', counts)


RESUME = False

if __name__ == '__main__':
    args = sys.argv[1:]
    if '--resume' in args:
        args.remove('--resume')
        RESUME = True
    mortal = '--mortal' in args
    if mortal:
        args.remove('--mortal')
    start, stall, count = 0, 75, 0
    if '--start-index' in args:
        i = args.index('--start-index'); start = int(args[i + 1]); del args[i:i + 2]
    if '--stall-seconds' in args:
        i = args.index('--stall-seconds'); stall = int(args[i + 1]); del args[i:i + 2]
    if '--count' in args:
        i = args.index('--count'); count = int(args[i + 1]); del args[i:i + 2]
    if len(args) != 2:
        sys.exit(__doc__)
    main(args[0], args[1], start, stall, keep_alive=not mortal, count=count)
