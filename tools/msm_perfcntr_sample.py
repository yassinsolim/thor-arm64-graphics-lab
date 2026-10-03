#!/usr/bin/env python3
"""Sample Adreno performance counters through DRM_IOCTL_MSM_PERFCNTR_CONFIG.

Linux 7.2 samples the whole GPU from this ioctl. MSM_PERFCNTR_STREAM is
gated by perfmon_capable() (CAP_PERFMON or CAP_SYS_ADMIN). The unprivileged
call returns EPERM. Closing this process closes the returned anon fd, and
the kernel releases the single global stream. This script does not touch
debugfs, does not change permissions, and does not open the game binary.

Countable ids are the a7xx select values from the kernel's
drivers/gpu/drm/msm/registers/adreno/a7xx_perfcntrs.xml at v7.2. The ioctl
writes those ids into the group's own select registers. It is not a general
register poke.

The stream is periodic and GPU-wide. It is not a per-renderpass trace.
"""

import argparse
import ctypes
import errno
import json
import os
import pwd
import struct
import subprocess
import time
from pathlib import Path

IOC_PERFCNTR = (1 << 30) | (32 << 16) | (ord("d") << 8) | (0x40 + 0x0E)
STREAM = 0x1
UPDATE = 0x2
GROUP_SIZE = 32

# (group, countable id, name). Slot counts on a7xx: SP 24, TP 12, UCHE 12,
# CCU 5, CP 14 with slot 0 reserved. The kernel allocates the global stream
# from the high slots, so these fit without using CP slot 0.
COUNTERS = [
    ("SP", 0, "sp_busy_cycles"),
    ("SP", 1, "sp_alu_working_cycles"),
    ("SP", 2, "sp_efu_working_cycles"),
    ("SP", 4, "sp_stall_cycles_tp"),
    ("SP", 5, "sp_stall_cycles_uche"),
    ("SP", 6, "sp_stall_cycles_rb"),
    ("SP", 8, "sp_wave_contexts"),
    ("SP", 9, "sp_wave_context_cycles"),
    ("SP", 20, "sp_wave_wait_cycles"),
    ("SP", 22, "sp_wave_idle_cycles"),
    ("SP", 37, "sp_fs_tex_instructions"),
    ("SP", 40, "sp_fs_full_alu_instructions"),
    ("SP", 41, "sp_fs_half_alu_instructions"),
    ("SP", 51, "sp_icl1_requests"),
    ("SP", 52, "sp_icl1_misses"),
    ("SP", 89, "sp_wave_alu_cycles"),
    ("TP", 0, "tp_busy_cycles"),
    ("TP", 1, "tp_stall_cycles_uche"),
    ("TP", 2, "tp_latency_cycles"),
    ("TP", 3, "tp_latency_trans"),
    ("TP", 6, "tp_l1_requests"),
    ("TP", 7, "tp_l1_misses"),
    ("TP", 10, "tp_output_pixels"),
    ("TP", 54, "tp_starve_cycles_sp"),
    ("UCHE", 0, "uche_busy_cycles"),
    ("UCHE", 1, "uche_stall_cycles_arbiter"),
    ("UCHE", 2, "uche_vbif_latency_cycles"),
    ("UCHE", 3, "uche_vbif_latency_samples"),
    ("UCHE", 4, "uche_vbif_read_beats_tp"),
    ("UCHE", 8, "uche_vbif_read_beats_sp"),
    ("UCHE", 27, "uche_vbif_read_beats_ch0"),
    ("UCHE", 28, "uche_vbif_read_beats_ch1"),
    ("UCHE", 52, "uche_vbif_write_beats_ch0"),
    ("UCHE", 53, "uche_vbif_write_beats_ch1"),
    ("UCHE", 29, "uche_gmem_read_beats"),
    ("UCHE", 56, "uche_gmem_write_beats"),
    ("CCU", 0, "ccu_busy_cycles"),
    ("CCU", 8, "ccu_gmem_read"),
    ("CCU", 9, "ccu_gmem_write"),
    ("CCU", 5, "ccu_depth_block_hit"),
    ("CCU", 6, "ccu_color_block_hit"),
    ("CP", 2, "cp_busy_cycles"),
    ("CP", 12, "cp_cache_flush"),
    ("CP", 23, "cp_sqe_sync_stall"),
    ("CP", 47, "cp_vbif_read_beats"),
]


def groups_from_counters(counters):
    order = []
    by = {}
    for group, cid, name in counters:
        if group not in by:
            order.append(group)
            by[group] = []
        by[group].append((cid, name))
    return [(group, by[group]) for group in order]


