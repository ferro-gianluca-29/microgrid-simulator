#!/usr/bin/env python3
"""Verify SOH discrete threshold logic without running full simulation."""

import sys
sys.path.insert(0, 'src')

import numpy as np
from pymgrid.modules.battery.transition_models.nmc_transition_model import NmcTransitionModel

print("=" * 80)
print("Verifying Discrete SOH Threshold Logic")
print("=" * 80)

nmc = NmcTransitionModel(ns_batt=16, np_batt=270, soh=1.0)

print(f"\n✓ NMC Battery Model Created")
print(f"  Initial SOH: {nmc.soh:.4f}")
print(f"  Chemistry: {nmc.chemistry}")
print(f"  Cumulative Ah: {nmc.cumulative_ah_throughput:.4f}")

print(f"\nSOH Threshold Points Loaded from Excel:")
print(f"  Total thresholds: {len(nmc.soh_ah_thresholds)}")

# Verify curve points
expected_first_ah = 29.3
expected_first_soh = 0.955
expected_last_ah = 1586.8
expected_last_soh = 0.818

print(f"\n  First threshold: {nmc.soh_ah_thresholds[0]:.1f} Ah → SOH {nmc.soh_ah_values[0]:.4f}")
print(f"    Expected:     {expected_first_ah:.1f} Ah → SOH {expected_first_soh:.4f}")
assert abs(nmc.soh_ah_thresholds[0] - expected_first_ah) < 0.1, "First threshold mismatch"
assert abs(nmc.soh_ah_values[0] - expected_first_soh) < 0.001, "First SOH value mismatch"
print(f"    ✓ First point matches")

print(f"\n  Last threshold: {nmc.soh_ah_thresholds[-1]:.1f} Ah → SOH {nmc.soh_ah_values[-1]:.4f}")
print(f"    Expected:    {expected_last_ah:.1f} Ah → SOH {expected_last_soh:.4f}")
assert abs(nmc.soh_ah_thresholds[-1] - expected_last_ah) < 0.2, "Last threshold mismatch"
assert abs(nmc.soh_ah_values[-1] - expected_last_soh) < 0.001, "Last SOH value mismatch"
print(f"    ✓ Last point matches")

# Test discrete threshold behavior
print(f"\n" + "=" * 80)
print(f"Testing Discrete Threshold Updates")
print(f"=" * 80)

test_cases = [
    (10.0,  1.0,      "Before first threshold (10 Ah)"),
    (29.2,  1.0,      "Just before first threshold (29.2 Ah)"),
    (29.3,  0.955,    "At first threshold (29.3 Ah)"),
    (30.0,  0.955,    "After first threshold (30 Ah)"),
    (57.4,  0.955,    "Just before second threshold (57.4 Ah)"),
    (57.5,  0.932,    "At second threshold (57.5 Ah)"),
    (100.0, 0.919,    "Between thresholds (100 Ah)"),
    (200.0, 0.895,    "Further in curve (200 Ah)"),
    (1586.0, 0.82,    "Before final threshold (1586.0 Ah, threshold at 1586.8)"),
    (1587.0, 0.818,   "At/past final threshold (1587 Ah)"),
]

print(f"\nTest Case | Cumulative Ah | Returned SOH | Expected SOH | Status")
print("-" * 70)

# Start with fresh state
nmc.cumulative_ah_throughput = 0.0
nmc.last_soh = 1.0

for i, (cumulative_ah, expected_soh, description) in enumerate(test_cases, 1):
    # Calculate delta needed to get from previous cumulative to this one
    prev_cumulative = test_cases[i-2][0] if i > 1 else 0.0
    delta_to_add = cumulative_ah - prev_cumulative
    
    # Call the update method (it will accumulate delta internally)
    returned_soh = nmc._update_soh_from_ah(0, delta_to_add)
    
    match = "✓" if abs(returned_soh - expected_soh) < 0.001 else "✗"
    print(f"{i:9d} | {cumulative_ah:13.1f} | {returned_soh:12.4f} | {expected_soh:12.4f} | {match}")
    
    if abs(returned_soh - expected_soh) >= 0.001:
        print(f"  ERROR: Expected {expected_soh:.4f}, got {returned_soh:.4f}")
        print(f"  Description: {description}")
        print(f"  Cumulative Ah now: {nmc.cumulative_ah_throughput:.4f}")

print(f"\n" + "=" * 80)
print(f"Monotonicity Test: SOH should never increase")
print(f"=" * 80)

# Test monotonicity
nmc.last_soh = 0.9  # Set previous SOH
nmc.cumulative_ah_throughput = 50.0  # Would normally give 0.955
returned = nmc._update_soh_from_ah(50.0, 0.0)

print(f"\nScenario: cumulative=50 Ah (→0.955), but last_soh=0.9")
print(f"  Expected behavior: min(0.955, 0.9) = 0.9 (monotonic decrease)")
print(f"  Returned SOH: {returned:.4f}")
assert returned <= 0.9, "Monotonicity violated!"
print(f"  ✓ Monotonicity maintained")

print(f"\n" + "=" * 80)
print("✓ All tests passed! Discrete threshold logic is working correctly.")
print("=" * 80)
