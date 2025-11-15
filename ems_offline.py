import os
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import pandas as pd



from microgrid_simulator import MicrogridSimulator
from tools import load_config, compute_offline_tariff_vectors
from EMS import Rule_Based_EMS

from pandasgui import show


###### LOAD CONFIGURATION FROM YAML 

config = load_config()              # Carica configurazione EMS da params.yml

price_config = config['price_bands']               # Configurazione fasce prezzi
simulation_steps = config['steps']                 # Numero di step di simulazione da eseguire

timezone_str = config['timezone']   # Configura timezone per timestamp 

##########  TIME SERIES DATASET   ###############

time_series = pd.read_csv('./data/processed_data_661_formatted.csv')
time_series = time_series[["datetime","solar", "load"]].interpolate()   # interpolate() for removing NaNs
time_series["datetime"] = pd.to_datetime(time_series["datetime"], utc=True, errors="coerce")


pv_time_series = time_series['solar']
pv_time_series = pv_time_series.clip(lower=0)

load_time_series = time_series['load']

timestamps = time_series['datetime']

price_buy_time_series, price_sell_time_series = compute_offline_tariff_vectors(
    ts_series=timestamps,
    local_timezone=timezone_str,
    price_config=price_config
)

# time series containing values for cost of carbon dioxide emissions (not accounted for this task, so put to zero)
emissions_time_series = np.zeros(len(price_buy_time_series))

grid_time_series = np.stack([price_buy_time_series, price_sell_time_series, emissions_time_series], axis=1)


############################################


###### INSTANTIATE MICROGRID SIMULATOR WITH MODULES


print("Inizializzazione microgrid...")

simulator = MicrogridSimulator(
    config_path='params.yml',
    online=False,
    load_time_series = load_time_series, 
    pv_time_series = pv_time_series, 
    grid_time_series = grid_time_series
)

microgrid = simulator.build_microgrid()  # Costruisce la microgrid dai parametri nel file di configurazione.

load_module = microgrid.modules['load'][0]         # Modulo load
pv_module = microgrid.modules['pv'][0]             # Modulo PV

microgrid.reset()  # Porta la microgrid in uno stato noto prima di iniziare la simulazione.


###### INSTANTIATE ENERGY MANAGEMENT SYSTEM AND RUN SIMULATION

rule_based_EMS = Rule_Based_EMS(microgrid)


for step in range(1, simulation_steps + 1):         # Loop principale per il numero di step specificato
 
    load_kwh = load_module.current_load
    pv_kwh = pv_module.current_renewable

    e_batt, e_grid = rule_based_EMS.control(                                # Calcola controllo basato su regole 
        load_kwh = load_kwh, 
        pv_kwh = pv_kwh,       
        )
    
    control = {"battery": e_batt, "grid": e_grid}   # Prepara dizionario controllo per report
    obs, reward, done, info = microgrid.step(control, normalized=False)

microgrid_df, log = simulator.get_simulation_log(microgrid)

log.to_csv("microgrid_log.csv", index=True)

microgrid_df['pv_prod'] = time_series['solar'].iloc[:2]
microgrid_df['consumption'] = time_series['load'].iloc[:2]


show(time_series=time_series, microgrid_df=microgrid_df)