def ini_flags(path):
    out = {}
    if not path.is_file():
        return out
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith((
            "FSR_FG", "FSR=", "SelectUpscaler", "ResolutionSizeX",
            "ResolutionSizeY", "FrameRateLimit", "bUseVSync",
            "bUseDynamicResolution", "bUseHDRDisplayOutput",
            "bConsoleRayTracing",
        )):
            key, _, val = line.partition("=")
            out[key] = val.strip()
    return out


def focus_app(display=":0"):
    # X access control allows only localuser:armada. A sudo'd process is
    # root, so xprop from this process is refused and looks like no focus.
    # Ask as the invoking user instead. This does not change the X host list.
    cmd = ["xprop", "-display", display, "-root", "GAMESCOPE_FOCUSED_APP"]
    if os.geteuid() == 0 and os.environ.get("SUDO_USER"):
        cmd = ["runuser", "-u", os.environ["SUDO_USER"], "--", *cmd]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=3, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    for token in proc.stdout.split():
        if token.isdigit():
            return int(token)
    return None


def gpu_freq():
    path = Path("/sys/devices/platform/soc@0/3d00000.gpu/devfreq/3d00000.gpu/cur_freq")
    try:
        return int(path.read_text().strip())
    except OSError:
        return None


def fdinfo_gpu(pid):
    base = Path(f"/proc/{pid}/fdinfo")
    best = None
    best_v = -1
    if not base.is_dir():
        return None
    for name in base.iterdir():
        try:
            text = name.read_text()
        except OSError:
            continue
        if "drm-engine-gpu" not in text:
            continue
        engine = cycles = None
        for line in text.splitlines():
            if line.startswith("drm-engine-gpu"):
                engine = int(line.split()[1])
            elif line.startswith("drm-cycles-gpu"):
                cycles = int(line.split()[1])
        if engine is not None and engine > best_v:
            best_v = engine
            best = {"engine_ns": engine, "cycles": cycles}
    return best


def ioctl_config(drm, flags, group_blobs):
    libc = ctypes.CDLL(None, use_errno=True)
    blob = b"".join(group_blobs)
    raw = ctypes.create_string_buffer(blob)
    cfg = struct.pack(
        "<IIQQII",
        flags,
        len(group_blobs),
        ctypes.addressof(raw),
        5_000_000,
        16,
        GROUP_SIZE,
    )
    arg = ctypes.create_string_buffer(cfg)
    rc = libc.ioctl(drm, IOC_PERFCNTR, arg)
    err = ctypes.get_errno()
    return rc, err, raw.raw


def build_group_blobs(grouped):
    blobs = []
    arrays = []
    for group, items in grouped:
        countables = struct.pack("<" + "I" * len(items), *[cid for cid, _ in items])
        hold = ctypes.create_string_buffer(countables)
        arrays.append(hold)
        blobs.append(struct.pack(
            "<16sIIQ",
            group.encode(),
            len(items),
            0,
            ctypes.addressof(hold),
        ))
    return blobs, arrays


def open_stream(grouped):
    drm = os.open("/dev/dri/renderD128", os.O_RDWR)
    blobs, arrays = build_group_blobs(grouped)
    rc, err, _ = ioctl_config(drm, STREAM | UPDATE, blobs)
    if rc < 0:
        os.close(drm)
        raise OSError(err, os.strerror(err))
    os.set_blocking(rc, False)
    return drm, rc, arrays


def parse_sample(data, names):
    timestamp, seqno, _mbz = struct.unpack_from("<QII", data)
    values = struct.unpack_from("<" + "Q" * len(names), data, 16)
    return timestamp, seqno, dict(zip(names, values))


def sample(stream, seconds, names, period, expected_focus=2074920, check_focus=True, display=":0"):
    buf = b""
    rows = []
    gaps = 0
    last_seq = None
    focus_log = []
    lost_focus = None
    deadline = time.monotonic() + seconds
    next_focus = time.monotonic()
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_focus:
            seen = focus_app(display)
            focus_log.append({"t": round(now, 3), "focus": seen})
            next_focus = now + 1.0
            if check_focus and seen != expected_focus:
                lost_focus = seen
                break
        try:
            chunk = os.read(stream, 65536)
        except BlockingIOError:
            time.sleep(0.002)
            continue
        except InterruptedError:
            break
        if not chunk:
            break
        buf += chunk
        while len(buf) >= period:
            timestamp, seqno, values = parse_sample(buf[:period], names)
            buf = buf[period:]
            if last_seq is not None and seqno != (last_seq + 1) & 0xFFFFFFFF:
                gaps += 1
            last_seq = seqno
            rows.append({"timestamp": timestamp, "seqno": seqno, "values": values})
    return rows, gaps, focus_log, lost_focus


