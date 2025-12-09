#!/usr/bin/env python3
"""Test that SOH always starts from 1.0 in transition method."""

import sys
sys.path.insert(0, 'src')

from pymgrid.modules.battery.transition_models.nmc_transition_model import NmcTransitionModel
import numpy as np

print("=" * 70)
print("Testing transition method with SOH reset at step 0")
print("=" * 70)

# Create NMC model with initial SOH not equal to 1.0 (simulate coming from params)
nmc = NmcTransitionModel(soh=0.85, np_batt=270)

print(f"\nInitial state (before transition):")
print(f"  self.soh: {nmc.soh}")
print(f"  self.last_soh: {nmc.last_soh}")
print(f"  chemistry: {nmc.chemistry}")

# Simulate first transition step
state_dict = {'soc': 0.5, 'temperature_c': 25.0, 'current_charge': 20.0}

# Call transition at step 0
print(f"\nCalling transition at current_step=0...")
result = nmc.transition(
    external_energy_change=0.5,
    min_capacity=5.0,
    max_capacity=51.2,
    max_charge=20.0,
    max_discharge=20.0,
    efficiency=0.95,
    battery_cost_cycle=0.0,
    current_step=0,
    state_dict=state_dict,
    state_update=True
)

print(f"\nState after transition step 0:")
print(f"  self.soh: {nmc.soh}")
print(f"  self.last_soh: {nmc.last_soh}")
print(f"  Transition history entries: {len(nmc._transition_history)}")
if nmc._transition_history:
    print(f"  SOH in history: {nmc._transition_history[0]['soh']}")

print("\n" + "=" * 70)
if nmc.soh == 1.0 and nmc._transition_history[0]['soh'] == 1.0:
    print("✓ SOH correctly reset to 1.0 at step 0!")
else:
    print(f"✗ SOH not reset correctly! Expected 1.0, got {nmc.soh}")
print("=" * 70)
