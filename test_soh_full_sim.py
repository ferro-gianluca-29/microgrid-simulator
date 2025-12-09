#!/usr/bin/env python3
"""Test SOH degradation curve in full simulation context."""

import sys
sys.path.insert(0, 'src')

import yaml
from pymgrid.microgrid import Microgrid
from pymgrid.modules.battery.transition_models.nmc_transition_model import NmcTransitionModel

# Load params
with open('params.yml') as f:
    params = yaml.safe_load(f)

print("=" * 70)
print("Testing SOH Degradation in Full Simulation")
print("=" * 70)

# Create transition model directly
battery = NmcTransitionModel(
    ns_batt=16,
    np_batt=270,
    soh=float(params['battery']['state_of_health'])
)

# Create transition model directly
battery = NmcTransitionModel(
    ns_batt=16,
    np_batt=270,
    soh=float(params['battery']['state_of_health'])
)

print(f"\nInitial SOH: {battery.soh:.4f}")
print(f"Cumulative Ah at start: {battery.cumulative_ah_throughput:.4f}")

# Simulate with known discharge patterns
print("\nSimulation steps:")
print("Step | Current(A) | Duration(s) | Delta Ah | Cumulative Ah | SOH")
print("-" * 70)

for step in range(200):
    # Varying discharge pattern to eventually hit thresholds
    if step < 50:
        current_a = 10  # 10A discharge
    elif step < 100:
        current_a = 15  # 15A discharge
    elif step < 150:
        current_a = 20  # 20A discharge
    else:
        current_a = 25  # 25A discharge
    
    delta_t = 60  # 60 seconds per step
    
    # Run transition
    battery.transition(
        current_a=current_a,
        delta_t=delta_t,
        power_generated=0,
        power_load=0,
        soc=None,
        status_before="discharging",
        status_after="discharging"
    )
    
    # Get delta_ah
    delta_ah = abs(current_a * delta_t / 3600)
    
    # Print every 10 steps or when SOH changes
    if step % 10 == 0 or (battery.transition_history and step > 0 and 
        battery.transition_history[-1]['soh'] != battery.transition_history[-2]['soh']):
        if battery.transition_history:
            soh_from_hist = battery.transition_history[-1]['soh']
        else:
            soh_from_hist = battery.soh
            
        print(f"{step:4d} | {current_a:10.1f} | {delta_t:11.0f} | {delta_ah:8.4f} | {battery.cumulative_ah_throughput:13.4f} | {soh_from_hist:6.4f}")

print("\n" + "=" * 70)
print("SOH Threshold Crossings Detected:")
print("=" * 70)

prev_soh = 1.0
for i, hist in enumerate(battery.transition_history):
    current_soh = hist['soh']
    if abs(current_soh - prev_soh) > 0.0001:
        ah = battery.cumulative_ah_throughput  # Approximate from step
        print(f"Step {i}: SOH {prev_soh:.4f} → {current_soh:.4f}")
        prev_soh = current_soh

print(f"\nFinal State:")
print(f"  Cumulative Ah: {battery.cumulative_ah_throughput:.2f}")
print(f"  Final SOH: {battery.soh:.4f}")
print(f"  History entries: {len(battery.transition_history)}")
