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


from generator_and_consumer.consumer_class import KafkaConsumer
from generator_and_consumer.consumer_class import KafkaConsumer


from microgrid_simulator import MicrogridSimulator
from tools import get_online_grid_prices, load_config, init_live_battery_display
from tools import update_live_battery_display, print_step_report, plot_results
from EMS import Rule_Based_EMS



def main():

    ###### LOAD CONFIGURATION FROM YAML 

    config = load_config()              # Carica configurazione EMS da params.yml
    timezone_str = config['timezone']   # Configura timezone per timestamp 
    night_charge_enabled = config.get('allow_night_grid_charge', False)

    print("\nInizializzazione Kafka Consumer...")
    consumer = KafkaConsumer(                         # Istanzia consumer Kafka con i parametri specificati
        buffer_size=config['buffer_size'],
        topic=config['kafka_topic'],
        timezone=timezone_str,
    )
    consumer.start_background()                        # Avvia consumer in thread separato
    price_config = config['price_bands']               # Configurazione fasce prezzi
    simulation_steps = config['steps']                 # Numero di step di simulazione da eseguire

    print("Attesa primi dati...")
    while len(consumer.solar) == 0:                    # Attende che arrivino i primi dati da Kafka
        time.sleep(0.1)                                # Esce dal loop solo quando c'e' almeno un dato PV


    #################################


    ###### INSTANTIATE MICROGRID SIMULATOR WITH MODULES

    print("Inizializzazione microgrid...")

    simulator = MicrogridSimulator(
        config_path='params.yml',
        online=True,
    )

    microgrid = simulator.build_microgrid()  # Costruisce la microgrid dai parametri nel file di configurazione.
    microgrid.reset()  # Porta la microgrid in uno stato noto prima di iniziare la simulazione.

    load_module = microgrid.modules['load'][0]         # Modulo load
    pv_module = microgrid.modules['pv'][0]             # Modulo PV
    results = []                                       # Lista per memorizzare i risultati di ogni step
    last_count = consumer.total_messages               # Conta messaggi processati per sincronizzazione

    initial_timestamp = consumer.deque_last(consumer.timestamps, datetime.now())                # Prende il primo timestamp disponibile da Kafka
    initial_prices, initial_band = get_online_grid_prices(initial_timestamp, price_config)    # Ottiene prezzi iniziali e banda oraria
    battery_module = microgrid.battery[0]                                              # Riferimento al modulo batteria


    #################################


    ###### TERMINAL GRAPHIC INTERFACE FOR INITIAL STATE 

    initial_soc = (                                                                    # Calcola SOC iniziale in percentuale
        battery_module.current_charge / simulator.nominal_capacity * 100.0
        if simulator.nominal_capacity > 0
        else 0.0
    )
    initial_battery_info = {                                         # Prepara dizionario info batteria iniziale per report step 0
        "soc_pct": initial_soc,
        "current_charge": battery_module.current_charge,
        "charge_amount": 0.0,
        "discharge_amount": 0.0,
    }
    zero_energy = {                                                  # Dizionario metriche energetiche iniziali a zero per report step 0
        "load_met": 0.0,
        "renewable_used": 0.0,
        "curtailment": 0.0,
        "loss_load": 0.0,
    }
    zero_grid = {"import": 0.0, "export": 0.0}                                         # Dizionario info rete iniziali a zero per report step 0
    zero_control = {"battery": 0.0, "grid": 0.0}                                       # Dizionario controllo iniziale a zero per report step 0
    zero_economics = {"cost": 0.0, "revenue": 0.0, "balance": 0.0, "reward": 0.0}      # Dizionario economia iniziale a zero per report step 0

    live_battery_display = init_live_battery_display(initial_soc, initial_timestamp)   # Inizializza visualizzazione live batteria

    print(f"\n{'=' * 120}")
    print("STEP 0 - INITIAL GRID STATE (no timestamp available)")
    print(f"{'=' * 120}")
    print(f"Fascia prezzi     : {initial_band.upper()}")
    print(f"Prezzi grid       : buy={initial_prices[0]:5.2f} EUR/kWh | sell={initial_prices[1]:5.2f} EUR/kWh")
    print("\nBatteria iniziale:")
    print(f"  SOC              : {initial_battery_info['soc_pct']:6.2f}%")
    print(f"  Current charge   : {initial_battery_info['current_charge']:6.3f} kWh")
    print(f"  Charge/Discharge : +{initial_battery_info['charge_amount']:6.3f} kWh | -{initial_battery_info['discharge_amount']:6.3f} kWh")


    ################################################




    ###### INSTANTIATE ENERGY MANAGEMENT SYSTEM AND RUN SIMULATION

    rule_based_EMS = Rule_Based_EMS(microgrid)

    for step in range(1, simulation_steps + 1):         # Loop principale per il numero di step specificato
        while consumer.total_messages == last_count:    # Attende nuovi dati Kafka se non sono arrivati 
            time.sleep(0.1)
        last_count = consumer.total_messages            # Aggiorna contatore messaggi

        kafka_load = consumer.deque_last(consumer.load, 0.0)                     # Energia load per intervallo dall'ultimo messaggio Kafka
        kafka_pv = consumer.deque_last(consumer.solar, 0.0)                      # Energia PV per intervallo dall'ultimo messaggio Kafka
        timestamp = consumer.deque_last(consumer.timestamps, datetime.now())     # Prende ultimo timestamp da buffer Kafka con default ora corrente

        grid_prices, band = get_online_grid_prices(timestamp, price_config)    # Ottiene prezzi rete e banda oraria corrente

        microgrid.ingest_real_time_data(                                 # Inietta dati real-time nella microgrid
            {"load": kafka_load, "pv": kafka_pv, "grid": [grid_prices]}
        )

        load_kwh = load_module.current_load             # Energia load attuale nello step della microgrid (dovrebbe corrispondere a kafka_load)
        pv_kwh = pv_module.current_renewable            # Energia PV attuale nello step della microgrid (dovrebbe corrispondere a kafka_pv)

        e_batt, e_grid = rule_based_EMS.control(                                # Calcola controllo basato su regole 
            load_kwh,
            pv_kwh,
            band=band,
            allow_night_grid_charge=night_charge_enabled,
        )
        control = {"battery": e_batt, "grid": e_grid}                       # Prepara dizionario controllo per report

        observations, reward, done, info = microgrid.step(                  # Esegue step di simulazione con i controlli calcolati
            {"battery": [e_batt], "grid": [e_grid]}, normalized=False
        )

        battery_module = microgrid.battery[0]                                       # Riferimento al modulo batteria aggiornato

        grid_import = simulator.sum_module_info(info, "grid", "provided_energy")              # Somma energia importata dalla rete per report step 
        grid_export = simulator.sum_module_info(info, "grid", "absorbed_energy")              # Somma energia esportata verso la rete per report step
        battery_charge = simulator.sum_module_info(info, "battery", "absorbed_energy")        # Somma energia caricata in batteria per report step
        battery_discharge = simulator.sum_module_info(info, "battery", "provided_energy")     # Somma energia scaricata dalla batteria per report step
        load_met = simulator.sum_module_info(info, "load", "absorbed_energy")                 # Somma energia load soddisfatta per report step
        renewable_used = simulator.sum_module_info(info, "pv", "provided_energy")             # Somma energia rinnovabile usata per report step    
        curtailment = simulator.sum_module_info(info, "pv", "curtailment")                    # Somma energia PV non utilizzata (curtailment) per report step
        loss_load_value = simulator.sum_module_info(info, "balancing", "loss_load_energy")    # Somma energia di load non soddisfatta (loss of load) per report step

        actual_soc = 0.0                                                        # Inizializza SOC reale a 0
        if simulator.nominal_capacity > 0:                                      # Calcola SOC reale dopo lo step
            actual_soc = np.clip(                                               # Clippa tra 0 e 1 per evitare valori anomali
                battery_module.current_charge / simulator.nominal_capacity,     # Calcola SOC come frazione della capacità nominale
                0.0,                                                            
                1.0,
            )

        battery_info = {                                                          # Prepara dizionario info batteria per report
            "soc_pct": actual_soc * 100.0,
            "current_charge": battery_module.current_charge,
            "charge_amount": battery_charge,
            "discharge_amount": battery_discharge,
        }
        grid_info = {                                                             # Prepara dizionario info rete per report
            "import": grid_import,
            "export": grid_export,
        }
        energy_metrics = {                                                        # Metriche energetiche derivanti dai log 
            "load_met": load_met if load_met > 0 else load_kwh,
            "renewable_used": renewable_used if renewable_used > 0 else min(pv_kwh, load_kwh),
            "curtailment": curtailment,
            "loss_load": loss_load_value,
        }

        prices = {"buy": grid_prices[0], "sell": grid_prices[1]}                  # Prepara dizionario prezzi per report
        economics = {                                                             # Calcola indicatori economici per report
            "cost": grid_info["import"] * prices["buy"],
            "revenue": grid_info["export"] * prices["sell"],
            "balance": grid_info["export"] * prices["sell"] - grid_info["import"] * prices["buy"],
            "reward": float(reward),
        }

        print_step_report(                       # Stampa report dettagliato per lo step corrente
            step,
            timestamp,
            band,
            kafka_load,
            kafka_pv,
            load_kwh,
            pv_kwh,
            battery_info,
            grid_info,
            energy_metrics,
            control,
            prices,
            economics,
        )

        results.append(                         # Memorizza i risultati dello step corrente per il CSV finale e i grafici
            {
                "step": step,
                "timestamp": timestamp,
                "band": band,
                "kafka_load_kwh": kafka_load,
                "kafka_pv_kwh": kafka_pv,
                "mg_load_kwh": load_kwh,
                "mg_pv_kwh": pv_kwh,
                "control_batt_kwh": e_batt,
                "control_grid_kwh": e_grid,
                "grid_import_kwh": grid_info["import"],
                "grid_export_kwh": grid_info["export"],
                "price_buy_eur_kwh": prices["buy"],
                "price_sell_eur_kwh": prices["sell"],
                "cost_import_eur": economics["cost"],
                "revenue_export_eur": economics["revenue"],
                "economic_balance_eur": economics["balance"],
                "reward": economics["reward"],
                "battery_soc_pct": battery_info["soc_pct"],
                "battery_current_charge_kwh": battery_info["current_charge"],
                "battery_charge_kwh": battery_info["charge_amount"],
                "battery_discharge_kwh": battery_info["discharge_amount"],
                "load_met_kwh": energy_metrics["load_met"],
                "renewable_used_kwh": energy_metrics["renewable_used"],
                "curtailment_kwh": energy_metrics["curtailment"],
                "loss_load_kwh": energy_metrics["loss_load"],
            }
        )

        update_live_battery_display(live_battery_display, battery_info["soc_pct"], timestamp)   # Aggiorna visualizzazione live batteria



    ######## STOP CONSUMER AND COMPUTE RESULTS

    consumer.stop()                         # Ferma il consumer Kafka
    print("\nConsumer fermato.")

    if live_battery_display:                # Chiude la visualizzazione live della batteria
        plt.ioff()
        try:
            live_battery_display["fig"].canvas.flush_events()         
        except Exception:
            pass
        plt.close(live_battery_display["fig"])

    results_df = pd.DataFrame(results)                                            # Crea DataFrame Pandas dai risultati raccolti
    output_dir = Path("outputs")                                                  # Directory di output per file CSV e grafici
    output_dir.mkdir(exist_ok=True)                                               # Crea directory se non esiste
    timestamp_now = datetime.now().strftime('%Y%m%d_%H%M%S')                      # Timestamp corrente per il nome file
    csv_name = f"ems_results_{timestamp_now}.csv"                                 # Nome file CSV con timestamp corrente
    csv_path = output_dir / csv_name                                              # Percorso completo del file CSV
    results_df.to_csv(csv_path, index=False)                                      # Salva risultati su file CSV 

    base_name = (output_dir / csv_name.replace(".csv", ""))                       # Base name per i file grafici
    plot_paths = plot_results(results_df, str(base_name), timezone_str)           # Genera e salva i grafici, ottenendo i percorsi dei file

    print("\n" + "-" * 120)
    print("RESOCONTO FINALE")                                     # Stampa resoconto finale con metriche aggregate
    print("-" * 120)
    print(f"Steps eseguiti             : {len(results_df)}")
    print(f"Load met totale [kWh]      : {results_df['load_met_kwh'].sum():8.3f}")
    print(f"Renewable usata [kWh]      : {results_df['renewable_used_kwh'].sum():8.3f}")
    print(f"Curtailment totale [kWh]   : {results_df['curtailment_kwh'].sum():8.3f}")
    print(f"Loss of load totale [kWh]  : {results_df['loss_load_kwh'].sum():8.3f}")
    print(f"Grid import totale [kWh]   : {results_df['grid_import_kwh'].sum():8.3f}")
    print(f"Grid export totale [kWh]   : {results_df['grid_export_kwh'].sum():8.3f}")
    print(f"Charge amount totale [kWh] : {results_df['battery_charge_kwh'].sum():8.3f}")
    print(f"Discharge amount tot [kWh] : {results_df['battery_discharge_kwh'].sum():8.3f}")
    print(f"SOC finale batteria   [%]  : {results_df['battery_soc_pct'].iloc[-1]:8.2f}")
    print(f"Current charge finale [kWh]: {results_df['battery_current_charge_kwh'].iloc[-1]:8.3f}")
    print(f"Costi import totali  [EUR] : {results_df['cost_import_eur'].sum():8.4f}")
    print(f"Ricavi export totali [EUR] : {results_df['revenue_export_eur'].sum():8.4f}")
    print(f"Bilancio economico   [EUR] : {results_df['economic_balance_eur'].sum():8.4f}")
    print(f"File CSV salvato           : {csv_name}")
    print("Grafici salvati:")
    for label, path in plot_paths.items():              # Stampa i percorsi dei file grafici generati
        print(f"  {label:7s} -> {path}")

    print("\nApertura grafici...")
    for label, path in plot_paths.items():              # Tenta di aprire automaticamente i file grafici generati
        try:
            os.startfile(os.path.abspath(path))
        except OSError:
            print(f"  Impossibile aprire automaticamente {path}")


if __name__ == "__main__":
    main()



