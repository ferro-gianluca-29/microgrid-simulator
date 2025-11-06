import os
import sys
import time
from collections import deque
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
import pytz
from typing import Optional
from pathlib import Path

# Assicura che la cartella generator_and_consumer sia visibile agli import
PROJECT_ROOT = Path(__file__).resolve().parent
GENERATOR_DIR = PROJECT_ROOT / "generator_and_consumer"
if GENERATOR_DIR.exists() and str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from generator_and_consumer.consumer_class import KafkaConsumer
from microgrid_simulator import MicrogridSimulator


# =============================================================================
# Funzioni di supporto
# =============================================================================
def get_grid_prices(timestamp: datetime, price_config: dict):
    """
    Calcola l'ora corrente, ricerca la fascia peak o standard in base ai range orari configurati, 
    e restituisce vettore prezzi [buy, sell, 0, 1] più etichetta banda; se nessuna corrispondenza 
    usa fascia offpeak o la prima disponibile.
    """
    hour = timestamp.hour                # Estrae l'ora corrente dallo timestamp fornito

    def hour_in_ranges(hr, ranges):      # Verifica se l'ora hr rientra in uno dei range specificati
        for rng in ranges or []:
            start, end = rng
            if start <= hr <= end:
                return True
        return False

    # Ordine preferito: peak -> standard -> offpeak (default)
    for band_key in ("peak", "standard"):                        # Controlla fasce peak e standard 
        band_cfg = price_config.get(band_key)
        if band_cfg and hour_in_ranges(hour, band_cfg.get("ranges")):       # Se l'ora rientra nei range, restituisce i prezzi e la banda
            return (
                np.array([band_cfg.get("buy", 0.0), band_cfg.get("sell", 0.0), 0.0, 1.0]),
                band_key.upper(),
            )

    # Se non è rientrato in nessuna fascia, usa quella di fallback (offpeak o la prima disponibile)
    fallback_key = "offpeak" if "offpeak" in price_config else next(iter(price_config))
    fallback_cfg = price_config.get(fallback_key, {})
    return (                                                                                 # Restituisce i prezzi di fallback e la banda
        np.array([fallback_cfg.get("buy", 0.0), fallback_cfg.get("sell", 0.0), 0.0, 1.0]),
        fallback_key.upper(),
    )


def rule_based_control(microgrid, load_kwh, pv_kwh):
    """ 
    Implementa controllo greedy sull'energia scambiata nello step corrente (kWh):
    se il carico supera il fotovoltaico tenta di scaricare la batteria fino al limite (max_production),
    importando da rete l'eventuale deficit; se il PV eccede il carico prova a caricare la batteria
    (max_consumption) ed esporta l'eccedenza residua.
    """
    battery = microgrid.battery[0]
    e_grid = 0.0
    e_batt = 0.0

    if load_kwh > pv_kwh:
        e_batt = battery.max_production
        deficit = load_kwh - pv_kwh - e_batt
        if deficit > 0:
            e_grid = deficit
    elif pv_kwh > load_kwh:
        e_batt = -battery.max_consumption
        surplus = pv_kwh - load_kwh - abs(e_batt)
        if surplus > 0:
            e_grid = -surplus

    return e_batt, e_grid


def deque_last(buffer: deque, default=None):
    """
    Utility per prendere l'ultimo elemento da una deque, con valore di
    default quando la coda e' vuota (utile durante l'avvio del consumer).
    """
    return buffer[-1] if len(buffer) else default


def get_logger_last(logger, key, default=0.0):
    """
    Ultimo valore disponibile per la chiave nel ModularLogger associato al modulo.
    """
    if logger is None:
        return default
    try:
        values = logger.get(key)
    except AttributeError:
        return default
    if not values:
        return default
    value = values[-1]
    try:
        return float(value)
    except (TypeError, ValueError):
        return value if value is not None else default


