"""Retro 'now playing' desktop widget.

Reads what Windows already knows is playing (SMTC: the same data as the
volume-key media popup), so no Spotify API or Premium is needed.
Run:  python app.py        Self-check:  python app.py --test
"""
import asyncio
import base64
import colorsys
import ctypes
import faulthandler
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from ctypes import wintypes
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import webview
from PIL import Image
import audio
from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
from winrt.windows.storage.streams import Buffer, InputStreamOptions

FROZEN = getattr(sys, "frozen", False)  # True when running as the packaged .exe (PyInstaller)
HERE = Path(sys._MEIPASS) if FROZEN else Path(__file__).parent  # where the app's own files (skins/, bubble.html) are
SKINS = HERE / "skins"  # every .html in here is a style; its <title> is the name in the menu
# YOUR files (settings, log) live in AppData: writable, kept when the app is updated or moved
DATA = Path(os.environ["APPDATA"]) / "Now Playing Widget"
SETTINGS = DATA / "settings.json"
STARTUP_LINK = Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup\Now Playing Widget.lnk"
PLAYING = 4  # Windows' code for "playing"
TITLE_TAG = re.compile(r"<title>(.*?)</title>")
BUBBLE = 64  # size of the mini bubble, in px
ACTIONS = {"toggle_play_pause", "skip_next", "skip_previous", "stop"}
BRACKETS = re.compile(r"[(\[][^)\]]*[)\]]")  # "(Official Video)", "[Lyrics]", "(feat. X)"
FEAT = re.compile(r"\s+(ft\.?|feat\.?|featuring)\s.*$", re.I)
LRC_LINE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)")  # "[01:07.40] Pee loon," -> minutes, seconds, text

songs = {}   # (artist, title) -> what we show; so each song is read / looked up once
lyrics = {}  # (artist, title) -> lyrics; same idea


def clean_title(title, channel):
    """YouTube 'Artist - Song (Official Video)' on channel 'ArtistVEVO' -> ('Artist', 'Song')."""
    title = BRACKETS.sub("", title).replace("|", " ").strip()
    if " - " in title:
        artist, song = title.split(" - ", 1)
    else:
        artist, song = re.sub(r"(\s*-\s*Topic|VEVO)$", "", channel), title
    return artist.strip(), FEAT.sub("", song).strip()


def itunes_lookup(artist, song):
    """Free iTunes search, no key. Returns (cover_url, album) or (None, '')."""
    query = urllib.parse.urlencode({"term": f"{artist} {song}", "entity": "song", "limit": 1})
    try:
        with urllib.request.urlopen(f"https://itunes.apple.com/search?{query}", timeout=5) as r:
            hits = json.load(r)["results"]
    except Exception:
        return None, ""
    if not hits:
        return None, ""
    # shortcut: trusts iTunes' top hit without checking it matches; add a name check if you see wrong covers
    return hits[0]["artworkUrl100"].replace("100x100", "600x600"), hits[0].get("collectionName", "")


def dominant_color(img):
    """The cover's most striking colour: squeeze it to 8 colours, then pick the one that is
    common AND vivid (a big dull grey area shouldn't win over a smaller bright red one)."""
    small = img.convert("RGB").resize((48, 48)).quantize(8)
    palette = small.getpalette()
    def score(item):
        count, idx = item
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in palette[idx * 3: idx * 3 + 3]))
        return count * (0.1 + s) * (0.2 + v) if v > 0.15 else 0  # near-black never wins
    _, idx = max(small.getcolors(), key=score)
    return "#%02x%02x%02x" % tuple(palette[idx * 3: idx * 3 + 3])


def cover_color(cover):
    """Colour for the 'album' theme from a data: URL or a web URL. None if it can't be read."""
    try:
        if cover.startswith("data:"):
            raw = base64.b64decode(cover.split(",", 1)[1])
        else:
            with urllib.request.urlopen(cover, timeout=5) as r:
                raw = r.read()
        return dominant_color(Image.open(BytesIO(raw)))
    except Exception:
        return None


