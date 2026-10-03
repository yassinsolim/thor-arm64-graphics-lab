#!/usr/bin/env python3
"""Launch one Godot renderer and record an unprivileged host sample.

No sudo. The optional Adreno counter command is printed, not executed.
"""

import argparse
import json
import os
import pty
import select
import signal
import subprocess
import sys
import time
from pathlib import Path


MEASURE_SEC = 20.0
READY_TIMEOUT = 600.0
MEM_AVAILABLE_MIN_KB = int(1.5 * 1024 * 1024)
ZRAM_USED_MAX_KB = 6 * 1024 * 1024


def read_text(path):
    try:
        return Path(path).read_text(errors="replace")
    except OSError:
        return ""


def meminfo():
    out = {}
    for line in read_text("/proc/meminfo").splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            out[key] = int(parts[0])
    return out


def zram_used_kb():
    used = 0
    for line in read_text("/proc/swaps").splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4 and "zram" in parts[0]:
            used += int(parts[3])
    return used


def memory_stop():
    if not Path("/proc/meminfo").is_file():
        return None
    info = meminfo()
    avail = info.get("MemAvailable")
    zram = zram_used_kb()
    if avail is not None and avail < MEM_AVAILABLE_MIN_KB and zram > ZRAM_USED_MAX_KB:
        return f"memory pressure MemAvailable_kB={avail} zram_used_kB={zram}"
    return None


def fdinfo_gpu(pid):
    base = Path(f"/proc/{pid}/fdinfo")
    best = None
    best_v = -1
    if not base.is_dir():
        return None
    for name in base.iterdir():
        text = read_text(name)
        if "drm-engine-gpu" not in text:
            continue
        engine = None
        for line in text.splitlines():
            if line.startswith("drm-engine-gpu"):
                engine = int(line.split()[1])
        if engine is not None and engine > best_v:
            best_v = engine
            best = engine
    return best


def gpu_clock_hz():
    candidates = [
        "/sys/devices/platform/soc@0/3d00000.gpu/devfreq/3d00000.gpu/cur_freq",
    ]
    for path in candidates:
        text = read_text(path).strip()
        if text.isdigit():
            return int(text)
    devfreq = Path("/sys/class/devfreq")
    if devfreq.is_dir():
        for child in devfreq.iterdir():
            if "gpu" not in child.name and "3d" not in child.name:
                continue
            text = read_text(child / "cur_freq").strip()
            if text.isdigit():
                return int(text)
    return None


def gpu_temp_c():
    thermal = Path("/sys/class/thermal")
    if not thermal.is_dir():
        return None
    for zone in sorted(thermal.glob("thermal_zone*")):
        kind = read_text(zone / "type").strip().lower()
        if not any(token in kind for token in ("gpu", "gpuss", "adreno")):
            continue
        raw = read_text(zone / "temp").strip()
        if raw.lstrip("-").isdigit():
            value = int(raw)
            return value / 1000.0 if abs(value) > 200 else float(value)
    return None


def proc_cpu_jiffies(pid):
    text = read_text(f"/proc/{pid}/stat")
    if not text:
        return None
    end = text.rfind(")")
    if end < 0:
        return None
    fields = text[end + 2:].split()
    # utime and stime are fields 14 and 15, 1-based, so indexes 11 and 12
    # after the comm field is removed.
    if len(fields) < 13:
        return None
    return int(fields[11]) + int(fields[12])


def proc_rss_kb(pid):
    for line in read_text(f"/proc/{pid}/status").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    return None


