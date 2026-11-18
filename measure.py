"""How much does each style cost your PC?  Play some music, then:  python measure.py

Starts the widget once per style, waits for it to settle, then samples CPU and RAM of the
widget's whole process family (Python + the hidden Edge WebView2 processes that draw it).
"""
import subprocess
import sys
import time
from pathlib import Path

import psutil

HERE = Path(__file__).parent
WARMUP, SECONDS = 8, 20


def family(proc):
    try:
        return [proc] + proc.children(recursive=True)
    except psutil.NoSuchProcess:
        return []


def measure(style):
    app = subprocess.Popen([sys.executable, str(HERE / "app.py"), "--style", style], cwd=HERE)
    root = psutil.Process(app.pid)
    time.sleep(WARMUP)
    seen = {}  # cpu_percent() measures "since last call", so each process must be asked once before it counts
    cpu, ram = [], []
    for _ in range(SECONDS + 1):
        total_cpu = total_ram = 0
        for p in family(root):
            try:
                if p.pid not in seen:
                    seen[p.pid] = p
                    p.cpu_percent()
                    continue
                total_cpu += p.cpu_percent()
                total_ram += p.memory_full_info().uss  # "unique" memory: shared parts aren't counted 7 times
            except psutil.NoSuchProcess:
                pass
        cpu.append(total_cpu)  # % of ONE core; divided by core count below for "% of the whole PC"
        ram.append(total_ram / 2**20)
        time.sleep(1)
    for p in family(root)[::-1]:  # kill children first, then Python; no settings get saved
        p.kill()
    cpu, ram = cpu[1:], ram[1:]  # first round only primed the counters
    return sum(cpu) / len(cpu), max(cpu), max(ram), len(seen)


if __name__ == "__main__":
    styles = sys.argv[1:] or sorted(p.stem for p in (HERE / "skins").glob("*.html"))
    cores = psutil.cpu_count()
    print(f"{cores} logical cores. 'Whole PC' is what Task Manager shows; 'one core' is easier to compare.")
    print(f"{'style':<12} {'whole PC':>9} {'one core':>9} {'peak 1 core':>12} {'RAM':>7} {'processes':>10}")
    for s in styles:
        avg, peak, ram, n = measure(s)
        print(f"{s:<12} {avg / cores:>8.2f}% {avg:>8.1f}% {peak:>11.1f}% {ram:>5.0f}MB {n:>10}", flush=True)