def deltas(rows):
    if len(rows) < 2:
        return {}
    first = rows[0]["values"]
    last = rows[-1]["values"]
    out = {}
    for key in first:
        out[key] = last[key] - first[key]
    out["always_on_ticks"] = rows[-1]["timestamp"] - rows[0]["timestamp"]
    return out


def ratio(num, den):
    if not den:
        return None
    return num / den


def summarize(delta):
    # Ratios are last sample minus first. The 20 s FG-off capture had no
    # backward steps, and the sum of 5 ms steps matched that span.
    # SP/TP/UCHE/CCU/CP counters are core-clock cycles or events, not the
    # 19.2 MHz always-on timestamp. UCHE VBIF "beats" are raw; Mesa's
    # derived byte counters multiply those beats by 32.
    busy = delta.get("sp_busy_cycles", 0)
    return {
        "sp_alu_per_busy": ratio(delta.get("sp_alu_working_cycles", 0), busy),
        "sp_efu_per_busy": ratio(delta.get("sp_efu_working_cycles", 0), busy),
        "sp_stall_tp_per_busy": ratio(delta.get("sp_stall_cycles_tp", 0), busy),
        "sp_stall_uche_per_busy": ratio(delta.get("sp_stall_cycles_uche", 0), busy),
        "sp_stall_rb_per_busy": ratio(delta.get("sp_stall_cycles_rb", 0), busy),
        "sp_wave_idle_per_busy": ratio(delta.get("sp_wave_idle_cycles", 0), busy),
        "sp_fs_full_alu_per_tex": ratio(
            delta.get("sp_fs_full_alu_instructions", 0),
            delta.get("sp_fs_tex_instructions", 0),
        ),
        "sp_fs_half_alu_per_tex": ratio(
            delta.get("sp_fs_half_alu_instructions", 0),
            delta.get("sp_fs_tex_instructions", 0),
        ),
        "sp_icl1_miss_rate": ratio(
            delta.get("sp_icl1_misses", 0),
            delta.get("sp_icl1_requests", 0),
        ),
        "sp_wave_contexts_per_cycle": ratio(
            delta.get("sp_wave_contexts", 0),
            delta.get("sp_wave_context_cycles", 0),
        ),
        "tp_l1_miss_rate": ratio(delta.get("tp_l1_misses", 0), delta.get("tp_l1_requests", 0)),
        "tp_stall_uche_per_busy": ratio(
            delta.get("tp_stall_cycles_uche", 0),
            delta.get("tp_busy_cycles", 0),
        ),
        "uche_stall_per_busy": ratio(
            delta.get("uche_stall_cycles_arbiter", 0),
            delta.get("uche_busy_cycles", 0),
        ),
        "uche_vbif_read_beats": (
            delta.get("uche_vbif_read_beats_ch0", 0)
            + delta.get("uche_vbif_read_beats_ch1", 0)
        ),
        "uche_vbif_write_beats": (
            delta.get("uche_vbif_write_beats_ch0", 0)
            + delta.get("uche_vbif_write_beats_ch1", 0)
        ),
        "ccu_gmem_read": delta.get("ccu_gmem_read", 0),
        "ccu_gmem_write": delta.get("ccu_gmem_write", 0),
        "cp_cache_flush": delta.get("cp_cache_flush", 0),
        "cp_sqe_sync_stall": delta.get("cp_sqe_sync_stall", 0),
    }


def give_file_to_sudo_user(path):
    uid = os.environ.get("SUDO_UID")
    gid = os.environ.get("SUDO_GID")
    if uid is None or gid is None:
        return
    os.chown(path, int(uid), int(gid))