def xprop(display, atom):
    try:
        proc = subprocess.run(
            ["xprop", "-display", display, "-root", atom],
            capture_output=True, text=True, timeout=2, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def focus_id(display):
    text = xprop(display, "GAMESCOPE_FOCUSED_APP")
    if not text:
        return None
    for token in text.split():
        if token.isdigit():
            return int(token)
    return None


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    idx = int(q * (len(ordered) - 1))
    return ordered[idx]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--renderer", required=True, choices=("forward_plus", "mobile"))
    parser.add_argument("--driver", required=True)
    parser.add_argument("--audio-driver", default="Dummy")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--display", default=os.environ.get("DISPLAY", ":0"))
    parser.add_argument("--user-arg", action="append", default=[])
    parser.add_argument("--godot-arg", action="append", default=[])
    args = parser.parse_args()

    log_path = args.out.with_suffix(".log")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        args.godot,
        *args.godot_arg,
        "--path", args.project,
        "--windowed",
        "--resolution", "1280x720",
        "--position", "40,40",
        "--rendering-driver", args.driver,
        "--rendering-method", args.renderer,
        "--audio-driver", args.audio_driver,
        "--",
        "--benchmark",
        *args.user_arg,
    ]
    master, slave = pty.openpty()
    proc = subprocess.Popen(cmd, stdout=slave, stderr=slave, stdin=slave, close_fds=True)
    os.close(slave)
    lines = []
    pending = ""
    ready = None
    measure_start = None
    done = None
    fail = None
    stop = None
    samples = []
    fd_start = None
    cpu_start = None
    deadline = time.monotonic() + READY_TIMEOUT
    cpu_last = None

    def take_line(line):
        nonlocal ready, measure_start, done, fail, fd_start, cpu_start
        lines.append(line)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
        if line.startswith("BENCHMARK_READY") and ready is None:
            ready = time.monotonic()
        elif line.startswith("BENCHMARK_MEASURE_START") and measure_start is None:
            measure_start = time.monotonic()
            fd_start = fdinfo_gpu(proc.pid)
            cpu_start = proc_cpu_jiffies(proc.pid)
            print(f"BENCHMARK_PID {proc.pid}", flush=True)
        elif line.startswith("BENCHMARK_DONE"):
            done = line[len("BENCHMARK_DONE "):].strip()
        elif line.startswith("BENCHMARK_FAIL"):
            fail = line.split(None, 1)[1].strip() if " " in line else "fail"

    while True:
        now = time.monotonic()
        if measure_start is None and now > deadline:
            stop = "no BENCHMARK_MEASURE_START within 600s"
            proc.send_signal(signal.SIGTERM)
            break
        if measure_start is not None:
            pressure = memory_stop()
            if pressure:
                stop = pressure
                proc.send_signal(signal.SIGTERM)
                break
            elapsed = now - measure_start
            if len(samples) == 0 or now - samples[-1]["t"] >= 0.5:
                cpu_last = proc_cpu_jiffies(proc.pid)
                samples.append({
                    "t": round(elapsed, 3),
                    "rss_kb": proc_rss_kb(proc.pid),
                    "gpu_hz": gpu_clock_hz(),
                    "gpu_temp_c": gpu_temp_c(),
                    "mem_available_kb": meminfo().get("MemAvailable"),
                    "focus": focus_id(args.display),
                    "fdinfo_engine_ns": fdinfo_gpu(proc.pid),
                })
            if done is not None or fail is not None:
                break
            if elapsed > MEASURE_SEC + 30:
                stop = "measure window exceeded 50s without BENCHMARK_DONE"
                proc.send_signal(signal.SIGTERM)
                break
        readable, _, _ = select.select([master], [], [], 0.2)
        if not readable:
            if proc.poll() is not None:
                break
            continue
        try:
            chunk = os.read(master, 65536)
        except OSError:
            break
        if not chunk:
            if proc.poll() is not None:
                break
            continue
        pending += chunk.decode("utf-8", errors="replace")
        while "\n" in pending:
            line, pending = pending.split("\n", 1)
            line = line.rstrip("\r")
            if line:
                take_line(line)
    if pending.strip():
        take_line(pending.strip())
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    os.close(master)
    log_path.write_text("\n".join(lines) + "\n")

    summary = None
    if done:
        try:
            summary = json.loads(done)
        except json.JSONDecodeError:
            summary = {"raw": done}
    fd_end = samples[-1]["fdinfo_engine_ns"] if samples else None
    wall = None
    busy = None
    if measure_start is not None:
        wall = time.monotonic() - measure_start
    if fd_start is not None and fd_end is not None and wall:
        busy = (fd_end - fd_start) / (wall * 1e9)
    cpu_end = cpu_last if cpu_last is not None else proc_cpu_jiffies(proc.pid)
    hz = os.sysconf(os.sysconf_names["SC_CLK_TCK"]) if "SC_CLK_TCK" in os.sysconf_names else None
    cpu_s = None
    if cpu_start is not None and cpu_end is not None and hz:
        cpu_s = (cpu_end - cpu_start) / hz
    focuses = [row["focus"] for row in samples if row["focus"] is not None]
    focus = focuses[-1] if focuses else focus_id(args.display)
    report = {
        "renderer": args.renderer,
        "driver": args.driver,
        "pid": proc.pid,
        "exit_code": proc.returncode,
        "ready": ready is not None,
        "summary": summary,
        "fail": fail,
        "stop": stop,
        "wall_s": wall,
        "gpu_busy": busy,
        "cpu_s": cpu_s,
        "focus": focus,
        "display": args.display,
        "samples": samples,
        "log": str(log_path),
    }
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {args.out}")
    if stop or fail or proc.returncode not in (0, None):
        return 1
    if not summary or summary.get("frames", 0) < 30:
        return 1
    if summary.get("width") != 1280 or summary.get("height") != 720:
        print(f"window size {summary.get('width')}x{summary.get('height')}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
