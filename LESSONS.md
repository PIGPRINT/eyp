# CD Player Widget: Lessons from a Lazy Senior Dev

Two files do all the work:
- `app.py` is the **brain**, written in Python. It asks Windows what's playing.
- `cdplayer.html` is the **face**, written in HTML and CSS. It draws the retro window.

(Since Lesson 10, the face is in `skins/`, and right-click switches styles.)

Run it:  `python app.py`

Run the self-check:  `python app.py --test`

---

## Lesson 1: Don't steal the data, ask the receptionist 🛎️

**Problem:** Spotify, YouTube and Brave are all separate programs. How can we know what each one is playing?

**Hard way:** Hack into each app, log into Spotify's API, scrape YouTube… three jobs that break easily.

**Lazy way:** Windows already has a receptionist called **SMTC** (System Media Transport Controls). Every media app checks in with it: "Hi, I'm playing *Din Raat* by Lifafa." That's how the media popup next to your volume keys knows the song.

We just ask the receptionist:
```python
manager = await Manager.request_async()     # "Hi receptionist"
manager.get_sessions()                      # "Who's playing?" -> [Brave, Spotify...]
await s.try_get_media_properties_async()    # "What song, artist, album, cover?"
```
**Why it's better:** one way to ask works for every app. No API key, no Premium, no login.

> 🧠 **Lazy rule #1:** before building something, check if the computer already does it.

---

## Lesson 2: `async` / `await`, or "order food, don't stare at the kitchen" 🍔

Asking Windows something takes a moment. `await` means: *"Start this, and come back to me with the answer."*
```python
p = await s.try_get_media_properties_async()
```
`asyncio.run(...)` is the waiter who carries the order. In `Api.state()` we hand him the whole job and wait for the tray.

---

## Lesson 3: Why HTML for the look instead of tkinter? 🎨

