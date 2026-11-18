// The shared brain of every style. A style is one HTML file that:
//  - has elements with ids: artist, title, album, cover, cd, seek, play, lyrBtn, lyrics, and <select class="pick">
//  - defines STYLE = { full:[w,h], compact:[w,h], lyrics:extraHeight, empty:"text when nothing plays" } before loading this file
// The body gets class "playing" while music plays, and CSS variable --progress (0..1), for animations.
// Optional extras a style can include: #time (m:ss; add data-roll for rolling digits or data-pixel for a 5x7 pixel font),
// #volume (range 0..1, fires "sync" when the real volume is read) + #vknob (a draggable knob for it),
// setViz(true/false) to switch the visualizer, and window.drawViz(levels, peaks):
// called every frame with 11 numbers each (10 bands bass→treble, then the average), all 0..1. Draw them on a canvas.
// The body also gets CSS variables --cover (url of the cover) and --album (the cover's main colour).
const $ = id => document.getElementById(id);
const NAMES = { "308046B0AF4A39CB": "Firefox", "MSEdge": "Edge" };  // Windows' app ids -> nice names
const nice = id => NAMES[id] || id.replace(/\.exe$/i, "");
const has = cls => document.body.classList.contains(cls);
let pick = null, seeking = false;

function send(action, seconds = 0) { pywebview.api.control(pick, action, seconds).then(tick); }

function setLayout() {
  const [w, h] = has("compact") ? STYLE.compact : STYLE.full;
  pywebview.api.resize(w, h + (has("lyrics-on") && !has("compact") ? STYLE.lyrics : 0));
}

function toggleCompact() { document.body.classList.toggle("compact"); setLayout(); }

function toggleLyrics() {
  $("lyrBtn").classList.toggle("on", document.body.classList.toggle("lyrics-on"));
  lyricKey = null;  // re-open = fresh try (also how you retry after a network error)
  setLayout();
  tick();
}

// ---- lyrics ----
let lyricKey = null, lines = [], synced = false, nowIdx = -1;

function showLines(texts, cls = "") {
  // textContent, never innerHTML: lyrics come from the internet, so they must never run as code
  $("lyrics").replaceChildren(...texts.map(t => Object.assign(document.createElement("p"), { textContent: t, className: cls })));
}

async function loadLyrics(s) {
  const key = s.artist + "\n" + s.title;
  if (key === lyricKey) return;
  lyricKey = key; nowIdx = -1; lines = [];
  showLines(["Searching for lyrics…"], "empty");
  const l = await pywebview.api.lyrics(s.artist, s.title, s.dur || 0);
  if (key !== lyricKey) return;  // the song changed while we were searching: throw this answer away
  lines = l.lines; synced = l.synced;
  $("lyrics").classList.toggle("synced", synced);
  if (lines.length) showLines(lines.map(([, t]) => t || "♪"));
  else showLines([l.error ? "Can't reach the lyrics server. Click ● twice to retry." : "No lyrics found"], "empty");
  $("lyrics").scrollTop = 0;
}

function highlight(pos) {
  if (!synced) return;
  const i = lines.findLastIndex(([t]) => t <= pos);  // the last line whose time has already come
  if (i === nowIdx) return;
  const box = $("lyrics"), p = box.children;
  p[nowIdx]?.classList.remove("now");
  nowIdx = i;
  if (i < 0) return;
  p[i].classList.add("now");
  box.scrollTo({ top: p[i].offsetTop - box.clientHeight / 2 + p[i].offsetHeight / 2, behavior: "smooth" });
}

// ---- the 1-second update ----
function fillPickers(sources, current) {
  for (const sel of document.querySelectorAll(".pick")) {
    if (sel.dataset.list !== sources.join()) {  // only rebuild when the list changes, or the open menu flickers
      sel.replaceChildren(...sources.map(s => new Option(nice(s), s)));
      sel.dataset.list = sources.join();
    }
    sel.value = current;
  }
}

