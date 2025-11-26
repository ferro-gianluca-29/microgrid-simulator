# -*- coding: utf-8 -*-


import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

"""
load the battery type to be simulated
"""
#choose one
from ESS_package_UNIPI.ESS_UNIPI_NMC import ESS  # NMC battery model
#from ESS_package_UNIPI.ESS_UNIPI_NCA import ESS  # NCA battery model
#from ESS_package_UNIPI.ESS_UNIPI_LFP import ESS  # LFP battery model
"""
insert parameter for ESS simulation test
"""
delta_t = 0.25  # simulation step time in h
simulation_hours = 10  # suration of whole simulation in h
time_steps = int(simulation_hours / delta_t)  # Numero totale di passi temporali
# creation of simple test power profile (rectangular discharge-charge constant power)
# battery power is considered positive when discharging
half_steps = time_steps // 2  
power_profile = np.concatenate([
    np.full(half_steps, 5),  # First constant power discharging step for half of the simulation (5kW)
    np.full(time_steps - half_steps, -5)  # Second constant power charging step for half of the simulation (-5kW)
])

# battery parametrization
ess_params = {
    "model": "ESS_UNIPI",
    "p_S_max": 50, # Maximum charging/discharging power in kW
    "a": 0.1, # Empirical cost model parameter
    "b": 0.2, # Empirical cost model parameter
    "B": 1, # Empirical cost model parameter
    "SoC_min": 0.2, # Minimum State of Charge value allowed 
    "SoC_max": 1, # Maximum State of Charge value allowed
    "C_n": 30, # Nominal value of the capacity of the single cell composing the battery in Ah
    "eta_inverter": 0.9, # inverter efficiency, considered constant
    "Ns_batt": 100, # Number of single cells connected in series to create a battery segment
    "Np_batt": 10,  # Number of segments connected in parallel to create the whole battery
    "SoC_0": 0.5, # Initial State of Charge of the battery (fraction of nominal capacity)
    "T": 20, # Battery working temperature (valid values: between 20 and 40 °C)
}

"""
creation of ESS class instance and initialization
"""
ess_model = ESS(**ess_params)


"""
Results list to be collected
"""
results = {
    "time": [],
    "SoE": [],
    "SoC": [],
    "voltage": [],
    "current": [],
    "power_profile": [],
    "excess": [],
    "lack": [],
    "eta": [],
    "C_b_k": []
}

"""
Simulation
"""
# Initial state definition
SoE_prev = ess_model.SoE
SoC_prev = ess_model.SoC
V_prev = ess_model.Voc_start  # Usa Voc inizialmente

# Simulation loop
for t, p_GL_S in enumerate(power_profile):
    current_time = t * delta_t
    
    # Update variables at each iteration
    I_batt = ess_model.update_I_batt(p_GL_S, V_prev)
    V_batt = ess_model.update_V_batt(I_batt)
    SoC = ess_model.update_SoC(I_batt, delta_t)
    excess = ess_model.calculate_excess(I_batt, V_batt, delta_t)
    lack = ess_model.calculate_lack(I_batt, V_batt, delta_t)
    SoE = ess_model.update_SoE(I_batt, delta_t)
    eta = ess_model.calculate_eta(I_batt, V_batt, delta_t)
    C_b_k = ess_model.get_wear_cost(SoC_prev, p_GL_S, delta_t)
    
    # Collect results
    results["time"].append(current_time)
    results["SoE"].append(SoE)
    results["SoC"].append(SoC)
    results["voltage"].append(V_batt)
    results["current"].append(I_batt)
    results["power_profile"].append(p_GL_S)
    results["excess"].append(excess)
    results["lack"].append(lack)
    results["eta"].append(eta)
    results["C_b_k"].append(C_b_k)
    
    
    # Update new state variables
    V_prev = V_batt
    SoE_prev = SoE
    SoC_prev = SoC

"""
for plotting
"""

# dataframe creation
df_results = pd.DataFrame(results)
# dataframe visualization
print(df_results)

# Results plots
plt.figure(figsize=(12, 8))

# Power profile
plt.subplot(3, 1, 1)
plt.plot(results["time"], results["power_profile"], label="Power Profile", color="blue", linestyle="--")
plt.title("Power Profile Over Time")
plt.xlabel("Time (hours)")
plt.ylabel("Power (kW)")
plt.grid()
plt.legend()

# SOC profile
plt.subplot(3, 1, 2)
plt.plot(results["time"], results["SoC"], label="State of Charge (SoC)", color="orange")
plt.title("State of Charge (SoC) Over Time")
plt.xlabel("Time (hours)")
plt.ylabel("SoC (fraction of capacity)")
plt.grid()
plt.legend()

# Voltage profile
plt.subplot(3, 1, 3)
plt.plot(results["time"], results["voltage"], label="Battery Voltage", color="red")
plt.title("Battery Voltage Over Time")
plt.xlabel("Time (hours)")
plt.ylabel("Voltage (V)")
plt.grid()
plt.legend()


plt.tight_layout()
plt.show()