| | tkinter (Python's built-in UI) | HTML + CSS (what we used) |
|---|---|---|
| A new style later | Rewrite the drawing code | Write a new `.html` file |
| Bevels, gradients, fonts | Painful | A few lines of CSS |
| Things to learn | A niche tool | The same skills websites use |

**pywebview** opens a small window with a mini web browser inside it, and lets JavaScript call Python:
```js
pywebview.api.state()   // JavaScript asks...
```
```python
class Api:
    def state(self, pick=None): ...   # ...and Python answers
```
Think of it as a walkie-talkie between the face (HTML) and the brain (Python).

---

## Lesson 4: The 3D look is just 4 border colours 🪟

Windows 98 buttons look raised because of one trick: **the top and left edges are light, the bottom and right edges are dark.** Your eye reads that as light coming from the top-left.
```css
.raised { border-color: white  black black  white; }   /* top right bottom left */
.sunken { border-color: grey   white white grey;  }   /* flipped = pushed in */
```
When you press a button, we flip the colours (`:active`) and it looks pushed in. No images needed.

The empty CD icon is also pure CSS: a `radial-gradient` of grey rings. That's one less image file to manage.

---

## Lesson 5: YouTube detective work 🕵️

YouTube only tells Windows: title = `"Artist - Song (Official Video)"`, artist = the channel name. The thumbnail is the video frame, not the album cover.

How we figure out it's YouTube: **Spotify always reports an album, YouTube never does.** No album means a video site.

Then:
1. **Clean the title** with *regex*, a tiny pattern language for text:
   ```python
   BRACKETS = re.compile(r"[(\[][^)\]]*[)\]]")   # anything inside () or []
   ```
   `"Daft Punk - One More Time (Official Video)"` becomes `"Daft Punk"` and `"One More Time"`.
2. **Ask iTunes** (free, no key) for that song and take the 600×600 cover and the album name.

`urllib` comes with Python. We didn't install the popular `requests` library for one web call.
> 🧠 **Lazy rule #2:** never add a dependency for a few lines.

---

## Lesson 6: A cache, or "remember, don't re-ask" 📒

The widget checks every second. Calling iTunes 60 times a minute for the same song would be slow and rude.
```python
songs = {}                 # a dictionary: (artist, title) -> cover, album
if key not in songs: ...   # only do the expensive work the first time
```
That's a **cache**: a notebook of answers you've already looked up.

---

## Lesson 7: Extrapolation, or the slider that guesses ⏱️

Apps only report "I'm at 1:32" now and then, not every second. So we do the maths:
```python
pos += now - last_updated_time      # report said 1:32, 5 seconds ago -> we're at 1:37
```
That keeps the slider moving smoothly between reports.

Bonus fact: Windows measures time in **ticks of 100 nanoseconds**, so seeking to 10 seconds means sending `10 × 10,000,000`.

---

## Lesson 8: Small details that prevent bugs 🐛

- **`setTimeout` after finishing, not `setInterval`.** If one iTunes call takes 5 seconds, `setInterval` would start 5 more checks that pile up. Ours waits for the last one to finish.
- **Invisible `<select>` over the ▼ arrow.** We get a real, working dropdown from the browser for free and just hide its ugly look.
- **An `ACTIONS` whitelist.** Python only runs commands we listed (`skip_next`, `stop`…), never whatever text the page sends.
- **`--test` self-check.** Three `assert` lines prove the title cleaner works. If someone breaks it, they'll know in one second.

---

## Lesson 9: Karaoke lyrics, or subtitles for songs 🎤

**Where lyrics come from:** **LRCLIB**, a free lyrics database built by fans. No key and no account.

**The secret format, LRC:** synced lyrics are plain text with a timestamp in front of each line, the same idea as movie subtitles:
```
[00:51.78] Jaadu,
[00:59.07] Tera yeh jalwa
```
A regex pulls the minutes, seconds and text out of each line, and `parse_lrc` turns that into `[[51.78, "Jaadu,"], [59.07, "Tera yeh jalwa"]]`.

**Highlighting the current line** comes down to one question: *"Which is the last line whose time has already passed?"*
```js
lines.findLastIndex(([t]) => t <= pos)
```
The song position we already calculated for the slider (Lesson 7) gets reused here. That's lazy dev joy: **one number powers two features.**

**Picking the right version:** LRCLIB often has several copies of a song (the radio edit, the album version…). We choose the one *with timestamps* whose *length is closest* to what's playing:
```python
min(hits, key=lambda h: (not h["syncedLyrics"], abs(h["duration"] - dur)))
```
`min` with a `key` means "sort by this, give me the winner". It sorts by two rules at once: first "has timestamps?", then "how close is the length?".

**Two safety habits:**
- **`textContent`, never `innerHTML`.** Lyrics come from strangers on the internet. `innerHTML` would treat `<script>` as code to run; `textContent` treats it as harmless text. Always do this with text from outside your app.
- **Throw away late answers.** If you skip a song while lyrics are still loading, the old answer arrives late. We check `if (key !== lyricKey) return;` so the old lyrics never overwrite the new song.

---

## Lesson 10: Styles, or one brain with many faces 🎭

Before this change, the brain (the JavaScript logic) lived inside `cdplayer.html`. A second style would have meant copying all of it, and then fixing every future bug twice.

**Split the brain from the face:**
```
skins/
  widget.js       <- the brain: updates, lyrics, buttons (shared)
  cdplayer.html   <- face #1: just HTML + CSS
  cassette.html   <- face #2: just HTML + CSS
```
The deal between them is a **contract**: every face promises to have elements with the same ids (`artist`, `title`, `cover`, `play`…). The brain only ever says `$("artist").textContent = ...`. It doesn't care whether that's a grey Win98 box or handwriting on a tape label.

**Adding a new style is now just adding one file.** Python lists `skins/*.html` and uses each file's `<title>` as its name in the right-click menu. You don't touch any Python.

**How the cassette moves without extra JavaScript:** the brain sets two general-purpose things on every update:
- `body.playing` (a class): CSS uses it to spin the reels. `animation-play-state: running`
- `--progress` (a CSS variable, 0 to 1): CSS uses it to size the tape. The left reel shrinks and the right reel grows:
  ```css
  .left  .tape { width: calc(22px + 20px * (1 - var(--progress))); }
  .right .tape { width: calc(22px + 20px * var(--progress)); }
  ```
The CD Player simply ignores both. **Hand the CSS facts, and let each style decide what to do with them.**

**A bug we hit, and the lesson in it:** at first, Python switched styles with `window.load_url(...)` *while the page was still waiting for Python's answer*. The page got replaced mid-conversation, the walkie-talkie link broke, and the widget froze. The log said exactly that: `set_style ... is not a function`.

The fix: Python only *checks and saves* the choice and answers `True`. Then the page navigates itself with `location.href = "cassette.html"`. **Finish the conversation before you hang up.**

**Security, again:** `set_style` only accepts names of files that already exist in `skins/`. A page could otherwise send `"../../something"` and make the app load any file on your PC.

---

## Lesson 11: The visualizer, or turning sound into bars 📊 (`audio.py`)

**Step 1: Listen to the speakers.** Windows can give programs a copy of whatever goes to your speakers. This is called **loopback**. The `pyaudiowpatch` library gives us that copy as a stream of numbers between -1 and 1: the speaker cone's position, 48,000 times a second.

**Step 2: Split the sound into pitches with an FFT.** The Fast Fourier Transform is a famous algorithm that answers: *"this wiggly wave, how much of it is low bass, how much is mid, how much is high treble?"* It's like a prism splitting white light into colours. `numpy` does it in one line:
```python
spectrum = np.abs(np.fft.rfft(mono * np.hanning(len(mono))))
```
(`hanning` fades the edges of each chunk, so the cut-off at the edges doesn't show up as fake noise.)

**Step 3: Decibels.** Ears don't hear loudness in a straight line. A sound has to be about 10× stronger to sound twice as loud. So we convert with `20 * log10(level)`, the decibel scale. Without this, quiet parts would show no bars at all and loud parts would be stuck at the top.

**Step 4: The self-test proves it.** We play a *fake* 1000 Hz tone through the maths and check that only the "1.2K" band lights up. No speakers needed.

**Lazy tricks:**
- **A callback, not `read()`.** When nothing plays, Windows sends *no data at all*. Our first test using `stream.read()` waited forever. A callback is "call me when sound arrives", so silence just means no calls, and we show empty bars.
- **Only on demand.** The capture starts when a style first asks for bars and stops 2 seconds after it stops asking. CD Player and Cassette don't have bars, so they never start it. That's why they cost almost nothing (see Lesson 13).
- **Honest labels.** The sliders say **VISUALIZER**, not "Equalizer". A real EQ would change Spotify's sound, and that needs a system audio driver. A widget pretending to be one would be lying.

---

## Lesson 12: Per-app volume 🔈

Windows' **Volume Mixer** keeps a separate volume slider for every app. `pycaw` lets Python move those sliders:
```python
for s in AudioUtilities.GetAllSessions():
    if s.Process.name() == "brave.exe": s.SimpleAudioVolume.SetMasterVolume(0.5, None)
```
Gotchas we found:
- A browser plays sound from several processes, so we move **all** of them together.
- Windows **drops a paused app** from the mixer. That's why the slider greys out when you pause.
- `comtypes.CoInitialize()`: Windows' audio objects (COM) need a short "hello" once per thread before they work.

---

## Lesson 13: Measuring cost, and a bug the measuring found 🔬 (`measure.py`)

**Don't guess performance, measure it.** `measure.py` starts the widget once per style, waits 8 seconds, then samples for 20 seconds using `psutil`.

Results on this PC (20 cores, music playing, lyrics off):

| Style | CPU (whole PC) | CPU (one core) | RAM |
|---|---|---|---|
| CD Player | 0.01% | 0.3% | ~183 MB |
| Cassette | 0.01% | 0.2% | ~186 MB |
| Millennium | 0.13% | 2.6% | ~286 MB |

How to read it:
- **CPU is tiny for all three.** Even Millennium, with maths 30 times a second, uses 1/40 of one core. The cassette reels spin for free because CSS animations run on the **graphics card**, not the CPU.
- **RAM is mostly the mini browser** (WebView2) that draws the window: 6 of the 7 processes. Millennium's extra ~100 MB is numpy plus the audio stream.
- **Measuring RAM honestly:** adding up each process's normal memory number (RSS) gave ~450 MB, because shared memory got counted 7 times. **USS** ("unique set size") counts only what each process uses alone.
- **"% of whole PC" vs "% of one core":** Task Manager divides by all 20 cores, so small numbers round to 0%. Per core is easier to compare.

**The bug:** the first measurement looked *too* good. A quick check from a fresh process froze. The cause: when a song changed in Brave, asking Windows for the cover image **never finished**, and it blocked the whole thread. Even Python's `asyncio` timeout couldn't fire, because a timer needs the thread to be free.

The fix:
1. Read the cover on a **helper thread**, wait 2 seconds, then give up and get the cover from iTunes instead.
2. The stuck helper thread then kept the app from **quitting**: the window closed but Python stayed running invisibly. So after the window closes (settings already saved), we exit immediately with `os._exit(0)`.

> 🧠 **Lazy rule #3:** surprising numbers are a clue. "Too good" is just as suspicious as "too bad".

---

## Lesson 14: Making pixels look like real, worn metal 🔧

No image files at all. Every control is drawn with CSS gradients and shadows.

**1. One light source.** Real objects are lit from one direction. We picked *top-left*, so **every** shadow falls down-right:
```css
--drop: 1px 2px 3px rgba(0,0,0,.45);   /* raised things cast a shadow down-right */
--well: inset 1px 2px 4px rgba(0,0,0,.45), 0 1px rgba(255,255,255,.8);  /* holes: shadow inside, light lip below */
```
If one button's shadow went the other way, your eye would instantly say "fake".

**2. Brushed metal = a cone of stripes.** `conic-gradient` sweeps colours around a centre point, like a clock hand. Alternating light and dark grey around the circle looks exactly like a spun aluminium knob. Add a white `radial-gradient` "hot spot" for the shine.

**3. Engraved text = dark text + a 1px white line under it.** `text-shadow: 0 1px white`. Your brain reads it as cut *into* the metal.

**4. Wear and tear is one layer on top of everything** (`.app::after`):
- **Grain:** an SVG `feTurbulence` filter, a random-noise generator built into every browser.
- **Scratches:** a few thin SVG lines, each with a white twin 2px away, so they catch the light like real scratches.
- **Age:** a faint yellow tint plus grime (a dark inner shadow) along the edges where hands touch it.
- `pointer-events: none` means clicks pass straight through the layer to the buttons underneath.

**5. Depth of field** is what cameras do: the subject is sharp, and things nearer or farther are blurry. We fake it with `backdrop-filter: blur()` on thin bands at the top and bottom, faded in with a `mask`. **Lesson learned:** the first version blurred the THEME button so much you couldn't read it. Effects must never cost usability, so we toned it down.

**6. The knob is a fake, and that's the point.** The real `<input type=range>` is hidden. The knob just *moves the input* and fires the same `input` event, so `widget.js` doesn't know or care that a knob exists. A `sync` event goes the other way when the real volume changes. The same contract idea as Lesson 10.

**What it cost** (measured again with `measure.py`): CPU unchanged at about 2.4% of one core, RAM +30 MB (blur needs extra image buffers in the graphics card's memory). Mostly free, because blur and gradients are drawn by the **GPU**.

---

## Lesson 15: Smooth motion, and a memory leak hunt 🎢

**Smooth = in-between frames.** Python sends the song position once a second and the sound bars 30 times a second. Your screen redraws about 60 times a second. If we just jump to each new number, it looks jerky. So every frame (`requestAnimationFrame`, "call me before the next screen refresh"), we:
- **Count the time forward ourselves** between Python's reports. The seek bar glides instead of hopping once a second.
- **Ease the bars:** move a fraction of the way to the target each frame. A big fraction on the way **up** (punchy), a small one on the way **down** (graceful). The `ease()` helper keeps the speed the same on a 60 Hz or 144 Hz screen.
- **Peak caps** hold the highest point, then drift down slowly, like on classic hi-fi meters.

**Rolling time digits:** each digit is a tall strip `0 1 2 … 9` behind a one-digit-high window (`overflow: hidden`). To show "7", slide the strip up by 7 rows. A CSS `transition` with a springy `cubic-bezier` curve makes it roll.

**The leak hunt (the real lesson):** after adding 60-fps animation, Millennium's memory grew **~20 MB every second**. We found the cause by **bisecting**: switching off one suspect at a time and re-measuring.

| Test | Result |
|---|---|
| No visualizer | flat ✅ → it's the visualizer |
| Only the Python calls, nothing drawn | flat ✅ → not the calls |
| Without blur / scratches / glow / cover / fading | still leaking ❌ |
| All values on one element instead of 22 | *worse* ❌ |

Conclusion: changing the **style** of many elements 60 times a second, in a page this detailed, made Edge pile up memory faster than it cleaned it up. The fix visualizers have always used: a **`<canvas>`**. It's one picture we redraw ourselves each frame, with no element styles changing at all. Result: memory stays flat-ish.

**A layering bug along the way:** the canvas fills were invisible. They *were* drawn, but the grooves were drawn on top of them. Elements with `position` set are drawn in page order, so later ones cover earlier ones. `z-index: 1` lifts the canvas above.

> 🧠 **Lazy rule #4:** when four "obvious" fixes fail, stop guessing and test the pieces one at a time.

---

## Lesson 16: The Album theme 🎨

**Python picks the colour** (`dominant_color` in `app.py`):
1. Shrink the cover to 48×48 (we don't need detail).
2. **Quantize** it to 8 colours, like a paint-by-numbers kit.
3. Score each colour as **how much of the picture it covers × how vivid it is**. A small bright red beats a big dull grey, and near-black never wins.

The self-test proves it: a grey picture with a red stripe must come out red.

**CSS mixes the palette** from that one colour with `color-mix()`:
```css
--lcd1: color-mix(in srgb, var(--album) 22%, #05070c);   /* dark version for the screen */
--glow: color-mix(in srgb, var(--album) 45%, white);     /* light version for text */
```
One colour in, a whole matching theme out. A canvas can't read CSS variables, so we read the *real* colour from a hidden element's computed style.

---

## Lesson 17: Real proportions, depth, and a twitchy seek bar 📼

**Real ratio for free:** a Compact Cassette is 100.4 × 63.8 mm. CSS can keep that shape at any width:
```css
.cassette { aspect-ratio: 100.4 / 63.8; }
```
Everything inside uses **percentages** (label = 68% of the height, head = 62% of the width), so the parts keep their real proportions too.

**Depth = layers of shadow, all from one light source above:**
1. The **bay** is a hole: `inset` shadow along its *top* inside edge.
2. The **cassette** sits in it: a soft shadow cast *down* onto the bay floor, plus a thin light line on its top edge (a bevel).
3. The **label** is paper glued on: a tiny shadow under it.
4. The **window** is see-through plastic set *into* the label: inset shadow again.

Every step down gets an inset shadow, every step up gets a drop shadow. That's the whole trick.

**The trapezoid** at the bottom is one `clip-path: polygon(...)`, which cuts any box into a shape. The drive holes are `radial-gradient` circles.

**Album colours everywhere:** the cassette body, label stripes and seek knob are all `color-mix(...)` of `--album`, like Millennium's Album theme.

**The twitchy seek bar:** every second, Python sends a fresh *estimate* of the position. Each estimate was off by a fraction of a second, so the bar jumped a little every second. The fix is to **trust our own clock** (`performance.now()` is very precise) and only jump to Python's number when it's *way* off (more than 1.5 s), which means a real seek, a new song, or play/pause.

> 🧠 Two clocks that both tick correctly but disagree a little: pick one and only sync on big differences.

---

## Lesson 18: Silverdeck, a busy faceplate 🎛️

**Mapping buttons to features is a design job, not a coding one.** The reference had more buttons than we had features, so we decided each one *before* writing code:

| Button | Feature |
|---|---|
| Cross pad | stop / play / previous / next, play-pause in the centre |
| Big knob | app volume (same `#vknob` code as Millennium) |
| TREBLE / BASS | **meters**: they turn by themselves with the music. They can't change the sound, so they don't pretend to |
| LY / VIS / TOP + lights | lyrics, visualizer on/off, always-on-top |
| CFG | the style menu · OPEN = pick source · ◀ ▶ = previous/next source |
| THEME tab / MINI | colour themes / compact |

**Don't copy, move:** Millennium and Silverdeck both needed the rolling digits and the volume knob. Instead of pasting the code twice, it moved into `widget.js`. A style now just writes `<span id="time" data-roll>` or adds an element with `id="vknob"`.

**Visualizer off really means off:** `setViz(false)` stops asking Python for sound bands. Python's capture notices nobody is asking and stops itself after 2 seconds (Lesson 11). That's a real CPU saving, not just hidden bars.

**LCD tricks:**
- **Dot-matrix texture:** a tiny `radial-gradient` dot repeated every 3px.
- **Ghost segments:** unlit bar segments are drawn at 7% opacity, like a real LCD where you can faintly see the "off" parts.
- **Current lyric line = a "lit" row:** dark background, screen-coloured text, the inverse of everything else.
- **Curved screen:** `border-radius` takes two sets of values (`64px 64px 20px 20px / 34px 34px 16px 16px`): horizontal and vertical radii. Different values give elliptical corners, the curved top of the screen.

**Fewer style updates:** the TREBLE/BASS knobs are two normal elements, so they only get a new angle when it changed by more than 1%. That's our lesson from the memory leak (Lesson 15).

---

## Lesson 19: "It keeps crashing", or who owns the process? 🕵️

**What the evidence said:** Windows' event log had only **one** entry: "python.exe stopped interacting with Windows and was closed" (a *freeze*, not a crash) at a moment when our memory tests were force-closing the widget's browser parts.

**The real cause of the disappearing widget:** every time, it had been started *from inside Claude's tool shell*. A program started from a shell is that shell's **child**: when the shell ends, its children go with it. Those "exit code 127" notices were the shell ending and taking the widget along.

**The fix (and your startup request) is the same thing:** a shortcut in Windows' **Startup** folder (`shell:startup`) runs the widget at login, owned by Windows itself and nobody else.
- It uses **`pythonw.exe`**: the same Python, but with no black console window.
- With no console, errors would vanish silently. So the app now writes them to **`widget.log`**: `sys.stderr` goes to the file, and `faulthandler` writes a stack trace even if Python itself dies.

> 🧠 Before fixing a "crash", find out what's actually ending the process.

**To stop it starting with Windows:** delete `Now Playing Widget` from the folder that `Win+R → shell:startup` opens.

---

## Lesson 20: Pixel font, raining pixels, and a tilted screen 👾

**A font with no font file:** each digit is 7 rows of 5 bits, `1` = pixel on:
```
"0": 01110 10001 10011 10101 11001 10001 01110
```
`widget.js` builds a 5×7 grid of tiny squares for each character and switches on the ones that are `1`. The off pixels stay faintly visible ("ghost" pixels), like a real LCD.

**The new animation:** each pixel knows its row (`--r`). Its transition starts `row × 28 ms` late, so when a digit changes, the new pixels **rain in from top to bottom**. A slightly springy `cubic-bezier` makes each one pop as it lands. Only changed pixels animate, because only their class changes.

**Perspective:** `transform: perspective(520px) rotateX(9deg)` tips the screen backwards around its bottom edge. `perspective` is how far your eye is from it: smaller means a stronger effect.

**Lyrics + visuals together:** when lyrics are on, the visualizer box shrinks to a strip on top. The canvas notices its new height and re-sizes itself (`c.height !== H × devicePixelRatio`).

**Its own theme:** Silverdeck now saves `theme-silverdeck`, so picking Amber here doesn't change Millennium's theme.

---

## Lesson 21: The mini bubble, or two windows, one app 🫧

**Two windows:** at start, Python creates the widget *and* a tiny second window (`bubble.html`) that's hidden. Pressing `_` hides the widget and shows the bubble. Clicking the bubble does the opposite. Both windows share the same `Api`, so the bubble gets song data the same way the widget does.

**Things that didn't work (and what we learned):**
- **A round window:** pywebview's `transparent=True` doesn't work on Windows (the corners stay grey). Telling Windows the window's shape (`SetWindowRgn`, or WinForms' `Region`) didn't stick either. So it's a **rounded tile**: Windows 11 rounds window corners by itself, and a cover filling the tile looks like an app icon.
- **Tiny windows:** Windows forced the window to at least ~150×50 px. Lowering WinForms' `MinimumSize` lets it be 64×64.

**Click vs. drag:** both start with the mouse button going down. We wait: if the mouse moves more than 4 px before you let go, it's a drag; otherwise it's a click.

**Two bugs our test found:**
1. **The play button sat in the middle**, so "click to restore" actually paused the music. Now it's a small button in the corner, and the rest of the tile restores.
2. **The snap fired too early.** Every mouse movement sent a separate "move" message to Python, and each runs on its own thread, so a late one could arrive *after* the snap. Fix: send **one move at a time, always the newest position**, and snap only once the last move has landed.

**Snapping:** Python asks Windows for the **work area** of the monitor the bubble is on (the screen minus the taskbar), picks the nearer left or right edge, and glides there in 8 small steps that slow down at the end (`1 - (1 - t)³`, an "ease-out" curve).

**Saving effort while hidden:** the hidden widget sets `hiddenNow = true`. It stops drawing and stops asking for visualizer data, so the sound capture switches itself off too.

---

## Lesson 22: Pin to desktop, and a deadlock caught red-handed 🔒

**Pinning:** Windows keeps windows in a stack, front to back. "Always on top" windows live in their own layer at the front. Pinning:
1. switches "always on top" off, then
2. pushes the widget to the **bottom** of the stack (`HWND_BOTTOM`), right above the wallpaper.

A click brings any window to the front, so a small loop pushes it back down 4 times a second.

**The freeze:** the first test froze the widget: no updates, 0% CPU. **`py-spy dump`** takes a snapshot of what every Python thread is doing, and it showed:
- Thread A (our `pin()` call): "switch off on-top", using **pywebview's `on_top`**, which **holds Python's lock** (the GIL) while waiting for the window's thread.
- The window's thread: handling the page's next "what's playing?" call, waiting for a new thread to start. That new thread **needs the GIL**, and A has it.

A waits for the window, the window waits for the new thread, the new thread waits for A. That's a circle, so nobody moves: a **deadlock**.

**The fix:** don't use pywebview's `on_top`, `show()` or `hide()` from our API at all. Plain `ctypes` calls to Windows (`SetWindowPos`, `ShowWindow`) **let go of the GIL** while Windows does the work, so the circle can't form. This bug could also have been behind some of the earlier "crashes".

**Two more surprises, found by testing:**
- pywebview's `resize()` quietly includes "show the window", so the hidden bubble popped up at startup. We hide it again right after sizing.
- pywebview never shrinks a window below its `min_size` (200×100 by default), so the bubble came out 200×100. Fix: `min_size=(64, 64)` when creating it.

> 🧠 When something freezes, don't guess: snapshot the threads and read who's waiting for whom.

**Known limit (you chose this):** Win+D / "show desktop" hides the pinned widget, and desktop icons can end up underneath it.

---

## Lesson 23: Button sounds with no sound files 🔊

**Synthesis instead of recordings:** the browser has a tiny synthesizer built in (Web Audio). Every sound is built from two ingredients:
- **A noise burst through a filter.** White noise (random numbers) is a hiss. Keep only one pitch band (`bandpass`) and fade it out in 25 ms, and it becomes a **click**. A narrow band with high `Q` "rings" like metal; a low, wide one sounds dull like a plastic mechanism.
- **A short falling tone.** A sine wave sliding from 200 Hz to 120 Hz in 60 ms is a soft **thump**, the "body" of a button press.

| Control | Sound |
|---|---|
| play / stop / skip | thump + click (on Cassette: plus a second "latch" click 35 ms later, like a piano key locking) |
| on/off switches | tick + a tiny tone, **higher for on, lower for off** |
| menu items | a soft blip |
| volume knob | a barely-there tick every 5%, like detents |
| everything else | one click |

Each style sets `STYLE.material`: plastic (bright), mech (dull), or metal (ringing).

**Measuring "lowkey":** we recorded the speakers (the same loopback as the visualizer) while clicking:
- With sounds **off**: silence. That proves what we heard was really our sounds.
- With one master volume knob (`SFX_VOLUME = 0.12`), the clicks peak at about **2–4% of full scale**. Music usually peaks near 70–100%, so the clicks sit far below it.
- A 50 ms **fade-in** when the synthesizer starts, so the sound device waking up can't "pop".

**Browsers only allow sound after a click.** So the synthesizer starts on your first click, and that first sound arrives about a second late while Windows wakes the audio device. After that, sounds are instant.

**Off switch:** right-click → **Button sounds**.

---

## Lesson 24: Packaging, or making it run on a PC without Python 📦

**PyInstaller** collects your script, the Python interpreter and every library it imports into one folder with an `.exe`. Your friend runs the `.exe`; Python comes along inside `_internal/`.

Things we had to tell it:
- **Data files aren't code**, so PyInstaller doesn't see them: `--add-data "skins;skins"` (plus `bubble.html`, `icon.ico`).
- **Libraries loaded in unusual ways** (pywebview's .NET parts, winrt's many sub-packages, the audio DLLs) need `--collect-all`, otherwise they're missing at runtime.
- `--windowed`: no black console window.

**Where files live, two kinds:**
- *The app's own files* (skins, icon) are inside the package. Code finds them with `sys._MEIPASS` when frozen.
- *Your files* (settings, log) go to **`%APPDATA%\Now Playing Widget`**. A program folder may be read-only, and an update would wipe your settings. The first run copies your old `settings.json` across.

**The app manages its own startup:** right-click → *Start with Windows* creates or deletes a shortcut in the Startup folder. The shortcut points to the `.exe` (or to `pythonw app.py` when running from source). The paths reach PowerShell as **environment variables**, not pasted into the command, so a folder name with a space or quote can't break it.

**Build-script gotchas we hit:**
- With a separate build folder (`--specpath`), PyInstaller reads *relative* paths from that folder, so `skins` wasn't found. Fix: `%~dp0`, the folder the script is in.
- `.bat` files should have Windows line endings (CRLF), especially with `^` line continuations.

**The real test** is a clean one: unzip into an empty folder and run it from there. It worked, including the visualizer and volume (the trickiest libraries to package).

**Also fixed this round:**
- **Pinned flicker:** the widget was pushed to `HWND_BOTTOM` 4× a second, *under* the desktop and back. Now it only moves when an app window is below it, and only to just above the desktop.
- **"-1:-1" on live streams:** the time is clamped at 0:00.

---

## What we skipped on purpose (and why)

| Skipped | Why |
|---|---|
| Hiding to the system tray | Needs an extra library; minimize does the job for now |
| Kbps / kHz / playlist / library | Windows doesn't share them; showing made-up numbers would be fake |
| Menu bar (File / Play / Options…) | Menus that do nothing are worse than no menus; right-click has the style menu |
| A match check on iTunes results | We trust the top hit for now; marked `shortcut:` in the code |