async function tick() {
  const s = await pywebview.api.state(pick);
  hiddenNow = !!s.hidden;  // folded into the mini bubble: pause the visualizer and animations
  fillPickers(s.sources, s.id);
  $("artist").textContent = s.id ? s.artist || "Unknown artist" : STYLE.empty;
  $("title").textContent = s.title || "";
  $("album").textContent = s.album || "";
  $("album").title = s.album || "";
  $("play").textContent = s.playing ? "❚❚" : "▶";
  document.body.classList.toggle("playing", !!s.playing);
  // Keep counting the position ourselves; only jump to Python's number when it really disagrees.
  // (Its estimate wobbles by a fraction of a second each report: following it made the bar twitch every second.)
  const now = performance.now(), mine = clock.pos + (clock.playing ? (now - clock.at) / 1000 : 0);
  if (s.id !== clock.id || !!s.playing !== clock.playing || Math.abs((s.pos || 0) - mine) > 1.5)
    clock = { pos: s.pos || 0, dur: s.dur || 0, playing: !!s.playing, id: s.id, at: now };  // seek, new song, play/pause
  clock.dur = s.dur || 0;

  const img = $("cover");
  if (img.getAttribute("src") !== (s.cover || null)) {  // only swap the picture when the song changes
    if (s.cover) img.src = s.cover; else img.removeAttribute("src");
    document.body.style.setProperty("--cover", s.cover ? `url("${s.cover}")` : "none");  // for CSS backgrounds
    document.body.style.setProperty("--album", s.color || "#3a6fd8");  // the cover's main colour
  }
  img.hidden = !s.cover;
  $("cd").hidden = !!s.cover;

  $("seek").disabled = !s.dur;  // some sites don't report song length: then the slider can't work
  $("seek").max = s.dur || 1;

  if (has("lyrics-on") && s.id) {
    loadLyrics(s);  // no await: a slow search shouldn't freeze the player
    highlight(s.pos);
  }

  if ($("volume") && !volDrag) {
    const v = s.id ? await pywebview.api.volume(s.id) : null;
    $("volume").disabled = v === null;  // Windows hides paused apps from the Volume Mixer
    if (v !== null) $("volume").value = v;
    $("volume").dispatchEvent(new Event("sync"));  // lets a style redraw its own volume control (e.g. a knob)
  }
  currentId = s.id;
}

// ---- optional: per-app volume ----
let volDrag = false, currentId = null;
if ($("volume")) {
  $("volume").oninput = () => { volDrag = true; pywebview.api.volume(currentId, +$("volume").value); };
  $("volume").onchange = () => volDrag = false;
}

// ---- optional: rolling time digits (<span id="time" data-roll>) ----
// Each digit is a strip "0 1 2 ... 9" in a one-digit-tall window (.dg); we slide the strip (.strip). Style them in CSS.
function rollTime(text) {
  const box = $("time"), shape = text.replace(/\d/g, "0");
  if (box.dataset.shape !== shape) {  // "9:59" -> "10:00" adds a digit: rebuild the strips
    box.dataset.shape = shape;
    box.replaceChildren(...[...text].map(ch => {
      if (!/\d/.test(ch)) return Object.assign(document.createElement("span"), { className: "colon", textContent: ch });
      const strip = Object.assign(document.createElement("span"), { className: "strip" });
      strip.append(...[..."0123456789"].map(d => Object.assign(document.createElement("span"), { textContent: d })));
      const win = Object.assign(document.createElement("span"), { className: "dg" });
      win.append(strip);
      return win;
    }));
  }
  const strips = box.querySelectorAll(".strip");
  [...text.replace(/\D/g, "")].forEach((d, i) => strips[i].style.transform = `translateY(${-d}em)`);
}

// ---- optional: pixel-font time (<span id="time" data-pixel>) ----
// Each character is a 5x7 grid of <i> "pixels". A digit is 7 rows of 5 bits: 1 = lit.
// CSS styles .pg (a character) and i / i.on (a pixel); each pixel has --r (its row) for staggered animation.
const FONT = {
  0: "01110 10001 10011 10101 11001 10001 01110", 1: "00100 01100 00100 00100 00100 00100 01110",
  2: "01110 10001 00001 00010 00100 01000 11111", 3: "11111 00010 00100 00010 00001 10001 01110",
  4: "00010 00110 01010 10010 11111 00010 00010", 5: "11111 10000 11110 00001 00001 10001 01110",
  6: "00110 01000 10000 11110 10001 10001 01110", 7: "11111 00001 00010 00100 01000 01000 01000",
  8: "01110 10001 10001 01110 10001 10001 01110", 9: "01110 10001 10001 01111 00001 00010 01100",
  ":": "0 0 1 0 1 0 0", "-": "00000 00000 00000 11111 00000 00000 00000",
};
function pixelTime(text) {
  const box = $("time");
  if (box.dataset.shape !== text.replace(/\d/g, "0")) {  // a different shape ("9:59" -> "10:00"): rebuild the grids
    box.dataset.shape = text.replace(/\d/g, "0");
    box.replaceChildren(...[...text].map(ch => {
      const rows = FONT[ch].split(" "), g = Object.assign(document.createElement("span"), { className: "pg" });
      g.style.gridTemplateColumns = `repeat(${rows[0].length}, auto)`;
      rows.forEach((row, r) => [...row].forEach(() => {
        const px = document.createElement("i");
        px.style.setProperty("--r", r);
        g.append(px);
      }));
      return g;
    }));
  }
  [...text].forEach((ch, k) => {  // only flip the pixels that changed, so only those animate
    const bits = FONT[ch].replace(/ /g, ""), px = box.children[k].children;
    for (let i = 0; i < bits.length; i++) px[i].classList.toggle("on", bits[i] === "1");
  });
}

