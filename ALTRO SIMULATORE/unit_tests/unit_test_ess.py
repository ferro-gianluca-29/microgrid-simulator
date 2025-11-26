import MG
import os
import json
import glob
import numpy as np
import matplotlib.pyplot as plt


# Declare constants
PV_MAX = 3  # kW
PL_MAX = 3  # kW

# Set the seed for test reproducibility
np.random.seed = 10

# delete previous results_mg from the specific folder
folder_path = 'results_ess'
files = glob.glob(os.path.join(folder_path, '*'))
for file in files:
    if os.path.isfile(file):
        os.remove(file)

# Load data
file_path = os.path.abspath('./data/data.json')
with open(file_path, 'r') as file:
    data = json.load(file)

# Create the test dataset
pvs = np.random.uniform(10) * PV_MAX
pls = np.random.uniform(10) * PL_MAX
dataset = []
dataset.append(pvs)
dataset.append(pls)

# Siimulate the mg with different ESSs
battery_models = ['linear', 'empirical', 'lfp', 'nca', 'nmc']
for b_m in battery_models:

    # Instantiate the mg
    mg = MG(data['economic_params'], data['simulation'], data['architecture']['mg0'], b_m)
    mg.simulate(dataset, 1)
    soes, costs, p_fls = mg.get_ess_insights()
    tot_cost = sum(costs)
    res = {
        "soes": soes,
        "costs": costs,
        "p_fls": p_fls,
        "tot_cost": tot_cost
    }

    # save results
    file_path = os.path.join(folder_path, f'res_{b_m}.json')
    with open(file_path, 'w') as file:
        json.dump(res, file)

    # Plot SoE
    plt.figure()
    plt.plot(soes, label=f"{b_m} SoE")
    plt.xlabel("Time Step")
    plt.ylabel("SoE")
    plt.title(f"{b_m} SoE")
    plt.legend()
    plt.grid(True)
    plt.savefig(os.path.join(folder_path, f"{b_m}_soes.png"))
    plt.close()

    # Plot ESS costs
    plt.figure()
    plt.plot(costs, label=f"{b_m} Costs", color='r')
    plt.xlabel("Time Step")
    plt.ylabel("Costs")
    plt.title(f"{b_m} Costs")
    plt.legend()
    plt.grid(True)
    plt.savefig(os.path.join(folder_path, f"{b_m}_costs.png"))
    plt.close()

    # Plot ESS power flows
    plt.figure()
    plt.plot(p_fls, label=f"{b_m} pow", color='g')
    plt.xlabel("Time Step")
    plt.ylabel("P")
    plt.title(f"{b_m} - Power flows")
    plt.legend()
    plt.grid(True)
    plt.savefig(os.path.join(folder_path, f"{b_m}_p_fls.png"))
    plt.close()






