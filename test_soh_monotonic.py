#!/usr/bin/env python3
"""Test monotonic SOH decrease."""

import sys
sys.path.insert(0, 'src')

from pymgrid.modules.battery.transition_models.nmc_transition_model import NmcTransitionModel
import numpy as np

print("=" * 70)
print("Testing monotonic SOH decrease with throughput accumulation")
print("=" * 70)

nmc = NmcTransitionModel(soh=1.0, np_batt=270)

print("\nSimulating throughput accumulation and SOH update:")
print("Step | Throughput Ah | Delta Ah | Updated SOH | Last SOH | Monotonic?")
print("-" * 70)

# Simulate increasing throughput with variable delta_ah (charge/discharge cycles)
current_ah_per_cell = 0.0
last_soh = 1.0

test_deltas = [50, 100, 50, 80, 120, 100, 150, 50, 80, 100]

for step, delta in enumerate(test_deltas, 1):
    current_ah_per_cell += delta
    
    # Call the update method
    updated_soh = nmc._update_soh_from_ah(current_ah_per_cell, delta)
    
    # Check if monotonic
    is_monotonic = updated_soh <= last_soh
    mono_str = "✓" if is_monotonic else "✗ VIOLATION"
    
    print(f"{step:4d} | {current_ah_per_cell:13.1f} | {delta:8.1f} | {updated_soh:11.4f} | {last_soh:8.4f} | {mono_str}")
    
    last_soh = updated_soh

print("\n" + "=" * 70)
if all(nmc._update_soh_from_ah(i*10, 10) <= nmc.last_soh for i in range(1, 100)):
    print("✓ SOH is monotonically decreasing throughout simulation!")
else:
    print("✗ SOH violations detected!")
print("=" * 70)
