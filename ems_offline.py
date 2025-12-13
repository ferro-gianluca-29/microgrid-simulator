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
from pandas import MultiIndex



from microgrid_simulator import MicrogridSimulator
from tools import load_config, compute_offline_tariff_vectors, plot_results, add_module_columns
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
price_buy_time_series = price_buy_time_series
price_sell_time_series = price_sell_time_series

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

microgrid = simulator.build_microgrid()  # Costruisce la microgrid con i moduli specificati nel file di configurazione 

load_module = microgrid.modules['load'][0]         # Modulo load
pv_module = microgrid.modules['pv'][0]             # Modulo PV

microgrid.reset()  # Porta la microgrid in uno stato noto prima di iniziare la simulazione.

###### INSTANTIATE ENERGY MANAGEMENT SYSTEM AND RUN SIMULATION

rule_based_EMS = Rule_Based_EMS(microgrid)       # Crea istanza EMS basato su regole per la microgrid


for step in range(1, simulation_steps + 1):         # Loop principale per il numero di step specificato

    load_kwh = load_module.current_load
    pv_kwh = pv_module.current_renewable

    e_batt, e_grid = rule_based_EMS.control(                                # Calcola controllo basato su regole 
        load_kwh = load_kwh, 
        pv_kwh = pv_kwh,       
        )

    control = {"battery": e_batt, "grid": e_grid}   # Prepara il dizionario di controllo per lo step corrente

    obs, reward, done, info = microgrid.step(control, normalized=False)


microgrid_df, log = simulator.get_simulation_log(microgrid)     # Ottiene il log della simulazione come DataFrame pandas con tutti gli step

log.to_csv("microgrid_log.csv", index=True)                     # Salva il log della simulazione su file CSV

battery_module = microgrid.battery[0]                           # Ottiene il modulo batteria dalla microgrid
transition_model = battery_module.battery_transition_model      # Ottiene il modello di transizione della batteria

history = transition_model.get_transition_history()                 # Ottiene la cronologia delle transizioni della batteria
#eta_dynamic = [entry['eta_dynamic'] for entry in history]           # Estrae l'efficienza dinamica dalla cronologia


additional_columns = {
    ('datetime', 0, 'timestamp'): time_series['datetime'].to_numpy()[:len(microgrid_df)],
    ('pv', 0, 'pv_prod_input'): time_series['solar'].to_numpy()[:len(microgrid_df)],             # Aggiunge la produzione PV in input come colonna al DataFrame della microgrid
    ('load', 0, 'consumption_input'): time_series['load'].to_numpy()[:len(microgrid_df)],        # Aggiunge il consumo in input come colonna al DataFrame della microgrid
   # ('battery', 0, 'eta_dynamic'): np.asarray(eta_dynamic),                                       # Aggiunge l'efficienza dinamica al DataFrame della microgrid
    ('price', 0, 'price_buy'): price_buy_time_series[: len(microgrid_df)],                       # Aggiunge la colonna price_buy al DataFrame della microgrid
    ('price', 0, 'price_sell'): price_sell_time_series[: len(microgrid_df)]                      # Aggiunge la colonna price_sell al DataFrame della microgrid
}

microgrid_df = add_module_columns(microgrid_df, additional_columns)

print(transition_model)

transition_model.plot_transition_history(save_path=f"transitions_{simulator.battery_chemistry}.png", show=True)
transition_model.save_transition_history(history_path=f"transitions_{simulator.battery_chemistry}.json")

#print(microgrid.log.columns)

#show(time_series=time_series, microgrid_df=microgrid_df)



###### PLOT FINAL RESULTS #######

timestamp_now = datetime.now().strftime('%Y%m%d_%H%M%S')
csv_name = f"ems_results_{timestamp_now}.csv"      
output_dir = Path("outputs")  
csv_path = output_dir / csv_name                                                  # Directory di output per file CSV e grafici
output_dir.mkdir(exist_ok=True)  
base_name = (output_dir / csv_name.replace(".csv", ""))

"""plot_paths = plot_results(microgrid_df, str(base_name), timezone_str)       # Genera e salva i grafici, ottenendo i percorsi dei file

print("\nApertura grafici...")
for label, path in plot_paths.items():              # Tenta di aprire automaticamente i file grafici generati
    try:
        os.startfile(os.path.abspath(path))
    except OSError:
        print(f"  Impossibile aprire automaticamente {path}")"""
