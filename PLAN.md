# Plan: three features for later

Order to build them in: **1 → 2 → 3**. Each one stands alone, so any can be skipped.

---

## 1. Mini bubble: minimize into a floating button that stays on top ✅ DONE

Built as a rounded tile (a true circle isn't possible with pywebview on Windows, see Lesson 21).

**What you get:** the `_` button shrinks the widget into a small round **bubble**: the album cover, spinning slowly while music plays. It floats above every window.
- **Click** the bubble → the full widget comes back where it was.
- **Hover** → song title + a ▶/❚❚ button.
- **Drag** it anywhere. It snaps to the nearest screen edge and remembers its spot.

**How it works:**
1. Python opens a second, tiny pywebview window (`bubble.html`, ~64×64 px, frameless, always on top).
2. Minimize hides the main window instead of minimizing it to the taskbar, then shows the bubble.
3. The bubble reuses `widget.js` for the song data, so there's no new data code.

**Risk:** frameless windows on Windows are square. A round bubble needs a transparent window, which pywebview supports badly on Windows. Fallback: a rounded square that matches the style's colours.

---

## 2. Pin to wallpaper: the widget lives *on* the desktop ✅ DONE (option B)

Built as option B, the clickable bottom window: right-click → **Pin to desktop**. Win+D still hides it.

## (original notes)

**What you get:** a **PIN** option. When pinned, the widget sits on the desktop behind all windows, like part of your wallpaper. You see it when you minimize everything (Win+D). Unpin brings it back to floating.

**How it works (two options; try A, fall back to B):**
- **A. Real wallpaper layer:** Windows draws the wallpaper in a hidden window called `WorkerW`. We ask Windows to create it (a known message, `0x052C`, sent to `Progman`), then make our window its child with `SetParent`. This is the same trick wallpaper apps like Lively and Wallpaper Engine use.
- **B. "Always at the bottom":** keep the window at the bottom of the window stack (`HWND_BOTTOM`) and put it back there whenever it gets clicked. Simpler and more reliable, but it's still a normal window.

**Risks:**
- Windows 11 24H2 changed how `WorkerW` works, so A must be tested on your PC first.
- When pinned under the desktop icons, **clicks may not reach the widget**. A pinned widget might be view-only, with unpin done from the tray or right-click.

---

## 3. Make it shareable ✅ 3a DONE

`release/Now-Playing-Widget.zip` (32.7 MB): unzip, run `Now Playing.exe`, no Python needed. Rebuild any time with `build.bat`.
Still open: a GitHub page (needs your account) and 3b, the "share what you're listening to" card.

## (original notes)

"Shareable" can mean two things. Pick one or both:

### 3a. Let friends install the widget (recommended)
1. **`requirements.txt` + `README.md`**: how to install and run (30 min).
2. **One `.exe` file** with PyInstaller: friends don't need Python. It'll be roughly 80–150 MB because Python, numpy and the audio libraries are inside (1–2 hours, mostly testing).
3. **GitHub repository + Releases page**: one link to share, and updates are easy (30 min).
4. Optional: **an installer** (Inno Setup) with a "Start with Windows" checkbox, replacing our manual Startup shortcut (1 hour).

**Before sharing:**
- Remove `settings.json` and `widget.log` from the package (your own position/theme and logs).
- Style names and looks stay "inspired by" (no Winamp/MMD3 names or logos), which they already are.

### 3b. Share what you're listening to
A **share button** that makes a picture card (cover + song + artist in the current style's look) and copies it to the clipboard, ready to paste into Discord or WhatsApp (~1–2 hours).

---

**Next step when you're ready:** say "start the plan with #1" (or any number).
