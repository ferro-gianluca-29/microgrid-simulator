import os
import time
from collections import deque
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from consumer_class import KafkaConsumer
from microgrid_simulator import MicrogridSimulator


# =============================================================================
# Funzioni di supporto
# =============================================================================
def get_grid_prices(timestamp: datetime, price_config: dict):
    """Restituisce prezzi TOU e fascia oraria per lo step corrente usando la configurazione."""
    hour = timestamp.hour

    def hour_in_ranges(hr, ranges):
        for rng in ranges or []:
            start, end = rng
            if start <= hr <= end:
                return True
        return False

    # Ordine preferito: peak -> standard -> offpeak (default)
    for band_key in ("peak", "standard"):
        band_cfg = price_config.get(band_key)
        if band_cfg and hour_in_ranges(hour, band_cfg.get("ranges")):
            return (
                np.array([band_cfg.get("buy", 0.0), band_cfg.get("sell", 0.0), 0.0, 1.0]),
                band_key.upper(),
            )

    # Se non è rientrato in nessuna fascia, usa quella di fallback (offpeak o la prima disponibile)
    fallback_key = "offpeak" if "offpeak" in price_config else next(iter(price_config))
    fallback_cfg = price_config.get(fallback_key, {})
    return (
        np.array([fallback_cfg.get("buy", 0.0), fallback_cfg.get("sell", 0.0), 0.0, 1.0]),
        fallback_key.upper(),
    )


def rule_based_control(microgrid, load_kw, pv_kw):
    """Controller semplice per massimizzare autoconsumo."""
    battery = microgrid.battery[0]
    e_grid = 0.0
    e_batt = 0.0

    if load_kw > pv_kw:
        e_batt = battery.max_production
        deficit = load_kw - pv_kw - e_batt
        if deficit > 0:
            e_grid = deficit
    elif pv_kw > load_kw:
        e_batt = -battery.max_consumption
        surplus = pv_kw - load_kw - abs(e_batt)
        if surplus > 0:
            e_grid = -surplus

    return e_batt, e_grid


def deque_last(buffer: deque, default=None):
    """Ultimo elemento di una deque (o default se vuota)."""
    return buffer[-1] if len(buffer) else default


def print_step_report(step_idx, timestamp, band, kafka_load, kafka_pv, load_kw, pv_kw,
                      battery_info, grid_info, control, prices, economics):
    """Stampa leggibile per lo step corrente."""
    header = f"\n{'=' * 120}\nSTEP {step_idx} - {timestamp.strftime('%Y-%m-%d %H:%M:%S')} ({band})\n{'=' * 120}"
    print(header)

    print(f"Kafka Load/PV        : load={kafka_load:6.3f} kW | pv={kafka_pv:6.3f} kW")
    print(f"Microgrid Load/PV    : load={load_kw:6.3f} kW | pv={pv_kw:6.3f} kW")
    print(f"Controllo applicato  : battery={control['battery']:6.3f} kW | grid={control['grid']:6.3f} kW")

    print("\nBatteria:")
    print(f"  SOC              : {battery_info['soc_pct']:6.2f}%")
    print(f"  Charge/Discharge : +{battery_info['charge_amount']:6.3f} kWh | -{battery_info['discharge_amount']:6.3f} kWh")

    print("\nRete:")
    print(f"  Import/Export    : +{grid_info['import']:6.3f} kWh | -{grid_info['export']:6.3f} kWh")
    print(f"  Prezzi           : buy={prices['buy']:5.2f} EUR/kWh | sell={prices['sell']:5.2f} EUR/kWh")

    print("\nEconomia:")
    print(f"  Cost Import      : {economics['cost']:7.4f} EUR")
    print(f"  Revenue Export   : {economics['revenue']:7.4f} EUR")
    print(f"  Balance          : {economics['balance']:7.4f} EUR")
    print(f"  Reward (approx)  : {economics['reward']:7.4f}")


