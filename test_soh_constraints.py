#!/usr/bin/env python3
"""Test SOH constraints for different chemistries."""

import sys
sys.path.insert(0, 'src')

from pymgrid.modules.battery.transition_models.lfp_transition_model import LfpTransitionModel
from pymgrid.modules.battery.transition_models.nmc_transition_model import NmcTransitionModel
from pymgrid.modules.battery.transition_models.nca_transition_model import NcaTransitionModel

print("=" * 60)
print("Testing LFP with SOH=1.0 (should work)...")
print("=" * 60)
try:
    lfp = LfpTransitionModel(soh=1.0)
    print(f"✓ LFP created with SOH=1.0")
    print(f"  Chemistry: {lfp.chemistry}")
    print(f"  SOH grid: {lfp.soh_grid}")
except Exception as e:
    print(f"✗ LFP failed: {e}")

print("\n" + "=" * 60)
print("Testing LFP with SOH=0.9 (should fail)...")
print("=" * 60)
try:
    lfp_bad = LfpTransitionModel(soh=0.9)
    print(f"✗ LFP should have rejected SOH=0.9!")
except ValueError as e:
    print(f"✓ LFP correctly rejected SOH=0.9")
    print(f"  Error: {e}")

print("\n" + "=" * 60)
print("Testing NCA with SOH=1.0 (should work)...")
print("=" * 60)
try:
    nca = NcaTransitionModel(soh=1.0)
    print(f"✓ NCA created with SOH=1.0")
    print(f"  Chemistry: {nca.chemistry}")
    print(f"  SOH grid: {nca.soh_grid}")
except Exception as e:
    print(f"✗ NCA failed: {e}")

print("\n" + "=" * 60)
print("Testing NCA with SOH=0.85 (should fail)...")
print("=" * 60)
try:
    nca_bad = NcaTransitionModel(soh=0.85)
    print(f"✗ NCA should have rejected SOH=0.85!")
except ValueError as e:
    print(f"✓ NCA correctly rejected SOH=0.85")
    print(f"  Error: {e}")

print("\n" + "=" * 60)
print("Testing NMC with SOH=1.0 (should work)...")
print("=" * 60)
try:
    nmc_1 = NmcTransitionModel(soh=1.0)
    print(f"✓ NMC created with SOH=1.0")
    print(f"  Chemistry: {nmc_1.chemistry}")
    print(f"  SOH grid: {nmc_1.soh_grid}")
except Exception as e:
    print(f"✗ NMC failed: {e}")

print("\n" + "=" * 60)
print("Testing NMC with SOH=0.863 (should work)...")
print("=" * 60)
try:
    nmc_863 = NmcTransitionModel(soh=0.863)
    print(f"✓ NMC created with SOH=0.863")
    print(f"  Chemistry: {nmc_863.chemistry}")
    print(f"  SOH grid: {nmc_863.soh_grid}")
    print(f"  Clipped SOH for interpolation: {nmc_863.soh}")
except Exception as e:
    print(f"✗ NMC failed: {e}")

print("\n" + "=" * 60)
print("Testing NMC with SOH=0.799 (should work)...")
print("=" * 60)
try:
    nmc_799 = NmcTransitionModel(soh=0.799)
    print(f"✓ NMC created with SOH=0.799")
    print(f"  Chemistry: {nmc_799.chemistry}")
    print(f"  SOH grid: {nmc_799.soh_grid}")
except Exception as e:
    print(f"✗ NMC failed: {e}")

print("\n" + "=" * 60)
print("Testing NMC with SOH=0.5 (should work but be clipped to 0.799)...")
print("=" * 60)
try:
    nmc_clip = NmcTransitionModel(soh=0.5)
    print(f"✓ NMC created with SOH=0.5 (allowed, will be clipped during interpolation)")
    print(f"  Chemistry: {nmc_clip.chemistry}")
    print(f"  SOH grid: {nmc_clip.soh_grid}")
    print(f"  Model SOH value: {nmc_clip.soh}")
except Exception as e:
    print(f"✗ NMC failed: {e}")

print("\n" + "=" * 60)
print("All tests completed!")
print("=" * 60)