def print_step_report(step_idx, timestamp, band, kafka_load, kafka_pv, load_kwh, pv_kwh,
                      battery_info, grid_info, energy_metrics, control, prices, economics):
    """
    Stampa un report leggibile per ogni step con dati Kafka vs simulator, controllo applicato,
    stato batteria, scambi rete, prezzi ed economia, facilitando il debug live.
    """
    header = f"\n{'=' * 120}\nSTEP {step_idx} - {timestamp.strftime('%Y-%m-%d %H:%M:%S')} ({band})\n{'=' * 120}"    # Intestazione step
    print(header)

    print(f"Kafka Load/PV        : load={kafka_load:6.3f} kWh | pv={kafka_pv:6.3f} kWh")
    print(f"Microgrid Load/PV    : load={load_kwh:6.3f} kWh | pv={pv_kwh:6.3f} kWh")
    print(f"Controllo applicato  : battery={control['battery']:6.3f} kWh | grid={control['grid']:6.3f} kWh")

    print("\nEnergia Microgrid:")
    print(f"  Load met          : {energy_metrics['load_met']:6.3f} kWh")
    print(f"  Renewable used    : {energy_metrics['renewable_used']:6.3f} kWh")
    print(f"  Curtailment       : {energy_metrics['curtailment']:6.3f} kWh")
    print(f"  Loss of load      : {energy_metrics['loss_load']:6.3f} kWh")

    print("\nBatteria:")
    print(f"  SOC              : {battery_info['soc_pct']:6.2f}%")
    print(f"  Current charge   : {battery_info['current_charge']:6.3f} kWh")
    print(f"  Charge/Discharge : +{battery_info['charge_amount']:6.3f} kWh | -{battery_info['discharge_amount']:6.3f} kWh")

    print("\nRete:")
    print(f"  Import/Export    : +{grid_info['import']:6.3f} kWh | -{grid_info['export']:6.3f} kWh")
    print(f"  Prezzi           : buy={prices['buy']:5.2f} EUR/kWh | sell={prices['sell']:5.2f} EUR/kWh")

    print("\nEconomia:")
    print(f"  Cost Import      : {economics['cost']:7.4f} EUR")
    print(f"  Revenue Export   : {economics['revenue']:7.4f} EUR")
    print(f"  Balance          : {economics['balance']:7.4f} EUR")
    print(f"  Reward (approx)  : {economics['reward']:7.4f}")


