#!/usr/bin/env python3
"""Test SOH curve as discrete thresholds."""

import sys
sys.path.insert(0, 'src')

from pymgrid.modules.battery.transition_models.nmc_transition_model import NmcTransitionModel

print("=" * 70)
print("Testing SOH as discrete threshold-based values from curve")
print("=" * 70)

nmc = NmcTransitionModel(soh=1.0, np_batt=270)

print(f"\nCurve thresholds from Excel:")
for i, (ah_thresh, soh_val) in enumerate(zip(nmc.soh_ah_thresholds, nmc.soh_ah_values)):
    print(f"  Point {i}: {ah_thresh:.1f} Ah -> SOH = {soh_val:.4f} ({soh_val*100:.1f}%)")

print(f"\nTesting cumulative throughput and SOH updates:")
print("Step | Cumulative Ah | Updated SOH | Previous SOH | Expected Behavior")
print("-" * 70)

current_ah = 0.0
test_deltas = [10, 10, 10, 20, 30, 50, 100, 150, 200]
expected_soh = 1.0  # Starts at 1.0

for step, delta in enumerate(test_deltas, 1):
    current_ah += delta
    updated_soh = nmc._update_soh_from_ah(current_ah, delta)
    
    # Determine expected SOH based on thresholds
    next_expected = 1.0
    for ah_thresh, soh_val in zip(nmc.soh_ah_thresholds, nmc.soh_ah_values):
        if current_ah >= ah_thresh:
            next_expected = soh_val
        else:
            break
    
    expected_str = f"Expected {next_expected:.4f}"
    status = "✓" if abs(updated_soh - next_expected) < 0.0001 else f"✗ (got {updated_soh:.4f})"
    
    print(f"{step:4d} | {current_ah:13.1f} | {updated_soh:11.4f} | {expected_soh:12.4f} | {expected_str} {status}")
    
    expected_soh = updated_soh

print("\n" + "=" * 70)
print("Behavior: SOH should stay at 1.0 until 29.3 Ah, then drop to 0.955")
print("=" * 70)
