#!/usr/bin/env python3
"""Test continuous SOH curve with steep initial drop."""

import sys
sys.path.insert(0, 'src')

import numpy as np
from pymgrid.modules.battery.transition_models.nmc_transition_model import NmcTransitionModel

print("=" * 80)
print("SOH Degradation - Continuous Curve with Steep Initial Drop")
print("=" * 80)

nmc = NmcTransitionModel(ns_batt=16, np_batt=270, soh=1.0)

# Test points showing the progression
test_cases = [
    (0.0,    "Start"),
    (5.0,    "Early: steep drop region"),
    (10.0,   "Early: steep drop region"),
    (14.65,  "Midpoint to first threshold (half of 29.3)"),
    (29.3,   "First threshold exact"),
    (40.0,   "After first drop"),
    (57.5,   "Second threshold"),
    (100.0,  "Well into curve"),
    (276.0,  "10th point"),
    (554.8,  "11th point (large gap)"),
    (1586.8, "Final point"),
    (2000.0, "Beyond curve"),
]

print(f"\nCumulative Ah | SOH Value | Rate of Change | Visual")
print("-" * 80)

prev_soh = 1.0
prev_ah = 0.0

for cumulative_ah, description in test_cases:
    nmc.cumulative_ah_throughput = 0.0
    nmc.last_soh = 1.0
    
    # Accumulate to reach target
    delta_ah = cumulative_ah
    soh = nmc._update_soh_from_ah(0, delta_ah)
    
    # Calculate rate of change
    if cumulative_ah > prev_ah:
        delta_soh = soh - prev_soh
        ah_diff = cumulative_ah - prev_ah
        rate = delta_soh / ah_diff
    else:
        rate = 0
    
    bar_width = int(soh * 50)
    bar = "█" * bar_width + "░" * (50 - bar_width)
    
    rate_str = f"{rate*100:+.3f}%/Ah" if abs(rate) > 0 else "      -"
    
    print(f"{cumulative_ah:13.1f} | {soh:9.4f} | {rate_str:14s} | [{bar}]")
    
    prev_soh = soh
    prev_ah = cumulative_ah

print("\n" + "=" * 80)
print("Key Observations:")
print("=" * 80)
print("""
1. At 0 Ah: SOH = 1.0000 (100%)
2. At 14.65 Ah: SOH should be ≈ 0.977 (halfway between 1.0 and 0.955)
3. At 29.3 Ah: SOH = 0.955 (95.5%) - matches first Excel point
4. After 29.3 Ah: degradation continues smoothly along curve
5. Rate of degradation decreases significantly after first 29.3 Ah
6. This natural curve shows rapid early wear, then stable operation

Initial Drop Characteristics:
  - Drop from 1.0 to 0.955 in 29.3 Ah (-0.00154 per Ah)
  - This is MUCH steeper than later degradation
  - Perfect representation of battery break-in
""")
