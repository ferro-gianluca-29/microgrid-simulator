#!/usr/bin/env python3
"""Test NMC model with SOH curve."""

import sys
sys.path.insert(0, 'src')

from pymgrid.modules.battery.transition_models.nmc_transition_model import NmcTransitionModel

print("=" * 60)
print("Testing NMC model with SOH curve loading")
print("=" * 60)

print("\nCreating NMC model...")
try:
    nmc = NmcTransitionModel(soh=1.0)
    print("✓ NMC model created successfully")
    print(f"  Chemistry: {nmc.chemistry}")
    print(f"  SOH grid: {nmc.soh_grid}")
    print(f"  SOH Ah interpolator loaded: {nmc.soh_ah_interpolator is not None}")
    print(f"  Cumulative Ah tracker initialized: {nmc.cumulative_ah}")
except Exception as e:
    print(f"✗ Failed to create NMC model: {e}")
    import traceback
    traceback.print_exc()

print("\nTesting SOH curve interpolation...")
try:
    nmc = NmcTransitionModel(soh=1.0)
    
    # Test interpolation at a few points
    test_ah_values = [0, 100, 500, 1000, 1500]
    print("  Ah_throughput -> SOH (%):")
    for ah in test_ah_values:
        soh_frac = nmc.soh_ah_interpolator(ah)
        soh_percent = soh_frac * 100
        print(f"    {ah:6.1f} Ah -> {soh_percent:.2f}% ({soh_frac:.4f})")
    
    print("✓ SOH curve interpolation working")
except Exception as e:
    print(f"✗ Failed to test SOH curve: {e}")
    import traceback
    traceback.print_exc()

print("\nTesting _update_soh_from_ah() method...")
try:
    nmc = NmcTransitionModel(soh=1.0)
    
    # Simulate some Ah throughput and update SOH
    test_ah_per_cell = [0, 100, 500, 1000]
    print("  Current Ah per cell -> Updated SOH:")
    for ah in test_ah_per_cell:
        updated_soh = nmc._update_soh_from_ah(ah)
        print(f"    {ah:6.1f} Ah -> SOH = {updated_soh:.4f}")
    
    print("✓ SOH update method working")
except Exception as e:
    print(f"✗ Failed to test SOH update: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("All tests completed!")
print("=" * 60)
