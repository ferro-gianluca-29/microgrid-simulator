
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import yaml
from typing import Dict, List, Optional, Tuple, Any
import pytz
import pandas as pd




def get_online_grid_prices(timestamp: datetime, price_config: dict):
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


def load_config(path='params.yml'):
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

    return {
        'kafka_topic': ems_cfg['kafka_topic'],
        'buffer_size': buffer_size,
        'timezone': ems_cfg['timezone'],
        'steps': steps,
        'price_bands': ems_cfg['price_bands'],
        'allow_night_grid_charge': bool(ems_cfg.get('allow_night_grid_charge', False)),
    }


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

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            "_".join(str(x) for x in col if x not in (None, ""))
            for col in df.columns
        ]

    column_mapping = {
        "datetime_0_timestamp": "timestamp",
        "pv_0_pv_prod_input": "pv_prod",
        "load_0_consumption_input": "consumption",
        "price_0_price_buy": "price_buy",
        "price_0_price_sell": "price_sell",
        "grid_0_grid_import": "grid_import",
        "grid_0_grid_export": "grid_export",
        "battery_0_soc": "soc",
        "battery_0_current_charge": "current_charge",
        "battery_0_charge_amount": "charge_amount",
        "battery_0_discharge_amount": "discharge_amount",
        "battery_0_reward": "wear_cost_battery",
        "balance_0_reward": "economic_balance_eur",
    }
    df.rename(
        columns={old: new for old, new in column_mapping.items() if old in df.columns},
        inplace=True,
    )

    if "cost_import_eur" not in df.columns and {"grid_import", "price_buy"}.issubset(df.columns):
        df["cost_import_eur"] = df["grid_import"] * df["price_buy"]

    if "revenue_export_eur" not in df.columns and {"grid_export", "price_sell"}.issubset(df.columns):
        df["revenue_export_eur"] = df["grid_export"] * df["price_sell"]

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

    # 1) Energie istantanee
    fig, ax = plt.subplots(figsize=(12, 5))
    control_batt = df["discharge_amount"] - df["charge_amount"] 
    control_grid = df["grid_import"] - df["grid_export"]
    ax.plot(df.index, df["consumption"], label="Load (kWh)", linewidth=2)
    ax.plot(df.index, df["pv_prod"], label="PV (kWh)", linewidth=2)
    ax.plot(df.index, control_batt, label="Battery Net Flow (kWh)", linewidth=1.8, linestyle="-.")
    ax.plot(df.index, control_grid, label="Grid Energy (kWh)", linewidth=1.8, linestyle="--")
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
    cumulative_import = df["grid_import"].cumsum()
    cumulative_export = df["grid_export"].cumsum()
    fig, ax1 = plt.subplots(figsize=(12, 5))
    ax1.bar(df.index, df["grid_import"], label="Import step (kWh)", color="tab:blue", alpha=0.45, width=0.025)
    ax1.bar(df.index, -df["grid_export"], label="Export step (kWh)", color="tab:orange", alpha=0.45, width=0.025)
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

    # 3) Prezzi
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(df.index, df["price_buy"], label="Price Buy (eur/kWh)", linewidth=2)
    ax.plot(df.index, df["price_sell"], label="Price Sell (eur/kWh)", linewidth=2)
    
    ax.set_title("Grid Prices Over Time")
    ax.set_ylabel("eur/kWh")
    ax.set_xlabel("Time")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.4)
    prices_path = f"{base_name}_prices.png"
    fig.tight_layout()
    fig.savefig(prices_path, dpi=160)
    plt.close(fig)

    # 4) Batteria: SOC e flussi
    battery_soc_pct = df["soc"]*100
    fig, ax1 = plt.subplots(figsize=(12, 5))
    ax1.plot(df.index, battery_soc_pct, color="tab:blue", label="SOC (%)", linewidth=2.2)
    ax1.set_ylabel("SOC [%]", color="tab:blue")
    ax1.tick_params(axis="y", labelcolor="tab:blue")
    ax1.grid(True, linestyle="--", alpha=0.4)

    ax2 = ax1.twinx()
    ax2.bar(df.index, df["charge_amount"], label="Charge (kWh)", color="tab:green", alpha=0.4, width=0.025)
    ax2.bar(df.index, -df["discharge_amount"], label="Discharge (kWh)", color="tab:red", alpha=0.4, width=0.025)
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
    wear_cost_battery = -df["wear_cost_battery"]
    fig, ax1 = plt.subplots(figsize=(12, 5))
    ax1.bar(df.index, df["cost_import_eur"], label="Import Cost (eur/step)", color="tab:blue", alpha=0.45, width=0.025)
    ax1.bar(df.index, df["revenue_export_eur"], label="Export Revenue (eur/step)", color="tab:orange", alpha=0.45, width=0.025)
    ax1.bar(df.index, wear_cost_battery, label="Wear cost battery (eur/step)", color="tab:green", alpha=0.45, width=0.025)

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



def compute_offline_tariff_vectors(ts_series, local_timezone, price_config):

    hr = ts_series.dt.tz_convert(local_timezone).dt.hour

    # List di condizioni e valori risultanti
    condlist = []
    buy_choices = []
    sell_choices = []

    # Itera sulle fasce definite nel file YAML
    for band_name, band_data in price_config.items():
        buy_val = float(band_data['buy'])
        sell_val = float(band_data['sell'])

        # Bande con ranges
        if 'ranges' in band_data and band_data['ranges'] is not None:
            band_conditions = None

            # Ogni range è [start_hour, end_hour]
            for start, end in band_data['ranges']:
                # Se l’utente usa in YAML range inclusivi (es. 18–20)
                # li interpretiamo come ore intere: start ≤ hr ≤ end
                condition = hr.between(start, end)
                band_conditions = condition if band_conditions is None else (band_conditions | condition)

            condlist.append(band_conditions)

        else:
            # Bande senza ranges → si assume valida per tutte le ore non coperte da altre fasce
            # Per evitare comportamenti non deterministici, creiamo una condizione placeholder;
            # verrà assegnata *solo se nessuna delle fasce precedenti è valida* dopo np.select.
            condlist.append(np.full(len(hr), True, dtype=bool))

        buy_choices.append(buy_val)
        sell_choices.append(sell_val)

    # np.select valuta i condlist in ordine: la prima condizione vera viene assegnata
    price_buy_vec = np.select(condlist, buy_choices).astype(float)
    price_sell_vec = np.select(condlist, sell_choices).astype(float)

    return price_buy_vec, price_sell_vec


def add_module_columns(df, mapping):
    """
    Aggiunge colonne extra al DataFrame preservandone la MultiIndex e l'ordine dei moduli.

    I nuovi campi vengono raggruppati accanto alle colonne del relativo modulo,
    così l'ispezione resta ordinata anche dopo l'aggiunta di grandezze derivate.
    """
    if not isinstance(df.columns, pd.MultiIndex):
        for column_key, values in mapping.items():
            df[column_key] = np.asarray(values)
        return df

    module_order = list(dict.fromkeys(df.columns.get_level_values(0)))

    for column_key, values in mapping.items():
        df.loc[:, column_key] = np.asarray(values)
        module_name = column_key[0] if isinstance(column_key, tuple) else column_key
        if module_name not in module_order:
            module_order.append(module_name)

    ordered_cols = []
    for module_name in module_order:
        ordered_cols.extend([col for col in df.columns if col[0] == module_name])

    df = df.loc[:, ordered_cols]
    return df