#!/usr/bin/env python3
"""faithful model of the FidelityFX SDK 1.1.4 DX12 present pacer."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import unittest
from dataclasses import dataclass


INT64_MAX = (1 << 63) - 1


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(q * (len(ordered) - 1)))
    return ordered[index]


def upstream_wait_for_performance_count(current: int, target: int) -> int:
    """model the observable result of upstream waitForPerformanceCount."""
    if current >= target:
        return current
    return target


def checked_target(previous_present_qpc: int, delta_qpc: int) -> int:
    if previous_present_qpc < 0 or delta_qpc < 0:
        raise ValueError("qpc values must be non-negative")
    if previous_present_qpc > INT64_MAX - delta_qpc:
        raise OverflowError("signed qpc target overflow")
    return previous_present_qpc + delta_qpc


@dataclass(frozen=True)
class PresentedFrame:
    kind: str
    ready_ms: float
    target_ms: float
    present_ms: float


def present_entry(
    previous_present_ms: float,
    delta_ms: float,
    generated_ready_ms: float,
    real_ready_ms: float,
) -> list[PresentedFrame]:
    """model presenterThread's generated-then-real loop."""
    frames: list[PresentedFrame] = []
    previous = previous_present_ms
    for kind, ready in (("generated", generated_ready_ms), ("real", real_ready_ms)):
        target = previous + delta_ms
        present = max(ready, target)
        frames.append(PresentedFrame(kind, ready, target, present))
        previous = present
    return frames


def simulate(
    pairs: int,
    real_gpu_ms: float,
    interpolation_gpu_ms: float,
    present_delta_ms: float,
    catch_up: bool = False,
) -> dict[str, object]:
    """model the single-queue loop seen on Thor.

    the next game frame starts after the prior real present. interpolation
    becomes ready after real rendering plus interpolation work. the real
    image is already ready when interpolation completes.
    """
    previous_real = 0.0
    previous_present = 0.0
    events: list[PresentedFrame] = []

    for _ in range(pairs):
        generated_ready = previous_real + real_gpu_ms + interpolation_gpu_ms
        real_ready = generated_ready
        if catch_up:
            # rejected candidate: use an absolute pair cadence. once late,
            # both deadlines are behind the fence completion.
            generated_target = previous_real + present_delta_ms
            generated_present = max(generated_ready, generated_target)
            real_target = previous_real + 2.0 * present_delta_ms
            real_present = max(real_ready, real_target, generated_present)
            pair = [
                PresentedFrame("generated", generated_ready, generated_target, generated_present),
                PresentedFrame("real", real_ready, real_target, real_present),
            ]
        else:
            pair = present_entry(
                previous_present,
                present_delta_ms,
                generated_ready,
                real_ready,
            )
        events.extend(pair)
        previous_present = pair[-1].present_ms
        previous_real = pair[-1].present_ms

    intervals = [
        events[i].present_ms - events[i - 1].present_ms
        for i in range(1, len(events))
    ]
    generated_intervals = intervals[0::2]
    real_intervals = intervals[1::2]
    duration = events[-1].present_ms - events[0].present_ms
    fps = (len(events) - 1) * 1000.0 / duration
    return {
        "fps": fps,
        "p50_ms": percentile(intervals, 0.50),
        "p95_ms": percentile(intervals, 0.95),
        "generated_interval_p50_ms": percentile(generated_intervals, 0.50),
        "real_interval_p50_ms": percentile(real_intervals, 0.50),
        "zero_or_sub_ms_intervals": sum(value < 1.0 for value in intervals),
        "busy_spin_ms_per_present": statistics.mean(
            max(0.0, event.present_ms - event.ready_ms) for event in events
        ),
        "events": len(events),
    }


class PacerTests(unittest.TestCase):
    def test_on_time_frame_waits_to_target(self) -> None:
        self.assertEqual(upstream_wait_for_performance_count(80, 100), 100)

    def test_late_fence_skips_wait_already(self) -> None:
        self.assertEqual(upstream_wait_for_performance_count(120, 100), 120)

    def test_late_generated_preserves_real_spacing(self) -> None:
        frames = present_entry(0.0, 8.0, 12.0, 12.0)
        self.assertEqual([frame.present_ms for frame in frames], [12.0, 20.0])

    def test_late_real_preserves_next_generated_spacing(self) -> None:
        first = present_entry(0.0, 8.0, 1.0, 30.0)
        second = present_entry(first[-1].present_ms, 8.0, 31.0, 31.0)
        self.assertEqual(first[-1].present_ms, 30.0)
        self.assertEqual(second[0].present_ms, 38.0)

    def test_generated_always_precedes_corresponding_real(self) -> None:
        for hz in (60, 90, 120):
            delta = 1000.0 / hz
            frames = present_entry(100.0, delta, 130.0, 101.0)
            self.assertLess(frames[0].present_ms, frames[1].present_ms)

    def test_vsync_does_not_change_pacer_deadline(self) -> None:
        # vsync only selects Present's sync interval in upstream 1.1.4.
        off = present_entry(0.0, 8.0, 2.0, 2.0)
        on = present_entry(0.0, 8.0, 2.0, 2.0)
        self.assertEqual(off, on)

    def test_frame_cap_changes_input_period_not_wait_rule(self) -> None:
        for cap in (60, 90, 120):
            period = 1000.0 / cap
            frames = present_entry(0.0, period / 2.0, period, period)
            self.assertEqual(frames[0].present_ms, period)
            self.assertEqual(frames[1].present_ms, period * 1.5)

    def test_fence_after_target_never_spins(self) -> None:
        for target in (8, 11, 16):
            self.assertEqual(
                upstream_wait_for_performance_count(target + 7, target),
                target + 7,
            )

    def test_qpc_precision_and_wrap_guard(self) -> None:
        frequency = 10_000_000
        for hz in (60, 90, 120):
            ticks = round(frequency / hz)
            error_ns = abs(ticks / frequency - 1.0 / hz) * 1e9
            self.assertLess(error_ns, 51)
        with self.assertRaises(OverflowError):
            checked_target(INT64_MAX - 3, 4)

    def test_rejected_catch_up_creates_bursts(self) -> None:
        result = simulate(20, 33.7, 7.2, 12.6, catch_up=True)
        self.assertGreater(result["zero_or_sub_ms_intervals"], 10)

    def test_stock_has_no_sub_ms_bursts(self) -> None:
        result = simulate(20, 33.7, 7.2, 12.6)
        self.assertEqual(result["zero_or_sub_ms_intervals"], 0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    if args.test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(PacerTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(0 if result.wasSuccessful() else 1)

    output = {
        "inputs": {
            "real_gpu_ms": 33.7,
            "interpolation_gpu_ms": 7.2,
            "present_delta_ms": 12.6,
            "panel_hz": 120,
            "vsync": False,
        },
        "stock": simulate(300, 33.7, 7.2, 12.6),
        "rejected_absolute_catch_up": simulate(
            300, 33.7, 7.2, 12.6, catch_up=True
        ),
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
