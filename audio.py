"""Sound for the visualizer and per-app volume.

Visualizer: record what the speakers play ("loopback"), split it into 10 frequency bands.
Capture only runs while a style keeps asking for bands; 2 s without a request and it stops,
so styles without a visualizer cost nothing.
"""
import threading
import time

import comtypes
import numpy as np
import pyaudiowpatch as pa
from pycaw.pycaw import AudioUtilities

EDGES = [20, 100, 200, 400, 800, 1600, 3200, 6400, 10000, 14000, 20000]  # Hz; matches the 70..16k labels
PROCESS = {"308046B0AF4A39CB": "firefox", "MSEdge": "msedge"}  # Windows media ids that aren't the .exe name

_lock = threading.Lock()
_latest = (0.0, None)  # (time, newest samples) written by the audio callback
_last_ask = 0.0
_audio = _stream = None
_rate = _channels = 0


def _on_audio(data, frames, info, status):
    global _latest
    _latest = (time.time(), np.frombuffer(data, np.float32))  # just keep the newest chunk; maths happens on request
    return None, pa.paContinue


def _start():
    global _audio, _stream, _rate, _channels
    _audio = pa.PyAudio()
    dev = _audio.get_default_wasapi_loopback()
    _rate, _channels = int(dev["defaultSampleRate"]), dev["maxInputChannels"]
    # a callback, not stream.read(): in silence Windows sends nothing and read() would wait forever
    _stream = _audio.open(format=pa.paFloat32, channels=_channels, rate=_rate, input=True,
                          input_device_index=dev["index"], frames_per_buffer=2048, stream_callback=_on_audio)
    threading.Thread(target=_stop_when_unused, daemon=True).start()


def _stop_when_unused():
    global _audio, _stream
    while time.time() - _last_ask < 2:
        time.sleep(0.5)
    with _lock:
        _stream.close()
        _audio.terminate()
        _audio = _stream = None


def bands():
    """10 numbers from 0 (quiet) to 1 (loud), bass first."""
    global _last_ask
    _last_ask = time.time()
    with _lock:
        if _stream is None:
            # shortcut: sticks to the speakers that were default at start; switching headphones needs a style switch to pick up
            _start()
    stamp, samples = _latest
    if samples is None or time.time() - stamp > 0.3:  # no fresh sound = silence
        return [0.0] * 10
    return to_bands(samples, _channels, _rate)


def to_bands(samples, channels, rate):
    mono = samples.reshape(-1, channels).mean(axis=1)
    spectrum = np.abs(np.fft.rfft(mono * np.hanning(len(mono)))) / (len(mono) / 4)  # 1.0 = full-volume tone
    freqs = np.fft.rfftfreq(len(mono), 1 / rate)
    out = []
    for lo, hi in zip(EDGES, EDGES[1:]):
        level = spectrum[(freqs >= lo) & (freqs < hi)].max(initial=0)
        db = 20 * np.log10(level + 1e-9)        # ears hear loudness in decibels, not raw numbers
        out.append(float(np.clip((db + 60) / 55, 0, 1)))  # -60 dB = empty bar, -5 dB = full
    return out


def app_volume(source_id, level=None):
    """Read (and with level, set) the Volume Mixer slider of the app behind a media source. None = app not found."""
    comtypes.CoInitialize()  # Windows audio objects need this once per thread
    exe = PROCESS.get(source_id, source_id.lower().removesuffix(".exe")).lower() + ".exe"
    found = [s.SimpleAudioVolume for s in AudioUtilities.GetAllSessions()
             if s.Process and s.Process.name().lower() == exe]  # browsers have several; move them together
    if level is not None:
        for v in found:
            v.SetMasterVolume(min(max(float(level), 0.0), 1.0), None)
    return found[0].GetMasterVolume() if found else None