def parse_lrc(text):
    """LRC text -> [[seconds, line], ...]"""
    return [[int(m) * 60 + float(s), line.strip()] for m, s, line in LRC_LINE.findall(text)]


def lyrics_query(artist, title):
    """Spotify says 'A, B' and 'Song - Remastered 2011'; LRCLIB finds more with 'A' and 'Song'."""
    return artist.split(",")[0].strip(), re.sub(r"\s+-\s+.*$", "", BRACKETS.sub("", title)).strip()


def lrclib_lyrics(artist, title, dur):
    """Free LRCLIB search, no key. Returns {'synced': bool, 'lines': [[seconds, text], ...]} or None on network error."""
    a, t = lyrics_query(artist, title)
    req = urllib.request.Request(
        "https://lrclib.net/api/search?" + urllib.parse.urlencode({"artist_name": a, "track_name": t}),
        headers={"User-Agent": "cd-player-widget"})  # LRCLIB asks apps to name themselves
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            hits = json.load(r)
    except Exception:
        return None
    if not hits:
        return {"synced": False, "lines": []}
    # best hit: has timestamps first, then the length closest to the song playing (skips edits/remixes)
    hit = min(hits, key=lambda h: (not h.get("syncedLyrics"), abs((h.get("duration") or 0) - dur)))
    if hit.get("instrumental"):
        return {"synced": False, "lines": [[0, "♪ Instrumental ♪"]]}
    if hit.get("syncedLyrics"):
        return {"synced": True, "lines": parse_lrc(hit["syncedLyrics"])}
    return {"synced": False, "lines": [[0, line] for line in (hit.get("plainLyrics") or "").splitlines()]}


async def read_thumbnail(ref):
    """Windows hands us the cover as a stream of bytes; turn it into something <img> can show."""
    stream = await ref.open_read_async()
    buf = Buffer(stream.size)
    await stream.read_async(buf, buf.capacity, InputStreamOptions.READ_AHEAD)
    return f"data:{stream.content_type or 'image/jpeg'};base64,{base64.b64encode(bytes(buf)).decode()}"


def read_cover(ref, seconds=2):
    """Browsers sometimes never finish sending the cover, and that call blocks its whole thread
    (so asyncio timeouts can't fire). Read it on a helper thread and stop waiting after 2 s."""
    box = []
    helper = threading.Thread(target=lambda: box.append(asyncio.run(read_thumbnail(ref))), daemon=True)
    helper.start()
    helper.join(seconds)
    # shortcut: a stuck helper thread is left behind (one per stuck song, a few KB each); closing the widget clears them
    return box[0] if box else None


async def find_session(pick):
    manager = await Manager.request_async()
    for s in manager.get_sessions():
        if s.source_app_user_model_id == pick:
            return s, manager
    return manager.get_current_session(), manager


async def get_state(pick):
    s, manager = await find_session(pick)
    sources = [x.source_app_user_model_id for x in manager.get_sessions()]
    if s is None:
        return {"sources": sources}
    p = await s.try_get_media_properties_async()
    key = (p.artist, p.title)
    if key not in songs:
        song = {"artist": p.artist, "title": p.title, "album": p.album_title, "cover": None}
        if p.thumbnail:
            song["cover"] = read_cover(p.thumbnail)
        is_video = not p.album_title  # no album = a video site like YouTube
        if is_video:
            song["artist"], song["title"] = clean_title(p.title, p.artist)
        if is_video or not song["cover"]:  # YouTube, or the cover never came: look up the real one
            url, album = itunes_lookup(song["artist"], song["title"])
            song["cover"] = url or song["cover"]
            song["album"] = song["album"] or album
        song["color"] = cover_color(song["cover"]) if song["cover"] else None
        songs[key] = song
    else:
        song = songs[key]

    t = s.get_timeline_properties()
    playing = s.get_playback_info().playback_status == PLAYING
    pos = t.position.total_seconds()
    if playing:  # apps only report position now and then, so add the time since the last report
        pos += (datetime.now(timezone.utc) - t.last_updated_time).total_seconds()
    dur = t.end_time.total_seconds()
    return {**song, "sources": sources, "id": s.source_app_user_model_id,
            "playing": playing, "pos": min(pos, dur), "dur": dur}


