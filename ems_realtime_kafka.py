import os
import sys
import time
from collections import deque
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import pandas as pd
import yaml
import pytz

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
    """Determina la fascia oraria del timestamp e restituisce il vettore prezzi associato."""
    hour = timestamp.hour  # Confrontiamo solo l'ora perché le fasce sono espresse in intervalli orari.

    def hour_in_ranges(hr, ranges):
        """True se l'ora `hr` rientra in uno dei range dichiarati per la fascia (peak o standard), altrimenti False."""
        for rng in ranges or []:
            start, end = rng
            if start <= hr <= end:
                return True
        return False

    # Ricerca prioritaria: prima le fasce più costose (peak) poi quelle standard.
    for band_key in ('peak', 'standard'):
        band_cfg = price_config.get(band_key)
        if band_cfg and hour_in_ranges(hour, band_cfg.get('ranges')):
            return (
                np.array([band_cfg.get('buy', 0.0), band_cfg.get('sell', 0.0), 0.0, 1.0]),
                band_key.upper(),
            )

    # In assenza di match utilizziamo la fascia di fallback (offpeak o la prima definita).
    fallback_key = 'offpeak' if 'offpeak' in price_config else next(iter(price_config))
    fallback_cfg = price_config.get(fallback_key, {})
    return (
        np.array([fallback_cfg.get('buy', 0.0), fallback_cfg.get('sell', 0.0), 0.0, 1.0]),
        fallback_key.upper(),
    )

def rule_based_control(microgrid, load_kwh, pv_kwh):
    """Controllo greedy che decide quanta energia usare da batteria e rete nello step corrente."""
    battery = microgrid.battery[0]
    e_grid = 0.0
    e_batt = 0.0

    tolerance = 1e-6  # Evita oscillazioni dovute alle approssimazioni floating point.
    if load_kwh > pv_kwh + tolerance:
        # Carico maggiore della produzione FV: scarica la batteria finché possibile e importa il resto.
        deficit = load_kwh - pv_kwh
        max_discharge = max(0.0, battery.max_production)
        discharge = min(deficit, max_discharge)
        e_batt = discharge
        e_grid = max(deficit - discharge, 0.0)
    elif pv_kwh > load_kwh + tolerance:
        # Surplus FV: carica la batteria entro i limiti e riversa l'eccesso verso la rete.
        surplus = pv_kwh - load_kwh
        max_charge = max(0.0, battery.max_consumption)
        charge = min(surplus, max_charge)
        e_batt = -charge
        e_grid = -max(surplus - charge, 0.0)

    return e_batt, e_grid

def deque_last(buffer: deque, default=None):
    """
    Utility per prendere l'ultimo elemento da una deque, con valore di
    default quando la coda e' vuota (utile durante l'avvio del consumer).
    Lo utiliziamo per ottenere gli ultimi valori di load, solar e timestamp da Kafka, 
    dato che il consumer li memorizza in deques (buffer) di dimensione limitata.
    """
    return buffer[-1] if len(buffer) else default


@dataclass
class EMSConfig:
    kafka_topic: str
    buffer_size: int
    timezone: str
    steps: int
    price_bands: dict


@dataclass
class EMSModules:
    simulator: MicrogridSimulator
    microgrid: Any
    load_module: Any
    pv_module: Any
    grid_module: Any
    battery_module: Any
    balancing_module: Optional[Any] = None


def sum_module_info(info_dict, module_name, key):
    """
    Somma un determinato campo di info per tutte le istanze del modulo richiesto.
    """
    total = 0.0
    for entry in info_dict.get(module_name, []):    # Itera su tutte le istanze del modulo
        if not isinstance(entry, dict):             # Salta se l'entry non e' un dizionario valido
            continue
        value = entry.get(key)                      # Prende il valore del campo specificato
        if value is None:                           # Salta se il campo non esiste
            continue
        try:
            total += float(value)                   # Aggiunge il valore convertito a float
        except (TypeError, ValueError):             # Salta se la conversione fallisce
            continue
    return total                                    # Restituisce il totale calcolato