def plot_results(df: pd.DataFrame, base_name: str, timezone: Optional[str] = None):
    """
    Duplica il DataFrame finale, ordina per timestamp e genera cinque grafici (potenze, energia rete step+cumulata, 
    prezzi/bande TOU con fill_between, SOC e flussi batteria con doppio asse, metriche economiche con bilancio cumulativo).
    Ogni figura viene salvata a 160 dpi con nome basato su base_name, poi chiusa per liberare memoria; 
    la funzione restituisce i percorsi dei file generati per uso successivo.
    """
    df = df.copy()                                         # Duplica DataFrame per evitare modifiche all'originale
    timestamps = pd.to_datetime(df["timestamp"], errors="coerce")  # Converte la colonna timestamp in datetime

    # Normalizza il timezone: se i timestamp sono tz-aware, convertili nel timezone configurato (se fornito)
    if hasattr(timestamps.dt, "tz") and timestamps.dt.tz is not None:
        if timezone:
            tz = pytz.timezone(timezone)
            timestamps = timestamps.dt.tz_convert(tz)
        timestamps = timestamps.dt.tz_localize(None)       # Porta i timestamp a naive per matplotlib
    df["timestamp"] = timestamps
    df.dropna(subset=["timestamp"], inplace=True)          # Rimuove eventuali righe senza timestamp valido
    df.sort_values("timestamp", inplace=True)              # Ordina per timestamp
    df.set_index("timestamp", inplace=True)                # Imposta timestamp come indice

    # 1) Potenze istantanee
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(df.index, df["mg_load_kwh"], label="Load (kWh)", linewidth=2)
    ax.plot(df.index, df["mg_pv_kwh"], label="PV (kWh)", linewidth=2)
    ax.plot(df.index, df["control_batt_kwh"], label="Battery Net Flow (kWh)", linewidth=1.8, linestyle="-.")
    ax.plot(df.index, df["battery_current_charge_kwh"], label="Battery Stored Energy (kWh)", linewidth=1.8, linestyle=":")
    ax.plot(df.index, df["control_grid_kwh"], label="Grid Energy (kWh)", linewidth=1.8, linestyle="--")
    ax.set_title("Energy Flows per Step")
    ax.set_ylabel("Energy [kWh]")
    ax.set_xlabel("Time")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.4)
    energy_path = f"{base_name}_energy.png"
    fig.tight_layout()
    fig.savefig(energy_path, dpi=160)
    plt.close(fig)

    # 2) Energia rete cumulativa e per step
    cumulative_import = df["grid_import_kwh"].cumsum()
    cumulative_export = df["grid_export_kwh"].cumsum()
    fig, ax1 = plt.subplots(figsize=(12, 5))
    ax1.bar(df.index, df["grid_import_kwh"], label="Import step (kWh)", color="tab:blue", alpha=0.45, width=0.025)
    ax1.bar(df.index, -df["grid_export_kwh"], label="Export step (kWh)", color="tab:orange", alpha=0.45, width=0.025)
    ax1.set_ylabel("Energy per step [kWh]")
    ax1.set_xlabel("Time")
    ax1.grid(True, linestyle="--", alpha=0.4)

    ax2 = ax1.twinx()
    ax2.plot(df.index, cumulative_import, label="Cumulative Import (kWh)", color="tab:blue", linewidth=2.2)
    ax2.plot(df.index, cumulative_export, label="Cumulative Export (kWh)", color="tab:orange", linewidth=2.2)
    ax2.set_ylabel("Cumulative Energy [kWh]")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    ax1.set_title("Grid Energy Exchange (Step & Cumulative)")
    grid_path = f"{base_name}_grid.png"
    fig.tight_layout()
    fig.savefig(grid_path, dpi=160)
    plt.close(fig)

    # 3) Prezzi vs band
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(df.index, df["price_buy_eur_kwh"], label="Price Buy (eur/kWh)", linewidth=2)
    ax.plot(df.index, df["price_sell_eur_kwh"], label="Price Sell (eur/kWh)", linewidth=2)
    unique_bands = df["band"].unique()
    for band in unique_bands:
        band_mask = df["band"] == band
        if band_mask.any():
            ax.fill_between(
                df.index,
                df["price_buy_eur_kwh"].min() * 0.95,
                df["price_buy_eur_kwh"].max() * 1.05,
                where=band_mask,
                alpha=0.08,
                label=f"Band {band}" if f"Band {band}" not in ax.get_legend_handles_labels()[1] else "",
            )
    ax.set_title("Grid Prices and Time-of-Use Bands")
    ax.set_ylabel("eur/kWh")
    ax.set_xlabel("Time")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.4)
    prices_path = f"{base_name}_prices.png"
    fig.tight_layout()
    fig.savefig(prices_path, dpi=160)
    plt.close(fig)

    # 4) Batteria: SOC e flussi
    fig, ax1 = plt.subplots(figsize=(12, 5))
    ax1.plot(df.index, df["battery_soc_pct"], color="tab:blue", label="SOC (%)", linewidth=2.2)
    ax1.set_ylabel("SOC [%]", color="tab:blue")
    ax1.tick_params(axis="y", labelcolor="tab:blue")
    ax1.grid(True, linestyle="--", alpha=0.4)

    ax2 = ax1.twinx()
    ax2.bar(df.index, df["battery_charge_kwh"], label="Charge (kWh)", color="tab:green", alpha=0.4, width=0.025)
    ax2.bar(df.index, -df["battery_discharge_kwh"], label="Discharge (kWh)", color="tab:red", alpha=0.4, width=0.025)
    ax2.set_ylabel("Charge / Discharge [kWh]", color="tab:red")
    ax2.tick_params(axis="y", labelcolor="tab:red")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    ax1.set_title("Battery State of Charge and Flows")

    battery_path = f"{base_name}_battery.png"
    fig.tight_layout()
    fig.savefig(battery_path, dpi=160)
    plt.close(fig)

    # 5) Indicatori economici per step e cumulativi
    fig, ax1 = plt.subplots(figsize=(12, 5))
    ax1.bar(df.index, df["cost_import_eur"], label="Import Cost (eur/step)", color="tab:blue", alpha=0.45, width=0.025)
    ax1.bar(df.index, df["revenue_export_eur"], label="Export Revenue (eur/step)", color="tab:orange", alpha=0.45, width=0.025)
    ax1.set_ylabel("eur/step")
    ax1.set_xlabel("Time")
    ax1.grid(True, linestyle="--", alpha=0.4)

    ax2 = ax1.twinx()
    ax2.plot(
        df.index,
        df["economic_balance_eur"].cumsum(),
        label="Cumulative Balance (EUR)",
        color="tab:purple",
        linewidth=2.3,
    )
    ax2.set_ylabel("Cumulative Balance [EUR]", color="tab:purple")
    ax2.tick_params(axis="y", labelcolor="tab:purple")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    ax1.set_title("Economic Performance")

    economics_path = f"{base_name}_economics.png"
    fig.tight_layout()
    fig.savefig(economics_path, dpi=160)
    plt.close(fig)

    return {                             # Restituisce i percorsi dei file generati
        "energy": energy_path,
        "grid": grid_path,
        "prices": prices_path,
        "battery": battery_path,
        "economics": economics_path,
    }