async def do_control(pick, action, seconds):
    s, _ = await find_session(pick)
    if s is None:
        return
    if action == "seek":
        await s.try_change_playback_position_async(int(seconds * 10_000_000))  # Windows counts in 100ns ticks
    elif action in ACTIONS:
        await getattr(s, f"try_{action}_async")()


class Api:
    """Every method here can be called from the page's JavaScript as pywebview.api.<name>()."""

    def state(self, pick=None):
        return {**asyncio.run(get_state(pick)), "hidden": bubble_mode}  # "hidden": folded into the bubble

    def control(self, pick, action, seconds=0):
        asyncio.run(do_control(pick, action, seconds))

    def minimize(self):
        """The "_" button: fold the widget into the mini bubble (which floats on top)."""
        global bubble_mode
        bubble_mode = True  # the widget's next state() call sees this and stops its visualizer + animations
        show_window(widget_hwnd, False)
        show_window(bubble_hwnd, True)
        snap_bubble()

    def restore(self):
        """Click on the bubble: the full widget comes back where it was."""
        global bubble_mode
        bubble_mode = False
        show_window(bubble_hwnd, False)
        show_window(widget_hwnd, True)

    def bubble_move(self, x, y):  # x, y: where the bubble's top-left should be, in screen px from its JavaScript
        bubble.move(int(x), int(y))

    def bubble_snap(self):
        snap_bubble()

    def close(self):
        window.destroy()

    def bands(self):
        return audio.bands()

    def volume(self, source_id, level=None):
        return audio.app_volume(source_id, level)

    def pref(self, key, value=None):
        """Small per-style choices (like a colour theme) saved in settings.json."""
        if not re.fullmatch(r"theme(-\w+)?|viz|sounds", key):  # "theme" or a style's own "theme-<style>"
            return None
        if value is not None:
            settings[key] = str(value)
        return settings.get(key)

    def on_top(self, on=None):
        """Read, or with on=True/False set, whether the widget floats above other windows."""
        if on is not None:
            if on:
                settings["pinned"] = False  # can't float on top and sit on the desktop at the same time
            settings["on_top"] = bool(on)
            set_topmost(widget_hwnd, bool(on))
        return settings.get("on_top", True)

    def autostart(self, on=None):
        """Read, or with on=True/False set, whether the widget starts with Windows (a shortcut in the Startup folder)."""
        if on is True:
            make_shortcut(STARTUP_LINK)
        elif on is False:
            STARTUP_LINK.unlink(missing_ok=True)
        return STARTUP_LINK.exists()

    def pin(self, on=None):
        """Read, or with on=True/False set, whether the widget sits on the desktop behind all other windows."""
        if on is not None:
            settings["pinned"] = bool(on)
            set_topmost(widget_hwnd, settings.get("on_top", True) and not on)  # unpinning brings back your on-top choice
        return settings.get("pinned", False)

    def resize(self, w, h):  # each style knows its own size, so it tells us
        window.resize(int(w), int(h))
        keep_on_screen(widget_hwnd)  # a wider style near the screen edge would otherwise hang off the side

    def styles(self):
        return [[p.stem, TITLE_TAG.search(p.read_text(encoding="utf-8")).group(1), p.stem == settings["style"]]
                for p in sorted(SKINS.glob("*.html"))]

    def set_style(self, name):
        """Remember the choice; the page then navigates itself (load_url from here froze the window)."""
        if name not in [p.stem for p in SKINS.glob("*.html")]:  # only our own files, never a path the page made up
            return False
        settings["style"] = name
        return True

    def lyrics(self, artist, title, dur):
        key = (artist, title)
        if key not in lyrics:
            found = lrclib_lyrics(artist, title, dur)
            if found is None:  # network hiccup: don't remember "nothing", try again next time
                return {"synced": False, "lines": [], "error": True}
            lyrics[key] = found
        return lyrics[key]


