from __future__ import annotations

import random

ACCEL_MPS2 = 2.5
DECEL_MPS2 = 3.5
MOTION_THRESHOLD_KMH = 2.0


def kmh_to_mps(kmh: float) -> float:
    return kmh / 3.6


def mps_to_kmh(mps: float) -> float:
    return mps * 3.6


def apply_dynamics(
    current_kmh: float,
    target_kmh: float,
    dt_seconds: float,
) -> float:
    if dt_seconds <= 0:
        return current_kmh

    current_mps = kmh_to_mps(current_kmh)
    target_mps = kmh_to_mps(max(0.0, target_kmh))
    diff = target_mps - current_mps

    if abs(diff) < 0.05:
        return max(0.0, target_kmh)

    max_delta = (ACCEL_MPS2 if diff > 0 else DECEL_MPS2) * dt_seconds
    if abs(diff) <= max_delta:
        new_mps = target_mps
    else:
        new_mps = current_mps + max_delta * (1 if diff > 0 else -1)

    return max(0.0, mps_to_kmh(new_mps))


def jitter_target_speed(base_kmh: float, speed_factor: float = 1.0) -> float:
    jitter = random.uniform(-0.08, 0.08)
    value = base_kmh * speed_factor * (1.0 + jitter)
    return max(5.0, min(130.0, value))
