#!/usr/bin/env python3
"""Visual demonstration of SOH degradation as discrete steps."""

import sys
sys.path.insert(0, 'src')

import numpy as np
from pymgrid.modules.battery.transition_models.nmc_transition_model import NmcTransitionModel

print("=" * 80)
print("SOH Degradation Curve - Discrete Step Function")
print("=" * 80)

nmc = NmcTransitionModel(ns_batt=16, np_batt=270, soh=1.0)

# Simulate accumulating Ah and show SOH at key points
cumulative_points = []
soh_values = []

# Create test points
test_ahs = list(np.linspace(0, 100, 101))  # First 100 Ah
test_ahs += list(np.linspace(100, 300, 51)[1:])  # Up to 300 Ah
test_ahs += [554.8, 560, 816.5, 820, 1074.6, 1080, 1331.6, 1340, 1586.8, 1590]  # Around thresholds

for target_ah in sorted(set(test_ahs)):
    nmc.cumulative_ah_throughput = target_ah
    nmc.last_soh = 1.0  # Allow any SOH for visualization
    soh = nmc._update_soh_from_ah(0, 0)
    cumulative_points.append(target_ah)
    soh_values.append(soh)

# Pretty print the curve
print(f"\nAh Throughput | SOH Value | Visual Representation")
print("-" * 80)

prev_soh = 1.0
for ah, soh in zip(cumulative_points, soh_values):
    if abs(soh - prev_soh) > 0.0001:
        marker = "→ STEP DOWN"
        prev_soh = soh
    else:
        marker = ""
    
    bar_width = int(soh * 50)
    bar = "█" * bar_width + "░" * (50 - bar_width)
    
    print(f"{ah:13.1f} | {soh:9.4f} | [{bar}] {soh*100:.1f}% {marker}")

print("\n" + "=" * 80)
print("Observations:")
print("=" * 80)
print(f"""
1. SOH starts at 1.0000 and remains constant until first threshold
2. At each threshold Ah value, SOH instantly drops to the next level
3. Between thresholds, SOH remains completely flat (no degradation)
4. This represents experimental battery behavior captured in discrete measurements

Threshold Overview:
  - Curve has {len(nmc.soh_ah_thresholds)} discrete measurement points
  - First step: 29.3 Ah → drops to {nmc.soh_ah_values[0]:.4f}
  - Last step: 1586.8 Ah → drops to {nmc.soh_ah_values[-1]:.4f}
  - Total degradation: {(1.0 - nmc.soh_ah_values[-1])*100:.1f}% over 1586.8 Ah
""")

print("=" * 80)