def make_shortcut(link):
    """A Windows shortcut (.lnk) that starts this widget: the .exe when packaged, otherwise pythonw + app.py."""
    target = Path(sys.executable) if FROZEN else Path(sys.executable).with_name("pythonw.exe")  # pythonw: no console
    script = Path(__file__).resolve()
    ps = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:NP_LINK); $s.TargetPath = $env:NP_TARGET; "
          "$s.Arguments = $env:NP_ARGS; $s.WorkingDirectory = $env:NP_DIR; $s.IconLocation = $env:NP_ICON; $s.Save()")
    # the paths travel as environment variables, so a space or quote in a folder name can't break the command
    env = {**os.environ, "NP_LINK": str(link), "NP_TARGET": str(target), "NP_ARGS": "" if FROZEN else f'"{script}"',
           "NP_DIR": str(target.parent if FROZEN else script.parent), "NP_ICON": str(HERE / "icon.ico")}
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, check=True, creationflags=0x08000000)  # no window


def save_settings():
    settings.update(x=window.x, y=window.y)
    SETTINGS.write_text(json.dumps(settings))


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", ctypes.c_ulong)]


def work_area(hwnd):
    """The usable part (no taskbar) of the monitor a window is on, in real screen pixels."""
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    ctypes.windll.user32.GetMonitorInfoW(ctypes.windll.user32.MonitorFromWindow(hwnd, 2), ctypes.byref(info))
    return info.rcWork


def keep_on_screen(hwnd):
    """If any part of the window sticks out past its monitor's edges, slide it back in."""
    if not hwnd:
        return
    u, r = ctypes.windll.user32, wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    work = work_area(hwnd)
    x = max(work.left, min(r.left, work.right - (r.right - r.left)))
    y = max(work.top, min(r.top, work.bottom - (r.bottom - r.top)))
    if (x, y) != (r.left, r.top):
        u.SetWindowPos(hwnd, 0, x, y, 0, 0, 0x1 | 0x4 | 0x10)  # NOSIZE | NOZORDER | NOACTIVATE


def snap_bubble():
    """Glide the bubble to the nearest left/right edge of the screen it's on (above the taskbar), and remember it."""
    u = ctypes.windll.user32
    hwnd = bubble_hwnd
    scale = u.GetDpiForWindow(hwnd) / 96  # Windows works in real pixels, pywebview's move() in scaled ones
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    u.GetMonitorInfoW(u.MonitorFromWindow(hwnd, 2), ctypes.byref(info))  # 2 = the monitor nearest the bubble
    r, work, gap = wintypes.RECT(), info.rcWork, round(10 * scale)
    u.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    left_half = (r.left + r.right) / 2 < (work.left + work.right) / 2
    x = work.left + gap if left_half else work.right - w - gap
    y = min(max(r.top, work.top + gap), work.bottom - h - gap)
    for i in range(1, 9):  # 8 small steps, easing out: a glide instead of a jump
        t = 1 - (1 - i / 8) ** 3
        bubble.move((r.left + (x - r.left) * t) / scale, (r.top + (y - r.top) * t) / scale)
        time.sleep(0.012)
    settings["bubble"] = [round(x / scale), round(y / scale)]


