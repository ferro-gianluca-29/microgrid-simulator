#!/usr/bin/env python3
"""Test that SOH starts from 1.0."""

import sys
sys.path.insert(0, 'src')

from pymgrid.modules.battery.transition_models.nmc_transition_model import NmcTransitionModel

print("=" * 70)
print("Testing SOH initialization and first few steps")
print("=" * 70)

nmc = NmcTransitionModel(soh=1.0, np_batt=270)

print(f"\nInitial state:")
print(f"  Initial SOH (self.soh): {nmc.soh}")
print(f"  Last SOH (self.last_soh): {nmc.last_soh}")
print(f"  Cumulative throughput: {nmc.cumulative_ah_throughput}")

print(f"\nTesting _update_soh_from_ah() calls:")
print("Step | Throughput Ah | Delta Ah | Updated SOH | Expected")
print("-" * 70)

# Test first few steps with small deltas
test_deltas = [10, 5, 15, 20, 50, 100]
current_ah = 0.0

for step, delta in enumerate(test_deltas, 1):
    current_ah += delta
    updated_soh = nmc._update_soh_from_ah(current_ah, delta)
    
    # Expected: SOH=1.0 while throughput < 1, then decrease
    expected = "1.0000" if current_ah < 1.0 else "decreased"
    
    print(f"{step:4d} | {current_ah:13.1f} | {delta:8.1f} | {updated_soh:11.4f} | {expected}")

print("\n" + "=" * 70)
print("Check: SOH should be 1.0000 for all steps where throughput < 1 Ah")
print("=" * 70)