# =============================================================================
# Main
# =============================================================================
def main():
    with open("params.yml", "r") as cfg_file:   # Carica configurazione da file YAML 
        full_config = yaml.safe_load(cfg_file)

    ems_cfg = full_config.get("ems")            # Estrae sezione 'ems' dalla configurazione caricata 
    if not ems_cfg:
        raise KeyError("Sezione 'ems' mancante in params.yml")     # Verifica presenza sezione 'ems' altrimenti solleva errore

    required_keys = ("kafka_topic", "buffer_size", "timezone", "steps", "price_bands")   # Chiavi richieste nella sezione 'ems'
    missing_keys = [key for key in required_keys if key not in ems_cfg]
    if missing_keys:
        raise KeyError(f"Mancano le chiavi {missing_keys} nella sezione 'ems' di params.yml")   # Verifica presenza chiavi richieste

    kafka_topic = ems_cfg["kafka_topic"]          # Topic Kafka
    buffer_size = ems_cfg["buffer_size"]          # Dimensione buffer dati (96 per 15min in 24h)
    timezone = ems_cfg["timezone"]                # Timezone per timestamp
    simulation_steps = ems_cfg["steps"]           # Numero di step di simulazione
    price_config = ems_cfg["price_bands"]         # Configurazione fasce orarie e prezzi

    print("\nInizializzazione Kafka Consumer...")
    consumer = KafkaConsumer(                          # Crea consumer Kafka con configurazione specificata
        buffer_size=buffer_size,
        topic=kafka_topic,
        timezone=timezone,
    )
    consumer.start_background()                        # Avvia consumer in thread separato

    print("Attesa primi dati...")
    while len(consumer.solar) == 0:                    # Attende che arrivino i primi dati
        time.sleep(0.5)

    print("Inizializzazione microgrid...")
    simulator = MicrogridSimulator(                    # Crea microgrid simulator con configurazione specificata
        config_path="params.yml",
        time_series=None,
        online=True,                                   # Modalità online per dati in tempo reale
    )
    microgrid = simulator.build_microgrid()            # Costruisce microgrid da configurazione
    load_module = microgrid.modules["load"][0]         # Riferimento al modulo load 
    pv_module = microgrid.modules["pv"][0]             # Riferimento al modulo PV
    grid_module = microgrid.modules["grid"][0]         # Riferimento al modulo rete
    try:
        balancing_module = microgrid.modules["balancing"][0]   # Riferimento al modulo balancing se presente, serve per i calcoli
    except (KeyError, IndexError, TypeError):
        balancing_module = None
    microgrid.reset()                                  # Resetta stato microgrid all'inizio della simulazione

    results = []                                       # Lista per memorizzare i risultati di ogni step
    last_count = consumer.total_messages               # Conta messaggi processati per sincronizzazione

    for step in range(1, simulation_steps + 1):         # Loop principale per il numero di step specificato
        while consumer.total_messages == last_count:    # Attende nuovi dati Kafka se non sono arrivati 
            time.sleep(0.5)
        last_count = consumer.total_messages            # Aggiorna contatore messaggi

        kafka_load = deque_last(consumer.load, 0.0)                     # Energia load per intervallo dall'ultimo messaggio Kafka
        kafka_pv = deque_last(consumer.solar, 0.0)                      # Energia PV per intervallo dall'ultimo messaggio Kafka
        timestamp = deque_last(consumer.timestamps, datetime.now())     # Prende ultimo timestamp da buffer Kafka con default ora corrente

        grid_prices, band = get_grid_prices(timestamp, price_config)    # Ottiene prezzi rete e banda oraria corrente

        microgrid.ingest_real_time_data(                                 # Inietta dati real-time nella microgrid
            {"load": kafka_load, "pv": kafka_pv, "grid": [grid_prices]}
        )

        load_kwh = load_module.current_load             # Energia load attuale nello step della microgrid (dovrebbe corrispondere a kafka_load)
        pv_kwh = pv_module.current_renewable            # Energia PV attuale nello step della microgrid (dovrebbe corrispondere a kafka_pv)

        e_batt, e_grid = rule_based_control(microgrid, load_kwh, pv_kwh)    # Calcola controllo basato su regole 
        control = {"battery": e_batt, "grid": e_grid}                     # Prepara dizionario controllo per report

        observations, reward, done, info = microgrid.step(                # Esegue step di simulazione con i controlli calcolati
            {"battery": [e_batt], "grid": [e_grid]}, normalized=False
        )

        battery_module = microgrid.battery[0]                                           # Riferimenti ai moduli batteria e rete
        battery_logger = battery_module.logger
        grid_logger = grid_module.logger
        load_logger = load_module.logger
        pv_logger = pv_module.logger
        balancing_logger = balancing_module.logger if balancing_module is not None else None

        battery_info = {                                                          # Prepara dizionario info batteria per report
            "soc_pct": battery_module.soc * 100,
            "current_charge": get_logger_last(battery_logger, "current_charge", battery_module.current_charge),
            "charge_amount": get_logger_last(battery_logger, "charge_amount", 0.0),
            "discharge_amount": get_logger_last(battery_logger, "discharge_amount", 0.0),
        }
        grid_info = {                                                             # Prepara dizionario info rete per report
            "import": get_logger_last(grid_logger, "grid_import", get_logger_last(grid_logger, "import", 0.0)),
            "export": get_logger_last(grid_logger, "grid_export", get_logger_last(grid_logger, "export", 0.0)),
        }
        loss_load_value = get_logger_last(balancing_logger, "loss_load", None)
        if loss_load_value is None:
            loss_load_value = get_logger_last(balancing_logger, "loss_load_energy", 0.0)
        energy_metrics = {                                                        # Metriche energetiche derivanti dai log
            "load_met": get_logger_last(load_logger, "load_met", load_kwh),
            "renewable_used": get_logger_last(pv_logger, "renewable_used", min(pv_kwh, load_kwh)),
            "curtailment": get_logger_last(pv_logger, "curtailment", 0.0),
            "loss_load": loss_load_value if loss_load_value is not None else 0.0,
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

    consumer.stop()                         # Ferma il consumer Kafka
    print("\nConsumer fermato.")

    results_df = pd.DataFrame(results)                                            # Crea DataFrame Pandas dai risultati raccolti
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)
    timestamp_now = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_name = f"ems_results_{timestamp_now}.csv"      # Nome file CSV con timestamp corrente
    csv_path = output_dir / csv_name
    results_df.to_csv(csv_path, index=False)                                      # Salva risultati su file CSV 

    base_name = (output_dir / csv_name.replace(".csv", ""))                       # Base name per i file grafici
    plot_paths = plot_results(results_df, str(base_name), timezone)       # Genera e salva i grafici, ottenendo i percorsi dei file

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


