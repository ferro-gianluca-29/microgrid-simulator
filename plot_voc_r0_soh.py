import os
import sys
import numpy as np
import matplotlib.pyplot as plt

# Ensure project root on path
sys.path.insert(0, os.getcwd())

from src.pymgrid.modules.battery.transition_models.unipi_transition_model import UnipiChemistryTransitionModel

OUTPUT_DIR = os.getcwd()

def main():
    m = UnipiChemistryTransitionModel('parameters_cell_NMC.mat', reference_cell_capacity_ah=2.9, nominal_cell_voltage=3.7)
    soc_grid = np.array(m.soc_grid)
    soh_grid = np.array(m.soh_grid)
    temp = 20.0

    # Build matrices
    Voc = np.zeros((len(soh_grid), len(soc_grid)))
    R0 = np.zeros_like(Voc)

    for i, soh in enumerate(soh_grid):
        for j, soc in enumerate(soc_grid):
            voc, r0 = m._interp_voc_r0(float(soc), float(temp), float(soh))
            Voc[i, j] = voc
            R0[i, j] = r0

    # Plot heatmaps: x = SOC, y = SOH
    fig, ax = plt.subplots(figsize=(8, 4))
    im = ax.imshow(Voc, aspect='auto', origin='lower', extent=(soc_grid[0], soc_grid[-1], soh_grid[0], soh_grid[-1]))
    ax.set_xlabel('SOC')
    ax.set_ylabel('SOH')
    ax.set_title(f'Voc (V) at T={temp}C')
    fig.colorbar(im, ax=ax, label='Voc (V)')
    out_voc = os.path.join(OUTPUT_DIR, 'voc_heatmap_soc_soh_20C.png')
    fig.tight_layout()
    fig.savefig(out_voc, dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4))
    im = ax.imshow(R0, aspect='auto', origin='lower', extent=(soc_grid[0], soc_grid[-1], soh_grid[0], soh_grid[-1]))
    ax.set_xlabel('SOC')
    ax.set_ylabel('SOH')
    ax.set_title(f'R0 (Ohm) at T={temp}C')
    fig.colorbar(im, ax=ax, label='R0 (Ohm)')
    out_r0 = os.path.join(OUTPUT_DIR, 'r0_heatmap_soc_soh_20C.png')
    fig.tight_layout()
    fig.savefig(out_r0, dpi=150)
    plt.close(fig)

    # Line plots Voc vs SOC for each SOH
    fig, ax = plt.subplots(figsize=(8, 5))
    for i, soh in enumerate(soh_grid):
        ax.plot(soc_grid, Voc[i, :], label=f'SOH={soh:.3f}')
    ax.set_xlabel('SOC')
    ax.set_ylabel('Voc (V)')
    ax.set_title(f'Voc vs SOC at T={temp}C')
    ax.legend(loc='best')
    fig.tight_layout()
    out_voc_lines = os.path.join(OUTPUT_DIR, 'voc_vs_soc_by_soh_20C.png')
    fig.savefig(out_voc_lines, dpi=150)
    plt.close(fig)

    # Line plots R0 vs SOC for each SOH
    fig, ax = plt.subplots(figsize=(8, 5))
    for i, soh in enumerate(soh_grid):
        ax.plot(soc_grid, R0[i, :], label=f'SOH={soh:.3f}')
    ax.set_xlabel('SOC')
    ax.set_ylabel('R0 (Ohm)')
    ax.set_title(f'R0 vs SOC at T={temp}C')
    ax.legend(loc='best')
    fig.tight_layout()
    out_r0_lines = os.path.join(OUTPUT_DIR, 'r0_vs_soc_by_soh_20C.png')
    fig.savefig(out_r0_lines, dpi=150)
    plt.close(fig)

    print('Saved:', out_voc)
    print('Saved:', out_r0)
    print('Saved:', out_voc_lines)
    print('Saved:', out_r0_lines)

if __name__ == '__main__':
    main()
