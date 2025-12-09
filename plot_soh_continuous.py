#!/usr/bin/env python3
"""Visualize continuous SOH degradation curve with steep initial drop."""

import sys
sys.path.insert(0, 'src')

import numpy as np
import matplotlib.pyplot as plt
from pymgrid.modules.battery.transition_models.nmc_transition_model import NmcTransitionModel

print("=" * 80)
print("Plotting Continuous SOH Degradation Curve")
print("=" * 80)

nmc = NmcTransitionModel(ns_batt=16, np_batt=270, soh=1.0)

# Generate smooth curve from 0 to 2000 Ah
ah_values = np.linspace(0, 2000, 1000)
soh_values = []

for ah in ah_values:
    nmc.cumulative_ah_throughput = 0.0
    nmc.last_soh = 1.0
    soh = nmc._update_soh_from_ah(0, ah)
    soh_values.append(soh)

# Plot
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

# Full curve
ax1.plot(ah_values, soh_values, 'b-', linewidth=2, label='Continuous SOH Curve')
ax1.scatter(nmc.soh_ah_thresholds, nmc.soh_ah_values, color='red', s=50, 
            label='Excel Data Points', zorder=5)
ax1.axhline(y=1.0, color='gray', linestyle='--', alpha=0.5)
ax1.axvline(x=29.3, color='orange', linestyle='--', alpha=0.7, label='First threshold (29.3 Ah)')
ax1.grid(True, alpha=0.3)
ax1.set_xlabel('Cumulative Ah Throughput', fontsize=11)
ax1.set_ylabel('State of Health (SOH)', fontsize=11)
ax1.set_title('Full SOH Degradation Curve', fontsize=12, fontweight='bold')
ax1.legend(loc='best')
ax1.set_ylim([0.7, 1.02])

# Zoom on initial region
ah_zoom = ah_values[ah_values <= 150]
soh_zoom = [soh for ah, soh in zip(ah_values, soh_values) if ah <= 150]

ax2.plot(ah_zoom, soh_zoom, 'b-', linewidth=2.5, label='Continuous SOH')
ax2.scatter(nmc.soh_ah_thresholds[nmc.soh_ah_thresholds <= 150], 
            nmc.soh_ah_values[nmc.soh_ah_thresholds <= 150], 
            color='red', s=80, label='Excel Points', zorder=5)

# Annotate key points
key_points = [(0, 1.0), (14.65, 0.9775), (29.3, 0.955), (57.5, 0.932)]
for ah, soh in key_points:
    ax2.annotate(f'{soh:.4f}', xy=(ah, soh), xytext=(ah+5, soh+0.005),
                fontsize=9, ha='left')
    ax2.plot(ah, soh, 'go', markersize=8, alpha=0.6)

ax2.axvline(x=29.3, color='orange', linestyle='--', alpha=0.7, linewidth=1.5)
ax2.grid(True, alpha=0.3)
ax2.set_xlabel('Cumulative Ah Throughput', fontsize=11)
ax2.set_ylabel('State of Health (SOH)', fontsize=11)
ax2.set_title('Initial Drop Region (Steep Degradation)', fontsize=12, fontweight='bold')
ax2.legend(loc='best')
ax2.set_xlim([-5, 155])
ax2.set_ylim([0.93, 1.01])

plt.tight_layout()
plt.savefig('soh_continuous_curve.png', dpi=150, bbox_inches='tight')
print("\n✓ Plot saved to: soh_continuous_curve.png")

# Print analysis
print("\n" + "=" * 80)
print("Curve Analysis:")
print("=" * 80)

print("\nInitial Drop Phase (0-29.3 Ah):")
print(f"  SOH at 0 Ah: {1.0:.4f}")
print(f"  SOH at 29.3 Ah: {nmc.soh_ah_values[0]:.4f}")
print(f"  Total drop: {(1.0 - nmc.soh_ah_values[0])*100:.2f}%")
print(f"  Rate: {(nmc.soh_ah_values[0] - 1.0) / 29.3 * 100:.4f}% per Ah (STEEP)")

print("\nProgressive Degradation (29.3-300 Ah):")
nmc.cumulative_ah_throughput = 29.3
nmc.last_soh = 1.0
soh_at_30 = nmc._update_soh_from_ah(0, 0.7)

nmc.cumulative_ah_throughput = 100
nmc.last_soh = 1.0
soh_at_100 = nmc._update_soh_from_ah(0, 0)

print(f"  SOH at 29.3 Ah: {soh_at_30:.4f}")
print(f"  SOH at 100 Ah: {soh_at_100:.4f}")
print(f"  Degradation 29.3-100 Ah: {(soh_at_30 - soh_at_100)*100:.2f}%")
print(f"  Rate: {(soh_at_30 - soh_at_100) / (100 - 29.3) * 100:.4f}% per Ah (MODERATE)")

print("\nLong-term Degradation (300+ Ah):")
nmc.cumulative_ah_throughput = 300
nmc.last_soh = 1.0
soh_at_300 = nmc._update_soh_from_ah(0, 0)

nmc.cumulative_ah_throughput = 1000
nmc.last_soh = 1.0
soh_at_1000 = nmc._update_soh_from_ah(0, 0)

print(f"  SOH at 300 Ah: {soh_at_300:.4f}")
print(f"  SOH at 1000 Ah: {soh_at_1000:.4f}")
print(f"  Degradation 300-1000 Ah: {(soh_at_300 - soh_at_1000)*100:.2f}%")
print(f"  Rate: {(soh_at_300 - soh_at_1000) / (1000 - 300) * 100:.4f}% per Ah (SLOW)")

print("\n" + "=" * 80)
