# Now Playing Widget

A small retro desktop widget that shows **what you're listening to**: Spotify (app or web), YouTube, or anything else that shows up in Windows' media controls. No Spotify Premium, no API keys, no login.

## Download & install (no Python needed)

1. Go to the **[Releases page](../../releases/latest)** and download **`Now-Playing-Widget.zip`**.
2. Right-click the zip → **Extract All…** → pick a folder you'll keep, e.g. `Documents\Now Playing`.
   (Don't run it from inside the zip.)
3. Open the extracted **Now Playing** folder and double-click **`Now Playing.exe`**.
4. Windows may say **"Windows protected your PC"**. That's because the app isn't signed with a paid certificate.
   Click **More info → Run anyway**. You only need to do this once.
5. Play something on Spotify or YouTube. The widget shows it.
6. Optional: right-click the widget → **Start with Windows**.

Needs Windows 10 or 11 with the Microsoft Edge WebView2 runtime (already built into Windows 11; on Windows 10 get it free from Microsoft if the widget opens blank).

## What it does

- Song, artist, album and **cover art** (YouTube videos get their real album cover looked up)
- **Synced lyrics**, line by line
- **Play / pause / skip / seek** and a per-app **volume** knob
- A **visualizer** that moves with the music
- **4 styles**: CD Player · Cassette · Millennium · Silverdeck, plus colour themes (including *Album*, which takes its colours from the cover)
- **–** folds it into a small floating bubble · **Pin to desktop** puts it behind your windows
- Soft button sounds (can be switched off)

**Everything is in the right-click menu:** styles, Pin to desktop, Button sounds, Start with Windows.

## Privacy

To find covers and lyrics, the widget sends the **song title and artist** to Apple's iTunes Search and to LRCLIB. Nothing else leaves your PC. Your settings and log are in `%APPDATA%\Now Playing Widget`.

## Uninstall

1. Right-click the widget → untick **Start with Windows** → close it.
2. Delete the app folder and `%APPDATA%\Now Playing Widget`.

---

## For developers

```
pip install -r requirements.txt
python app.py            # run from source
python app.py --test     # self-check
build.bat                # build release\Now-Playing-Widget.zip
```

| File | What it is |
|---|---|
| `app.py` | reads Windows' media info, lyrics, covers, window handling |
| `audio.py` | visualizer sound capture + per-app volume |
| `skins/widget.js` | shared logic for every style |
| `skins/*.html` | one file per style; add a file to add a style |
| `bubble.html` | the mini bubble |
| `measure.py` | measures each style's CPU and RAM |
| `LESSONS.md` | how and why everything works, step by step |