# --- talking to the windows directly ---
# pywebview's own on_top / show() / hide() change a window from a background thread and WAIT for the window's
# thread, while holding Python's lock (the GIL). If the window's thread is busy starting a thread for the page's
# next call (it needs that same lock), both wait forever: the widget froze (found with py-spy, Lesson 22).
# These ctypes calls let go of the lock while Windows does the work, so they can't deadlock like that.
widget_hwnd = bubble_hwnd = None  # Windows' handles for the two windows, filled in once each page has loaded
bubble_mode = False               # True while the widget is folded into the bubble


def remember_hwnd():
    global widget_hwnd
    widget_hwnd = window.native.Handle.ToInt32()


def set_topmost(hwnd, on):
    HWND_TOPMOST, HWND_NOTOPMOST, NOSIZE, NOMOVE, NOACTIVATE = -1, -2, 0x1, 0x2, 0x10
    ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST if on else HWND_NOTOPMOST, 0, 0, 0, 0, NOSIZE | NOMOVE | NOACTIVATE)


def show_window(hwnd, on):
    SW_HIDE, SW_SHOW = 0, 5
    ctypes.windll.user32.ShowWindow(hwnd, SW_SHOW if on else SW_HIDE)


DESKTOP_LAYERS = {"Progman", "WorkerW"}  # Windows' own wallpaper/icon windows: we sit right above these


def class_name(hwnd):
    buf = ctypes.create_unicode_buffer(64)
    ctypes.windll.user32.GetClassNameW(hwnd, buf, 64)
    return buf.value


def keep_on_desktop():
    """While pinned: if any app window has ended up BELOW the widget (e.g. after you clicked the widget),
    slide the widget down to just above the desktop layers. If everything is already right, do nothing.
    (The first version pushed it to HWND_BOTTOM 4x a second no matter what, which put it under the desktop
    layers and back again: that was the flicker.)"""
    # shortcut: polling, not hooking Windows' z-order messages. A hook would run Python on the window's own
    # thread, and that can deadlock against pywebview's calls (Lesson 22).
    u = ctypes.windll.user32
    GW_HWNDNEXT, NOSIZE, NOMOVE, NOACTIVATE, NOOWNERZORDER = 2, 0x1, 0x2, 0x10, 0x200
    while True:
        time.sleep(0.25)
        if not (settings.get("pinned") and widget_hwnd) or bubble_mode:
            continue
        lowest_app, h = None, u.GetWindow(widget_hwnd, GW_HWNDNEXT)  # walk down the stack from the widget
        while h:
            if u.IsWindowVisible(h) and class_name(h) not in DESKTOP_LAYERS and h != bubble_hwnd:
                lowest_app = h
            h = u.GetWindow(h, GW_HWNDNEXT)
        if lowest_app:  # something is under us: go just beneath the lowest one (still above the desktop)
            u.SetWindowPos(widget_hwnd, lowest_app, 0, 0, 0, 0, NOSIZE | NOMOVE | NOACTIVATE | NOOWNERZORDER)


def setup_bubble():
    """Remember the bubble's handle, and size it: the window starts at Windows' minimum (~150x50),
    pywebview's resize() sets the real size straight through Windows (a ctypes call, so it's deadlock-safe)."""
    global bubble_hwnd
    bubble_hwnd = bubble.native.Handle.ToInt32()
    bubble.resize(BUBBLE, BUBBLE)
    if not bubble_mode:
        show_window(bubble_hwnd, False)  # pywebview's resize() also SHOWS the window; keep it hidden until "_"