def init_live_battery_display(initial_soc_pct, timestamp):
    """Crea la finestra matplotlib con l'icona della batteria aggiornata ad ogni step."""
    try:
        plt.ion()  # Modalità interattiva per aggiornare il disegno senza bloccare l'esecuzione.
        fig, ax = plt.subplots(figsize=(3, 5))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1.3)
        ax.axis('off')  # Nasconde gli assi per mostrare solo l'icona stilizzata.

        # Corpo e cappuccio della batteria (solo contorni).
        body = patches.Rectangle((0.2, 0.15), 0.6, 1.0, linewidth=2.5, edgecolor='black', facecolor='none', joinstyle='round')
        cap = patches.Rectangle((0.4, 1.15), 0.2, 0.08, linewidth=2.0, edgecolor='black', facecolor='lightgray')

        # Riempimento proporzionale allo stato di carica iniziale.
        fill = patches.Rectangle(
            (0.2, 0.15),
            0.6,
            max(0.0, min(1.0, initial_soc_pct / 100.0)) * 1.0,
            facecolor='#32CD32',
        )

        ax.add_patch(fill)
        ax.add_patch(body)
        ax.add_patch(cap)

        # Testi dinamici per SOC e timestamp corrente.
        soc_text = ax.text(0.5, 0.05, f"{initial_soc_pct:5.1f}%", ha='center', va='center', fontsize=12, fontweight='bold')
        time_text = ax.text(0.5, 1.28, str(timestamp), ha='center', va='bottom', fontsize=10)

        fig.canvas.draw()
        fig.canvas.flush_events()
        return {'fig': fig, 'fill': fill, 'soc_text': soc_text, 'time_text': time_text}
    except Exception as exc:  # pragma: no cover
        print(f"[WARN] impossibile inizializzare la batteria live: {exc}")
        return None

def update_live_battery_display(display, soc_pct, timestamp):
    """Aggiorna colore, altezza del riempimento e testi della batteria live."""
    if not display:
        return
    soc_norm = max(0.0, min(1.0, soc_pct / 100.0))
    display['fill'].set_height(soc_norm * 1.0)

    # Colori intuitivi in base allo stato di carica.
    if soc_pct <= 20:
        display['fill'].set_color('#CC2936')  # rosso
    elif soc_pct <= 40:
        display['fill'].set_color('#FFA500')  # arancione
    else:
        display['fill'].set_color('#32CD32')  # verde

    display['soc_text'].set_text(f"{soc_pct:5.1f}%")
    display['time_text'].set_text(str(timestamp))
    display['fig'].canvas.draw()
    display['fig'].canvas.flush_events()

def build_microgrid() -> EMSModules:
    """Istanzia il simulatore, recupera i moduli principali e li incapsula in `EMSModules`."""
    simulator = MicrogridSimulator(
        config_path='params.yml',
        time_series=None,
        online=True,
    )
    microgrid = simulator.build_microgrid()

    # I moduli vengono prelevati una volta sola per evitare ricerche ripetute nel loop principale.
    load_module = microgrid.modules['load'][0]
    pv_module = microgrid.modules['pv'][0]
    grid_module = microgrid.modules['grid'][0]
    try:
        balancing_module = microgrid.modules['balancing'][0]
    except (KeyError, IndexError, TypeError):
        balancing_module = None

    microgrid.reset()  # Porta la microgrid in uno stato noto prima di iniziare la simulazione.
    return EMSModules(
        simulator=simulator,
        microgrid=microgrid,
        load_module=load_module,
        pv_module=pv_module,
        grid_module=grid_module,
        battery_module=microgrid.battery[0],
        balancing_module=balancing_module,
    )