// ---- button sounds: made on the spot by the browser's synthesizer (Web Audio). No sound files. ----
// Every sound is a tiny burst of noise or a short tone, < 0.1 s, at most ~8% volume: felt more than heard.
// A style picks its material with STYLE.material: "plastic" (CD Player), "mech" (Cassette), "metal" (default).
let audioCtx = null, sfxOn = true, noise = null, master = null;
const SFX_VOLUME = 0.3;  // one knob for all button sounds: clicks peak ~5-10% of full scale, still well under music
const MATERIAL = {  // pitch of the click (Hz) and how much it rings: plastic is bright, metal pings, mech is dull
  plastic: { click: 3400, ring: 1.2, thump: 150 },
  metal:   { click: 5200, ring: 7,   thump: 120 },
  mech:    { click: 1800, ring: 2,   thump: 90 },
};
function burst(a, at, { freq, q = 1, dur = 0.025, vol = 0.06 }) {  // filtered noise: a click
  const src = a.createBufferSource(), f = a.createBiquadFilter(), g = a.createGain();
  src.buffer = noise;
  f.type = "bandpass"; f.frequency.value = freq; f.Q.value = q;
  g.gain.setValueAtTime(vol, at); g.gain.exponentialRampToValueAtTime(0.0001, at + dur);  // fast fade = "tick", not "hiss"
  src.connect(f).connect(g).connect(master);
  src.start(at); src.stop(at + dur);
}
function tone(a, at, { from, to = from, dur = 0.04, vol = 0.05, type = "sine" }) {  // short tone: a thump or a blip
  const o = a.createOscillator(), g = a.createGain();
  o.type = type;
  o.frequency.setValueAtTime(from, at); o.frequency.exponentialRampToValueAtTime(to, at + dur);
  g.gain.setValueAtTime(vol, at); g.gain.exponentialRampToValueAtTime(0.0001, at + dur);
  o.connect(g).connect(master);
  o.start(at); o.stop(at + dur);
}
function sfx(kind) {
  if (!sfxOn) return;
  if (!audioCtx) {  // browsers only allow sound after the first click, so we create the synthesizer then
    audioCtx = new AudioContext();
    master = audioCtx.createGain();  // fades in over 50 ms, so the sound device waking up can't "pop"
    master.gain.setValueAtTime(0, audioCtx.currentTime);
    master.gain.linearRampToValueAtTime(SFX_VOLUME, audioCtx.currentTime + 0.05);
    master.connect(audioCtx.destination);
    noise = audioCtx.createBuffer(1, audioCtx.sampleRate * 0.1, audioCtx.sampleRate);
    noise.getChannelData(0).forEach((_, i, d) => d[i] = Math.random() * 2 - 1);
  }
  const a = audioCtx, t = a.currentTime, m = MATERIAL[STYLE.material] || MATERIAL.metal;
  if (kind === "press") {          // play / stop / skip: a soft body thump + the click of the switch
    tone(a, t, { from: m.thump * 1.6, to: m.thump, dur: 0.06, vol: 0.08 });
    burst(a, t, { freq: m.click, q: m.ring, vol: 0.05 });
    if (STYLE.material === "mech") burst(a, t + 0.035, { freq: m.click * 1.4, q: 3, vol: 0.035 });  // cassette key latching
  } else if (kind === "on" || kind === "off") {  // switches: two quick ticks, going up for on, down for off
    burst(a, t, { freq: m.click, q: m.ring, vol: 0.035, dur: 0.015 });
    tone(a, t + 0.03, { from: kind === "on" ? 1400 : 900, dur: 0.03, vol: 0.025 });
  } else if (kind === "menu") {    // menu item: a tiny soft blip
    tone(a, t, { from: 1100, to: 900, dur: 0.03, vol: 0.02 });
  } else if (kind === "tick") {    // knob detent: barely there
    burst(a, t, { freq: m.click * 1.3, q: m.ring + 2, vol: 0.025, dur: 0.008 });
  } else {                         // "click": any other button
    burst(a, t, { freq: m.click, q: m.ring, vol: 0.045 });
  }
}
// which sound a control makes, decided from what the control does
document.addEventListener("pointerdown", e => {
  if (e.button !== 0) return;
  const el = e.target.closest("button, .item, .tab, .switch, .pick, .seek, [onclick]");
  if (!el || el.id === "vknob") return;  // the knob ticks by itself while turning (below)
  const does = (el.getAttribute("onclick") || "") + " " + el.id + " " + el.className;
  if (el.classList.contains("item")) sfx("menu");
  else if (/toggle(Lyrics|Vis|Top|Compact)|lyrBtn|switch|nextTheme|tab/.test(does)) {
    // is the thing ON right now (so this click turns it off)? read the real state from the page
    const isOn = /Lyrics|lyrBtn|switch/.test(does) ? has("lyrics-on") : /Vis/.test(does) ? has("viz-on")
               : /Top/.test(does) ? has("ontop") : /Compact/.test(does) ? has("compact") : false;
    sfx(isOn ? "off" : "on");
  }
  else if (/send\(/.test(does)) sfx("press");
  else sfx("click");
}, true);

// ---- optional: volume knob (#vknob): drag up/down or scroll. It only moves the hidden #volume input ----
if ($("vknob")) {
  const vol = $("volume"), knob = $("vknob");
  const showVol = () => { knob.style.setProperty("--vol", vol.value); knob.classList.toggle("off", vol.disabled); };
  const setVol = v => {
    if (vol.disabled) return;
    v = Math.min(1, Math.max(0, v));
    if (Math.round(v * 20) !== Math.round(+vol.value * 20)) sfx("tick");  // a faint detent every 5%
    vol.value = v;
    vol.dispatchEvent(new Event("input"));
    showVol();
  };
  vol.addEventListener("sync", showVol);
  knob.onpointerdown = e => {
    knob.setPointerCapture(e.pointerId);  // keep getting moves even if the mouse leaves the knob
    const startY = e.clientY, start = +vol.value;
    knob.onpointermove = m => setVol(start + (startY - m.clientY) / 120);  // 120 px of drag = 0 → 100%
  };
  knob.onpointerup = () => { knob.onpointermove = null; vol.dispatchEvent(new Event("change")); };
  knob.onwheel = e => { setVol(+vol.value - Math.sign(e.deltaY) * 0.05); vol.dispatchEvent(new Event("change")); };
}

// ---- optional: visualizer data, about 30 times a second ----
let target = Array(11).fill(0);  // 10 bands + the average, as Python last measured them
let vizOn = true;  // a style can switch it off with setViz(false); Python then stops listening after 2 s
let hiddenNow = false;  // true while the widget is folded into the mini bubble (from Python's state())
const setViz = on => { vizOn = on; if (!on) target = Array(11).fill(0); };
async function vizLoop() {
  const active = vizOn && !hiddenNow;  // nobody can see the bars: stop asking, so the sound capture stops too
  const b = active ? await pywebview.api.bands().catch(() => null) : null;
  if (b && active) target = [...b, b.reduce((x, y) => x + y) / b.length];
  setTimeout(vizLoop, active ? 33 : 300);
}

// ---- every screen refresh: glide everything smoothly ----
// Data arrives in steps (bands 30x/s, position 1x/s); the screen redraws ~60x/s.
// So each frame we move a little towards the latest data instead of jumping to it.
let clock = { pos: 0, dur: 0, playing: false, id: null, at: 0 };
const shown = Array(11).fill(0), peak = Array(11).fill(0);
let lastFrame = performance.now(), lastTime = "";
const ease = (k, dt) => 1 - Math.pow(1 - k, dt / 16.7);  // same speed on a 60 Hz or 144 Hz screen
const fmt = t => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;

function frame(now) {
  const dt = Math.min(now - lastFrame, 100);
  lastFrame = now;
  if (hiddenNow) return setTimeout(() => requestAnimationFrame(frame), 250);  // hidden: no drawing, check back 4x/s

  if (window.drawViz) {
    for (let i = 0; i < 11; i++) {
      // rise fast (punchy), fall slowly (graceful); peaks hang a moment then drift down
      shown[i] += (target[i] - shown[i]) * ease(target[i] > shown[i] ? 0.35 : 0.07, dt);
      peak[i] = Math.max(shown[i], peak[i] - 0.0006 * dt);
    }
    // the style draws on a <canvas>: changing element styles 60x/s made Edge's memory grow ~20 MB/s (measured)
    drawViz(shown, peak);
  }

  // the song position, counted forward between Python's once-a-second reports
  // never below 0:00 (live streams can report a slightly negative position, which showed as "-1:-1")
  const pos = Math.max(0, Math.min(clock.pos + (clock.playing ? (now - clock.at) / 1000 : 0), clock.dur || Infinity));
  if (!seeking) $("seek").value = pos;
  document.body.style.setProperty("--progress", clock.dur ? (pos / clock.dur).toFixed(4) : 0);
  const t = clock.id ? fmt(pos) : "-:--";
  if ($("time") && t !== lastTime) {
    lastTime = t;
    const d = $("time").dataset;
    "pixel" in d ? pixelTime(t) : "roll" in d ? rollTime(t) : $("time").textContent = t;
  }
  requestAnimationFrame(frame);
}

async function loop() {
  try { await tick(); } catch (e) { console.error(e); }
  setTimeout(loop, 1000);  // wait for the last check to finish before the next one (a slow lookup won't pile up)
}

// ---- right-click: pick a style ----
const closeMenu = () => document.querySelector(".menu")?.remove();

document.addEventListener("contextmenu", async e => {
  e.preventDefault();
  closeMenu();
  const menu = Object.assign(document.createElement("div"), { className: "menu" });
  for (const [file, name, current] of await pywebview.api.styles()) {
    const item = Object.assign(document.createElement("div"), { className: "item", textContent: (current ? "✓ " : "   ") + name });
    item.onclick = async () => { if (await pywebview.api.set_style(file)) location.href = file + ".html"; };
    menu.append(item);
  }
  // below the styles: pin the widget to the desktop (behind all windows) or let it float again
  const pinned = await pywebview.api.pin();
  const pin = Object.assign(document.createElement("div"), { className: "item", textContent: (pinned ? "✓ " : "   ") + "Pin to desktop" });
  pin.style.borderTop = "1px solid rgba(128,128,128,.4)";
  pin.onclick = () => pywebview.api.pin(!pinned);
  menu.append(pin);
  const snd = Object.assign(document.createElement("div"), { className: "item", textContent: (sfxOn ? "✓ " : "   ") + "Button sounds" });
  snd.onclick = () => { sfxOn = !sfxOn; pywebview.api.pref("sounds", sfxOn ? "on" : "off"); };
  menu.append(snd);
  const auto = await pywebview.api.autostart();
  const start = Object.assign(document.createElement("div"), { className: "item", textContent: (auto ? "✓ " : "   ") + "Start with Windows" });
  start.onclick = () => pywebview.api.autostart(!auto);
  menu.append(start);
  document.body.append(menu);
  // keep the menu inside the small window
  menu.style.left = Math.min(e.clientX, innerWidth - menu.offsetWidth - 2) + "px";
  menu.style.top = Math.min(e.clientY, innerHeight - menu.offsetHeight - 2) + "px";
});
document.addEventListener("click", closeMenu);

document.querySelectorAll(".pick").forEach(sel => sel.onchange = () => { pick = sel.value; tick(); });
$("seek").oninput = () => seeking = true;
$("seek").onchange = () => { seeking = false; send("seek", +$("seek").value); };
window.addEventListener("pywebviewready", async () => {
  sfxOn = (await pywebview.api.pref("sounds")) !== "off";  // sounds are on unless you switched them off
  setLayout();
  loop();
  if (window.drawViz) vizLoop();  // styles without a visualizer never start the audio capture: zero cost
  requestAnimationFrame(frame);  // the browser pauses this by itself while the window is minimized
});
