import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytz
import yaml

from ems_realtime_kafka import (
    build_microgrid,
    load_config,
    get_grid_prices,
    rule_based_control,
    sum_module_info,
    plot_results,
)


def normalize_timestamp(ts, timezone):
    """Converte un timestamp in un oggetto timezone-aware coerente con la simulazione."""
    if pd.isna(ts):
        return pd.NaT
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is None:
        # Gestisce ambiguità dovute al cambio ora legale
        return timezone.localize(stamp, ambiguous=True, nonexistent="shift_forward")
    return stamp.tz_convert(timezone)


def load_time_series(csv_path, timezone):
    """Carica il CSV offline e restituisce un DataFrame ordinato e tz-aware."""
    df = pd.read_csv(csv_path, parse_dates=["datetime"])
    required_columns = {"datetime", "solar", "load"}
    missing = required_columns.difference(df.columns)
    if missing:
        raise ValueError(f"Il CSV deve contenere le colonne {sorted(required_columns)} (mancano: {sorted(missing)})")

    df["datetime"] = df["datetime"].apply(lambda ts: normalize_timestamp(ts, timezone))
    df.dropna(subset=["datetime"], inplace=True)
    df.sort_values("datetime", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def read_sample_time_hours(params_path):
    """Recupera il sample time (in ore) dalla sezione battery di params.yml."""
    with open(params_path, "r", encoding="utf-8") as cfg_file:
        data = yaml.safe_load(cfg_file)
    return float(data["battery"].get("sample_time", 0.25))


def parse_args():
    parser = argparse.ArgumentParser(description="Esegue l'EMS offline utilizzando dati da CSV.")
    parser.add_argument("--params", default="params.yml", help="Percorso al file params.yml (default: %(default)s)")
    parser.add_argument("--csv", help="CSV alternativo da usare per la simulazione (default: ems.forecast_csv)")
    parser.add_argument("--steps", type=int, help="Override del numero di step da simulare (default: config.ems.steps)")
    parser.add_argument(
        "--enable-night-charge",
        action="store_true",
        help="Forza l'attivazione della ricarica da rete nelle fasce OFFPEAK indipendentemente dalla config.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    config = load_config(args.params)
    timezone = pytz.timezone(config["timezone"])
    csv_path = args.csv or config.get("forecast_csv")
    if not csv_path:
        raise ValueError("Specificare --csv oppure valorizzare ems.forecast_csv in params.yml")
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV non trovato: {csv_path}")

    sample_time_hours = read_sample_time_hours(args.params)
    price_config = config["price_bands"]
    night_charge_enabled = args.enable_night_charge or config.get("allow_night_grid_charge", False)
    max_steps = args.steps or config["steps"]

    dataset = load_time_series(csv_path, timezone)
    if max_steps:
        dataset = dataset.head(max_steps)

    simulator, microgrid = build_microgrid()
    if hasattr(microgrid, "enable_logging"):
        microgrid.enable_logging()  # Garantisce la raccolta log completa in modalità offline

    load_module = microgrid.modules["load"][0]
    pv_module = microgrid.modules["pv"][0]

    results = []

    for step, row in enumerate(dataset.itertuples(index=False), start=1):
        timestamp = row.datetime
        load_kw = max(0.0, float(row.load))
        pv_kw = max(0.0, float(row.solar))
        load_kwh = load_kw * sample_time_hours
        pv_kwh = pv_kw * sample_time_hours

        grid_prices, band = get_grid_prices(timestamp, price_config)
        microgrid.ingest_real_time_data({"load": load_kwh, "pv": pv_kwh, "grid": [grid_prices]})

        load_kwh_sim = load_module.current_load
        pv_kwh_sim = pv_module.current_renewable

        e_batt, e_grid = rule_based_control(
            microgrid,
            load_kwh_sim,
            pv_kwh_sim,
            band=band,
            allow_night_grid_charge=night_charge_enabled,
        )
        control = {"battery": e_batt, "grid": e_grid}

        observations, reward, done, info = microgrid.step({"battery": [e_batt], "grid": [e_grid]}, normalized=False)

        battery_module = microgrid.battery[0]
        grid_import = sum_module_info(info, "grid", "provided_energy")
        grid_export = sum_module_info(info, "grid", "absorbed_energy")
        battery_charge = sum_module_info(info, "battery", "absorbed_energy")
        battery_discharge = sum_module_info(info, "battery", "provided_energy")
        load_met = sum_module_info(info, "load", "absorbed_energy")
        renewable_used = sum_module_info(info, "pv", "provided_energy")
        curtailment = sum_module_info(info, "pv", "curtailment")
        loss_load_value = sum_module_info(info, "balancing", "loss_load_energy")

        actual_soc = 0.0
        if simulator.nominal_capacity > 0:
            actual_soc = np.clip(battery_module.current_charge / simulator.nominal_capacity, 0.0, 1.0)

        battery_info = {
            "soc_pct": actual_soc * 100.0,
            "current_charge": battery_module.current_charge,
            "charge_amount": battery_charge,
            "discharge_amount": battery_discharge,
        }
        grid_info = {"import": grid_import, "export": grid_export}
        energy_metrics = {
            "load_met": load_met if load_met > 0 else load_kwh_sim,
            "renewable_used": renewable_used if renewable_used > 0 else min(pv_kwh_sim, load_kwh_sim),
            "curtailment": curtailment,
            "loss_load": loss_load_value,
        }
        prices = {"buy": grid_prices[0], "sell": grid_prices[1]}
        economics = {
            "cost": grid_info["import"] * prices["buy"],
            "revenue": grid_info["export"] * prices["sell"],
            "balance": grid_info["export"] * prices["sell"] - grid_info["import"] * prices["buy"],
            "reward": float(reward),
        }

        results.append(
            {
                "step": step,
                "timestamp": timestamp,
                "band": band,
                "csv_load_kwh": load_kwh,
                "csv_pv_kwh": pv_kwh,
                "mg_load_kwh": load_kwh_sim,
                "mg_pv_kwh": pv_kwh_sim,
                "control_batt_kwh": control["battery"],
                "control_grid_kwh": control["grid"],
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

    results_df = pd.DataFrame(results)
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)
    timestamp_now = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_name = f"ems_offline_results_{timestamp_now}.csv"
    csv_path = output_dir / csv_name
    results_df.to_csv(csv_path, index=False)

    base_name = (output_dir / csv_name.replace(".csv", "")).as_posix()
    plot_results(results_df, base_name, config["timezone"])

    pymgrid_log = simulator.get_simulation_log(microgrid)
    pymgrid_log_path = output_dir / csv_name.replace("results", "pymgrid_log")
    pymgrid_log.to_csv(pymgrid_log_path, index=False)

    print("\nSimulazione offline completata.")
    print(f"Passi eseguiti                : {len(results_df)}")
    print(f"Risultati EMS                 : {csv_path}")
    print(f"Log PyMGrid                   : {pymgrid_log_path}")
    print(f"Grafici generati (base name)  : {base_name}")


if __name__ == "__main__":
    main()