def wait_for_focus(timeout, expected_focus=2074920, check_focus=True, display=":0"):
    deadline = time.monotonic() + timeout
    last = focus_app(display)
    if not check_focus:
        return last
    announced = False
    while last != expected_focus and time.monotonic() < deadline:
        if not announced:
            print(f"waiting up to {timeout:.0f}s for Gamescope focus {expected_focus} (now {last})")
            announced = True
        time.sleep(0.5)
        last = focus_app(display)
    return last


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--pid", type=int, default=141377)
    parser.add_argument("--out", type=Path, required=False)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--precheck", action="store_true")
    parser.add_argument("--focus-wait", type=float, default=30.0)
    parser.add_argument(
        "--focus-app",
        type=int,
        default=2074920,
        help="Gamescope app id that must stay focused (default is The First Descendant)",
    )
    parser.add_argument(
        "--display",
        default=":0",
        help="X display for the Gamescope focus atom",
    )
    parser.add_argument(
        "--no-focus-check",
        action="store_true",
        help="log focus but do not refuse. skips the First Descendant settings ini",
    )
    parser.add_argument(
        "--allow-current",
        action="store_true",
        help="sample even if focus is not 2074920 or frame generation is on",
    )
    args = parser.parse_args()

    grouped = groups_from_counters(COUNTERS)
    names = [name for _, items in grouped for _, name in items]
    period = 16 + 8 * len(names)

    if args.status:
        try:
            drm, stream, _arrays = open_stream(grouped)
        except OSError as exc:
            print(f"status: {exc.errno} {exc.strerror}")
            return 1
        os.close(stream)
        os.close(drm)
        print("status: stream opened and released")
        return 0

    if args.out is None and not args.precheck:
        parser.error("--out is required")

    home = Path.home()
    if os.environ.get("SUDO_USER"):
        home = Path(pwd.getpwnam(os.environ["SUDO_USER"]).pw_dir)
    ini = home / ".local/share/Steam/steamapps/compatdata/2074920/pfx/drive_c/users/steamuser/AppData/Local/M1/Saved/Config/Windows/GameUserSettings.ini"
    settings = ini_flags(ini)
    # the ini and the 2074920 default are the First Descendant capture.
    # another focus id, or an explicit skip, does not read that lobby.
    tfd_gate = args.focus_app == 2074920 and not args.no_focus_check
    if tfd_gate and not args.allow_current and settings.get("FSR_FG") != "False":
        print(f"refusing: FSR_FG={settings.get('FSR_FG')}. Turn frame generation off on the lobby first.")
        return 2
    check_focus = not args.no_focus_check
    focus = wait_for_focus(
        0 if (args.allow_current or args.no_focus_check) else args.focus_wait,
        args.focus_app,
        check_focus and not args.allow_current,
        args.display,
    )
    if args.precheck:
        print(f"precheck focus={focus} FSR_FG={settings.get('FSR_FG')} pid={args.pid}")
        print("xauthority: none, Xwayland :0 is started without -auth")
        if args.no_focus_check:
            return 0
        return 0 if focus == args.focus_app else 2
    if check_focus and not args.allow_current and focus != args.focus_app:
        print(f"refusing: Gamescope focus is {focus}, want {args.focus_app}")
        return 2

    try:
        drm, stream, _arrays = open_stream(grouped)
    except OSError as exc:
        if exc.errno == errno.EPERM:
            print("EPERM: MSM_PERFCNTR_STREAM requires CAP_PERFMON. Run this with sudo.")
        else:
            print(f"ioctl failed: {exc.errno} {exc.strerror}")
        return 1

    gpu_before = fdinfo_gpu(args.pid)
    freq_before = gpu_freq()
    wall0 = time.time()
    mono0 = time.monotonic()
    try:
        rows, gaps, focus_log, lost_focus = sample(
            stream, args.seconds, names, period,
            args.focus_app, check_focus, args.display,
        )
    finally:
        os.close(stream)
        os.close(drm)
    wall1 = time.time()
    gpu_after = fdinfo_gpu(args.pid)
    freq_after = gpu_freq()
    delta = deltas(rows)
    report = {
        "kernel_uapi": "DRM_IOCTL_MSM_PERFCNTR_CONFIG MSM_PERFCNTR_STREAM",
        "period_ns": 5_000_000,
        "sample_bytes": period,
        "counters": [{"group": g, "id": cid, "name": name} for g, cid, name in COUNTERS],
        "settings": settings,
        "focus": focus,
        "focus_log": focus_log,
        "valid": lost_focus is None,
        "lost_focus": lost_focus,
        "pid": args.pid,
        "wall_start": wall0,
        "wall_end": wall1,
        "elapsed_s": time.monotonic() - mono0,
        "samples": len(rows),
        "gaps": gaps,
        "gpu_hz_start": freq_before,
        "gpu_hz_end": freq_after,
        "fdinfo_start": gpu_before,
        "fdinfo_end": gpu_after,
        "delta": delta,
        "summary": summarize(delta),
        "rows": rows,
    }
    args.out.write_text(json.dumps(report))
    give_file_to_sudo_user(args.out)
    print(f"wrote {args.out} samples {len(rows)} gaps {gaps} valid {lost_focus is None}")
    if lost_focus is not None:
        print(f"invalid: Gamescope focus left the game ({lost_focus})")
        return 3
    for key, value in report["summary"].items():
        if isinstance(value, float):
            print(f"  {key} {value:.4f}")
        else:
            print(f"  {key} {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
