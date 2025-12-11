import os
import sys
import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, os.getcwd())
from src.pymgrid.modules.battery.transition_models.unipi_transition_model import UnipiChemistryTransitionModel

OUT = os.getcwd()

def main():
    m = UnipiChemistryTransitionModel('parameters_cell_NMC.mat', reference_cell_capacity_ah=2.9, nominal_cell_voltage=3.7)
    # Build cumulative Ah array from 0 to last threshold * 1.05
    if m.soh_ah_interpolator is None:
        raise RuntimeError('SOH Ah interpolator not loaded; check that chemistry==NMC and excel file present')

    thresholds = m.soh_ah_thresholds
    last = thresholds[-1] if len(thresholds) > 0 else 1.0
    ahs = np.linspace(0.0, last * 1.05, 200)

    # Compute SOH progression matching _update_soh_from_ah logic
    soh_vals = np.zeros_like(ahs)
    first_th = thresholds[0]
    for i, a in enumerate(ahs):
        if a <= 0:
            soh = 1.0
        elif a < first_th:
            ratio = a / first_th
            soh = 1.0 + ratio * (m.soh_ah_values[0] - 1.0)
        else:
            soh = float(m.soh_ah_interpolator(a))
        soh_vals[i] = soh

    # Sample Voc/R0 at a few SOCs
    socs = [0.1, 0.5, 0.9]
    Voc = np.zeros((len(socs), len(ahs)))
    R0 = np.zeros_like(Voc)
    for j, soh in enumerate(soh_vals):
        for i, soc in enumerate(socs):
            voc, r0 = m._interp_voc_r0(float(soc), 20.0, float(soh))
            Voc[i, j] = voc
            R0[i, j] = r0

    # Plot Voc vs cumulative Ah for each SOC
    plt.figure(figsize=(8,5))
    for idx, soc in enumerate(socs):
        plt.plot(ahs, Voc[idx,:], label=f'SOC={soc:.2f}')
    plt.xlabel('Cumulative Ah per cell')
    plt.ylabel('Voc (V)')
    plt.title('Voc vs cumulative Ah (SOH progression) at T=20C')
    plt.legend()
    out1 = os.path.join(OUT, 'voc_vs_ah_progression.png')
    plt.tight_layout()
    plt.savefig(out1, dpi=150)
    plt.close()

    # Plot R0 vs cumulative Ah
    plt.figure(figsize=(8,5))
    for idx, soc in enumerate(socs):
        plt.plot(ahs, R0[idx,:], label=f'SOC={soc:.2f}')
    plt.xlabel('Cumulative Ah per cell')
    plt.ylabel('R0 (Ohm)')
    plt.title('R0 vs cumulative Ah (SOH progression) at T=20C')
    plt.legend()
    out2 = os.path.join(OUT, 'r0_vs_ah_progression.png')
    plt.tight_layout()
    plt.savefig(out2, dpi=150)
    plt.close()

    # Voc vs SOH lines
    plt.figure(figsize=(8,5))
    for idx, soc in enumerate(socs):
        plt.plot(soh_vals, Voc[idx,:], label=f'SOC={soc:.2f}')
    plt.xlabel('SOH')
    plt.ylabel('Voc (V)')
    plt.title('Voc vs SOH at T=20C')
    plt.legend()
    out3 = os.path.join(OUT, 'voc_vs_soh.png')
    plt.tight_layout()
    plt.savefig(out3, dpi=150)
    plt.close()

    # R0 vs SOH lines
    plt.figure(figsize=(8,5))
    for idx, soc in enumerate(socs):
        plt.plot(soh_vals, R0[idx,:], label=f'SOC={soc:.2f}')
    plt.xlabel('SOH')
    plt.ylabel('R0 (Ohm)')
    plt.title('R0 vs SOH at T=20C')
    plt.legend()
    out4 = os.path.join(OUT, 'r0_vs_soh.png')
    plt.tight_layout()
    plt.savefig(out4, dpi=150)
    plt.close()

    print('Saved:', out1)
    print('Saved:', out2)
    print('Saved:', out3)
    print('Saved:', out4)

if __name__ == '__main__':
    main()