def load_config(path: str = 'params.yml') -> EMSConfig:
    """Legge la sezione `ems` dal file YAML e valida i campi necessari all'esecuzione."""
    with open(path, 'r') as cfg_file:
        full_config = yaml.safe_load(cfg_file)

    ems_cfg = full_config.get('ems')
    if not ems_cfg:
        raise KeyError("Sezione 'ems' mancante in params.yml")

    # Verifica presenza chiavi richieste per evitare errori silenziosi più avanti.
    required_keys = ('kafka_topic', 'buffer_size', 'timezone', 'steps', 'price_bands')
    missing_keys = [key for key in required_keys if key not in ems_cfg]
    if missing_keys:
        raise KeyError(f"Mancano le chiavi {missing_keys} nella sezione 'ems' di params.yml")

    try:
        buffer_size = int(ems_cfg['buffer_size'])
        steps = int(ems_cfg['steps'])
    except (TypeError, ValueError) as exc:
        raise ValueError("I campi 'buffer_size' e 'steps' devono essere interi.") from exc

    return EMSConfig(
        kafka_topic=ems_cfg['kafka_topic'],
        buffer_size=buffer_size,
        timezone=ems_cfg['timezone'],
        steps=steps,
        price_bands=ems_cfg['price_bands'],
    )

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
    df.sort_values("timestamp", inplace=True)
    df["timestamp_original"] = df["timestamp"]
    df.set_index("timestamp", inplace=True)                # Imposta timestamp come indice

    # Rebase timeline to a regular range starting from the first timestamp.
    inferred_freq = pd.infer_freq(df.index)
    if inferred_freq is None and len(df.index) > 1:
        deltas = df.index.to_series().diff().dropna()
        if not deltas.empty:
            inferred_freq = deltas.median()
    if inferred_freq is None:
        inferred_freq = pd.Timedelta(minutes=15)
    aligned_index = pd.date_range(
        start=df.index.min(),
        periods=len(df.index),
        freq=inferred_freq
    )
    df.index = aligned_index

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

    # 4b) Animazione batteria a forma di icona
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
    config = load_config()              # Carica configurazione EMS da params.yml

    timezone_str = config.timezone      # Configura timezone per timestamp 

    print("\nInizializzazione Kafka Consumer...")
    consumer = KafkaConsumer(                         # Istanzia consumer Kafka con i parametri specificati
        buffer_size=config.buffer_size,
        topic=config.kafka_topic,
        timezone=timezone_str,
    )
    consumer.start_background()                        # Avvia consumer in thread separato
    price_config = config.price_bands                  # Configurazione fasce prezzi
    simulation_steps = config.steps                    # Numero di step di simulazione da eseguire

    print("Attesa primi dati...")
    while len(consumer.solar) == 0:                    # Attende che arrivino i primi dati da Kafka
        time.sleep(0.5)                                # Esce dal loop solo quando c'e' almeno un dato PV

    print("Inizializzazione microgrid...")
    modules = build_microgrid()                        # Costruisce microgrid e recupera i moduli principali
    simulator = modules.simulator                      # Modulo simulatore
    microgrid = modules.microgrid                      # Modulo microgrid
    load_module = modules.load_module                  # Modulo load
    pv_module = modules.pv_module                      # Modulo PV
    grid_module = modules.grid_module                  # Modulo rete
    balancing_module = modules.balancing_module        # Modulo bilanciamento (se presente)
    results = []                                       # Lista per memorizzare i risultati di ogni step
    last_count = consumer.total_messages               # Conta messaggi processati per sincronizzazione

    initial_timestamp = deque_last(consumer.timestamps, datetime.now())                # Prende il primo timestamp disponibile da Kafka
    initial_prices, initial_band = get_grid_prices(initial_timestamp, price_config)    # Ottiene prezzi iniziali e banda oraria
    battery_module = microgrid.battery[0]                                              # Riferimento al modulo batteria
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
        control = {"battery": e_batt, "grid": e_grid}                       # Prepara dizionario controllo per report

        observations, reward, done, info = microgrid.step(                  # Esegue step di simulazione con i controlli calcolati
            {"battery": [e_batt], "grid": [e_grid]}, normalized=False
        )

        battery_module = microgrid.battery[0]                                       # Riferimento al modulo batteria aggiornato

        grid_import = sum_module_info(info, "grid", "provided_energy")              # Somma energia importata dalla rete per report step 
        grid_export = sum_module_info(info, "grid", "absorbed_energy")              # Somma energia esportata verso la rete per report step
        battery_charge = sum_module_info(info, "battery", "absorbed_energy")        # Somma energia caricata in batteria per report step
        battery_discharge = sum_module_info(info, "battery", "provided_energy")     # Somma energia scaricata dalla batteria per report step
        load_met = sum_module_info(info, "load", "absorbed_energy")                 # Somma energia load soddisfatta per report step
        renewable_used = sum_module_info(info, "pv", "provided_energy")             # Somma energia rinnovabile usata per report step    
        curtailment = sum_module_info(info, "pv", "curtailment")                    # Somma energia PV non utilizzata (curtailment) per report step
        loss_load_value = sum_module_info(info, "balancing", "loss_load_energy")    # Somma energia di load non soddisfatta (loss of load) per report step

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



