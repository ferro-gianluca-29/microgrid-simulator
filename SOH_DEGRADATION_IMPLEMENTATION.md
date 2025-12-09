# SOH Degradation Implementation - Complete

## Summary

Successfully implemented **discrete threshold-based SOH degradation** for NMC batteries using experimental data from Excel curve.

## Implementation Details

### Core Changes

1. **File: `unipi_transition_model.py`**
   - Modified `_load_soh_curve()` method (~line 244):
     - Reads `NMC-SOHAh.xlsx` from data directory
     - Extracts Ah throughput thresholds → `self.soh_ah_thresholds`
     - Extracts SOH percentages → `self.soh_ah_values` (converted to fractions)
     - Creates `self.soh_ah_interpolator` as fallback for between-point values

   - Modified `_update_soh_from_ah()` method (~line 280):
     - **NEW LOGIC:** Discrete threshold-based updates instead of continuous interpolation
     - Accumulates `cumulative_ah_throughput += abs(delta_ah)`
     - Finds **highest threshold crossed** in the curve
     - Returns corresponding SOH value for that threshold
     - Maintains monotonicity: `soh_updated = min(soh_updated, self.last_soh)`

   - Updated `transition()` and `transition_without_update()`:
     - At `current_step==0`, NMC batteries reset to SOH=1.0 and `cumulative_ah_throughput=0`
     - Calls `_update_soh_from_ah()` to apply degradation
     - Saves SOH in transition history

   - Added SOH metric to `plot_transition_history()`:
     - New "soh" field in metric_specs with tab:brown color
     - Generates step-wise SOH degradation plot

### Excel Data Format

**File:** `src/pymgrid/modules/battery/transition_models/data/NMC-SOHAh.xlsx`

15 discrete points representing experimental NMC cell degradation:

```
Ah Throughput | SOH %
   29.3       | 95.5
   57.5       | 93.2
   85.3       | 91.9
   113.0      | 90.9
   140.5      | 90.4
   167.8      | 89.6
   195.0      | 89.5
   222.1      | 89.1
   249.1      | 88.8
   276.0      | 88.6
   554.8      | 84.5
   816.5      | 83.5
  1074.6      | 82.6
  1331.6      | 82.0
  1586.8      | 81.8
```

### Degradation Behavior

SOH progresses as a **step function**:

- **0 - 29.2 Ah:** SOH = 1.000 (100%)
- **29.3 - 57.4 Ah:** SOH = 0.955 (95.5%)
- **57.5 - 85.2 Ah:** SOH = 0.932 (93.2%)
- **85.3 - 112.9 Ah:** SOH = 0.919 (91.9%)
- ... (continues through all 15 points)
- **1586.8+ Ah:** SOH = 0.818 (81.8%)

Each threshold triggers an **instantaneous drop** to the new SOH value.

## Validation Results

✅ **All Discrete Threshold Tests Pass:**
- ✓ SOH=1.0 before first threshold (10 Ah)
- ✓ SOH drops to 0.955 exactly at 29.3 Ah
- ✓ SOH stays 0.955 until 57.5 Ah
- ✓ SOH continues stepping at each subsequent threshold
- ✓ SOH=0.82 at 1331.6 Ah threshold
- ✓ SOH=0.818 at final 1586.8 Ah threshold

✅ **Monotonicity Maintained:**
- SOH never increases (always ≤ last_soh)
- Proper handling of max/min constraints

✅ **Full Simulation Success:**
- NMC chemistry correctly detected
- SOH initialized to 1.0 at simulation start
- Transition history captured with SOH values
- Plots generated successfully with SOH metric

## Key Code Example

```python
# Load discrete curve from Excel
def _load_soh_curve(self):
    df = pd.read_excel(excel_path)
    self.soh_ah_thresholds = df.iloc[:, 0].values  # [29.3, 57.5, 85.3, ...]
    self.soh_ah_values = df.iloc[:, 1].values / 100.0  # [0.955, 0.932, 0.919, ...]

# Update SOH based on cumulative Ah throughput
def _update_soh_from_ah(self, current_charge_ah_per_cell, delta_ah):
    self.cumulative_ah_throughput += abs(delta_ah)
    
    soh_updated = 1.0  # Start at full health
    for i, ah_threshold in enumerate(self.soh_ah_thresholds):
        if self.cumulative_ah_throughput >= ah_threshold:
            soh_updated = self.soh_ah_values[i]
        else:
            break  # Stop at first unmet threshold
    
    # Ensure monotonic decrease
    soh_updated = min(soh_updated, self.last_soh)
    return soh_updated
```

## Testing

**Test Files Created:**
1. `test_soh_thresholds.py` - Basic threshold crossing tests ✅
2. `test_verify_soh_discrete.py` - Comprehensive discrete logic validation ✅
3. `test_soh_full_sim.py` - End-to-end simulation test ✅

**Test Results Summary:**
- 10/10 discrete threshold points validated
- Monotonicity constraint verified
- Full simulation runs without errors
- Plots generated with SOH metric included

## Chemistry-Specific Behavior

- **LFP/NCA:** SOH fixed at 1.0 (raises ValueError if configured otherwise)
- **NMC:** SOH degrades according to experimental curve
  - Resets to 1.0 at simulation start (current_step==0)
  - Accumulates Ah throughput from all transitions
  - Steps down at curve thresholds

## Configuration

**params.yml:**
```yaml
battery:
  state_of_health: 1.0  # Auto-resets for NMC at simulation start
  chemistry: NMC         # Selects NMC battery model with SOH curve
```

## Status: ✅ COMPLETE

- ✅ Excel curve loading with discrete points
- ✅ Cumulative Ah throughput tracking (absolute value)
- ✅ Threshold-based SOH updates (step function)
- ✅ Monotonicity enforcement
- ✅ Chemistry-specific constraints maintained
- ✅ Transition history logging with SOH values
- ✅ Plot generation with SOH metric
- ✅ Comprehensive validation tests
- ✅ Full simulation verification

The discrete threshold-based SOH degradation system is fully implemented, tested, and validated.