def plot_results(df: pd.DataFrame, base_name: str):
    """Genera grafici riepilogativi completi a partire dal DataFrame finale."""
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.sort_values("timestamp", inplace=True)
    df.set_index("timestamp", inplace=True)

    # 1) Potenze istantanee
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(df.index, df["mg_load_kw"], label="Load (kW)", linewidth=2)
    ax.plot(df.index, df["mg_pv_kw"], label="PV (kW)", linewidth=2)
    ax.plot(df.index, df["control_batt_kw"], label="Battery Power (kW)", linewidth=1.8, linestyle="-.")
    ax.plot(df.index, df["control_grid_kw"], label="Grid Power (kW)", linewidth=1.8, linestyle="--")
    ax.set_title("Power Flows")
    ax.set_ylabel("Power [kW]")
    ax.set_xlabel("Time")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.4)
    power_path = f"{base_name}_power.png"
    fig.tight_layout()
    fig.savefig(power_path, dpi=160)
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
    ax.plot(df.index, df["price_buy_eur_kwh"], label="Price Buy (€/kWh)", linewidth=2)
    ax.plot(df.index, df["price_sell_eur_kwh"], label="Price Sell (€/kWh)", linewidth=2)
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
    ax.set_ylabel("€/kWh")
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
    ax1.bar(df.index, df["cost_import_eur"], label="Import Cost (€/step)", color="tab:blue", alpha=0.45, width=0.025)
    ax1.bar(df.index, df["revenue_export_eur"], label="Export Revenue (€/step)", color="tab:orange", alpha=0.45, width=0.025)
    ax1.set_ylabel("€/step")
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

    return {
        "power": power_path,
        "grid": grid_path,
        "prices": prices_path,
        "battery": battery_path,
        "economics": economics_path,
    }