def self_test():
    assert clean_title("Daft Punk - One More Time (Official Video)", "DaftPunkVEVO") == ("Daft Punk", "One More Time")
    assert clean_title("Blinding Lights [Lyrics]", "The Weeknd - Topic") == ("The Weeknd", "Blinding Lights")
    assert clean_title("Drake - Passionfruit ft. Someone", "x") == ("Drake", "Passionfruit")
    assert parse_lrc("[00:51.78] Jaadu,\n[01:07.40] Pee loon,\n[01:08.53] ") == \
        [[51.78, "Jaadu,"], [67.4, "Pee loon,"], [68.53, ""]]
    assert lyrics_query("Lifafa, Hashback Hashish", "Hey Jude - Remastered 2015") == ("Lifafa", "Hey Jude")
    import numpy as np
    tone = np.repeat(np.sin(2 * np.pi * 1000 * np.arange(4096) / 48000) * 0.5, 2).astype(np.float32)  # 1 kHz, stereo
    b = audio.to_bands(tone, 2, 48000)
    assert b.index(max(b)) == 4 and sum(x > 0.1 for x in b) == 1, b  # only the 800-1600 Hz band lights up
    img = Image.new("RGB", (48, 48), (128, 128, 128))  # mostly dull grey...
    img.paste((220, 30, 40), (0, 0, 16, 48))           # ...with a vivid red stripe: red should win
    r, g, b = (int(dominant_color(img)[i:i + 2], 16) for i in (1, 3, 5))
    assert r > 180 and g < 80, dominant_color(img)
    print("self-test ok")


if __name__ == "__main__":
    if "--test" in sys.argv:
        self_test()
        sys.exit()
    # one widget at a time: a named "mutex" is a flag Windows keeps for the whole PC. If it already exists,
    # the widget is running (e.g. from Windows start), so bring that one forward instead of opening a second
    ctypes.windll.kernel32.CreateMutexW(None, False, "NowPlayingWidget.SingleInstance")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        u = ctypes.windll.user32
        mini, full = u.FindWindowW(None, "Now Playing mini"), u.FindWindowW(None, "Now Playing")
        u.SetForegroundWindow(mini if u.IsWindowVisible(mini) else full)  # folded into the bubble? then that's what you get
        sys.exit()

    # pythonw (used at Windows start) has no console: send errors from every thread to widget.log,
    # and let faulthandler write a stack trace even if Python itself crashes
    # shortcut: the log is never trimmed; it grows a few lines per start, delete it if it ever gets big
    DATA.mkdir(exist_ok=True)
    old = Path(__file__).parent / "settings.json"  # settings from before they moved to AppData: bring them along once
    if not SETTINGS.exists() and old.exists():
        SETTINGS.write_text(old.read_text())
    log = open(DATA / "widget.log", "a", buffering=1, encoding="utf-8")
    sys.stderr = log
    faulthandler.enable(log)
    print(f"--- started {datetime.now():%Y-%m-%d %H:%M:%S}", file=log)

    settings = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
    if "--style" in sys.argv:  # used by measure.py: python app.py --style cassette
        settings["style"] = sys.argv[sys.argv.index("--style") + 1]
    if not (SKINS / f"{settings.get('style')}.html").exists():
        settings["style"] = "cdplayer"
    window = webview.create_window(
        "Now Playing", str(SKINS / f"{settings['style']}.html"), js_api=Api(),
        width=460, height=204, x=settings.get("x"), y=settings.get("y"),  # the style resizes itself once loaded
        frameless=True, on_top=settings.get("on_top", True) and not settings.get("pinned"), resizable=False,
        background_color="#c0c0c0")
    window.events.loaded += remember_hwnd
    threading.Thread(target=keep_on_desktop, daemon=True).start()
    window.events.closing += save_settings
    window.events.closed += lambda: os._exit(0)  # closing the widget also ends the (maybe hidden) bubble
    bx, by = settings.get("bubble", (None, None))
    bubble = webview.create_window(
        "Now Playing mini", str(HERE / "bubble.html"), js_api=Api(), width=BUBBLE, height=BUBBLE, x=bx, y=by,
        frameless=True, on_top=True, resizable=False, hidden=True, background_color="#15171c",
        min_size=(BUBBLE, BUBBLE))  # pywebview never resizes below min_size, which is 200x100 unless we say so
    bubble.events.loaded += setup_bubble
    webview.start()
    os._exit(0)  # settings are saved; don't wait for a stuck cover thread (see read_cover) before quitting