# =============================================================================
# Main
# =============================================================================
def main():
    with open("params.yml", "r") as cfg_file:
        full_config = yaml.safe_load(cfg_file)

    ems_cfg = full_config.get("ems", {})
    kafka_topic = ems_cfg.get("kafka_topic", "test_topic_661")
    buffer_size = ems_cfg.get("buffer_size", 96)
    timezone = ems_cfg.get("timezone", "Europe/Rome")
    simulation_steps = ems_cfg.get("steps", 5)
    price_config = ems_cfg.get("price_bands", {})
    if not price_config:
        price_config = {
            "peak": {"buy": 0.35, "sell": 0.12, "ranges": [[18, 20]]},
            "standard": {"buy": 0.28, "sell": 0.10, "ranges": [[7, 17], [21, 22]]},
            "offpeak": {"buy": 0.20, "sell": 0.08, "ranges": []},
        }

    print("\nInizializzazione Kafka Consumer...")
    consumer = KafkaConsumer(
        buffer_size=buffer_size,
        topic=kafka_topic,
        timezone=timezone,
    )
    consumer.start_background()

    print("Attesa primi dati...")
    while len(consumer.solar) == 0:
        time.sleep(0.5)

    print("Inizializzazione microgrid...")
    simulator = MicrogridSimulator(
        config_path="params.yml",
        time_series=None,
        online=True,
    )
    microgrid = simulator.build_microgrid()
    load_module = microgrid.modules["load"][0]
    pv_module = microgrid.modules["pv"][0]
    grid_module = microgrid.modules["grid"][0]
    microgrid.reset()

    results = []
    last_count = consumer.total_messages

    for step in range(1, simulation_steps + 1):
        while consumer.total_messages == last_count:
            time.sleep(0.5)
        last_count = consumer.total_messages

        kafka_load = deque_last(consumer.load, 0.0)
        kafka_pv = deque_last(consumer.solar, 0.0)
        timestamp = deque_last(consumer.timestamps, datetime.now())

        grid_prices, band = get_grid_prices(timestamp, price_config)

        microgrid.ingest_real_time_data(
            {"load": kafka_load, "pv": kafka_pv, "grid": [grid_prices]}
        )

        load_kw = load_module.current_load
        pv_kw = pv_module.current_renewable

        e_batt, e_grid = rule_based_control(microgrid, load_kw, pv_kw)
        control = {"battery": e_batt, "grid": e_grid}

        observations, reward, done, info = microgrid.step(
            {"battery": [e_batt], "grid": [e_grid]}, normalized=False
        )

        battery_module = microgrid.battery[0]
        battery_log = battery_module.log.iloc[-1] if len(battery_module.log) else {}
        grid_log = grid_module.log.iloc[-1] if len(grid_module.log) else {}

        battery_info = {
            "soc_pct": battery_module.soc * 100,
            "charge_amount": battery_log.get("charge_amount", 0.0),
            "discharge_amount": battery_log.get("discharge_amount", 0.0),
        }
        grid_info = {
            "import": grid_log.get("grid_import", grid_log.get("import", 0.0)),
            "export": grid_log.get("grid_export", grid_log.get("export", 0.0)),
        }

        prices = {"buy": grid_prices[0], "sell": grid_prices[1]}
        economics = {
            "cost": grid_info["import"] * prices["buy"],
            "revenue": grid_info["export"] * prices["sell"],
            "balance": grid_info["export"] * prices["sell"] - grid_info["import"] * prices["buy"],
            "reward": float(reward),
        }

        print_step_report(
            step,
            timestamp,
            band,
            kafka_load,
            kafka_pv,
            load_kw,
            pv_kw,
            battery_info,
            grid_info,
            control,
            prices,
            economics,
        )

        results.append(
            {
                "step": step,
                "timestamp": timestamp,
                "band": band,
                "kafka_load_kw": kafka_load,
                "kafka_pv_kw": kafka_pv,
                "mg_load_kw": load_kw,
                "mg_pv_kw": pv_kw,
                "control_batt_kw": e_batt,
                "control_grid_kw": e_grid,
                "grid_import_kwh": grid_info["import"],
                "grid_export_kwh": grid_info["export"],
                "price_buy_eur_kwh": prices["buy"],
                "price_sell_eur_kwh": prices["sell"],
                "cost_import_eur": economics["cost"],
                "revenue_export_eur": economics["revenue"],
                "economic_balance_eur": economics["balance"],
                "reward": economics["reward"],
                "battery_soc_pct": battery_info["soc_pct"],
                "battery_charge_kwh": battery_info["charge_amount"],
                "battery_discharge_kwh": battery_info["discharge_amount"],
            }
        )

    consumer.stop()
    print("\nConsumer fermato.")

    results_df = pd.DataFrame(results)
    csv_name = f"ems_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    results_df.to_csv(csv_name, index=False)

    base_name = csv_name.replace(".csv", "")
    plot_paths = plot_results(results_df, base_name)

    print("\n" + "-" * 120)
    print("RESOCONTO FINALE")
    print("-" * 120)
    print(f"Steps eseguiti             : {len(results_df)}")
    print(f"Grid import totale [kWh]   : {results_df['grid_import_kwh'].sum():8.3f}")
    print(f"Grid export totale [kWh]   : {results_df['grid_export_kwh'].sum():8.3f}")
    print(f"Costi import totali  [EUR] : {results_df['cost_import_eur'].sum():8.4f}")
    print(f"Ricavi export totali [EUR] : {results_df['revenue_export_eur'].sum():8.4f}")
    print(f"Bilancio economico   [EUR] : {results_df['economic_balance_eur'].sum():8.4f}")
    print(f"File CSV salvato           : {csv_name}")
    print("Grafici salvati:")
    for label, path in plot_paths.items():
        print(f"  {label:7s} -> {path}")

    print("\nApertura grafici...")
    for label, path in plot_paths.items():
        try:
            os.startfile(os.path.abspath(path))
        except OSError:
            print(f"  Impossibile aprire automaticamente {path}")


if __name__ == "__main__":
    main()
