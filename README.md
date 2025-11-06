# Microgrid Simulator EMS

This project delivers an Energy Management System that consumes realtime (or emulated) data from Kafka, feeds the `pymgrid` microgrid model, applies a rule-based controller focused on self-consumption, and generates detailed energy/economic reports (console, CSV, charts).

---

## 1. Clone and environment setup

```bash
# Clone the repository and move into the project folder
git clone <URL_REPO> microgrid-simulator
cd microgrid-simulator

# Optional: switch to the working branch
git checkout Alessio

# Create and activate a virtual environment
python -m venv mio_env_ems
# Windows PowerShell
.\mio_env_ems\Scripts\activate
# macOS / Linux
source mio_env_ems/bin/activate

# Upgrade pip and install core dependencies
pip install --upgrade pip
pip install -r requirements.txt

# For advanced ML/RL features you can also install:
# pip install -r requirements_full.txt
```

### External requirements
- Python 3.10 or newer
- Kafka broker reachable from this machine. The default registration endpoint is defined in `generator_and_consumer/consumer_class.py` (`http://localhost:50005/register/dc`). Make sure the topic set in `params.yml` is available and publishes load/PV measurements.

---

## 2. Key files

| File | Description |
|------|-------------|
| `ems_realtime_kafka.py` | Main script that ties Kafka, the simulator and the reporting pipeline. |
| `params.yml` | Configuration for battery, grid, EMS parameters, Kafka topic and TOU price bands. |
| `generator_and_consumer/consumer_class.py` | Kafka consumer wrapper with `deque` buffers for load, PV and timestamps. |
| `microgrid_simulator.py` | Builds `pymgrid` modules (battery, grid, load, PV, balancing) from the YAML config. |
| `ems_realtime_kafka_guide.txt` | Extended documentation of the current flow for reference. |

---

## 3. Configuration (`params.yml`)

The entire simulation is driven by this file.

### Battery
```yaml
battery:
  soc_min: 0.2        # minimum SOC (0-1)
  soc_max: 1.0        # maximum SOC
  capacity: 10.0      # nominal capacity in kWh
  power_max: 3.0      # max charge/discharge power in kW
  sample_time: 0.25   # step duration in hours (0.25 = 15 minutes)
  efficiency: 0.95    # round-trip efficiency
  init_soc: 0.25      # initial SOC (25%)
```

### Grid
```yaml
grid:
  max_import_power: 8
  max_export_power: 8
  prices: [0.3, 0.1, 0.0, 1.0]   # safety fallback (buy, sell, ...)
```

### EMS / Kafka / TOU price bands
```yaml
ems:
  kafka_topic: test_topic_661
  buffer_size: 96               # deque length (96 steps = 24h with 15-minute steps)
  timezone: Europe/Rome
  steps: 96                     # number of simulation steps
  price_bands:
    peak:
      buy: 0.35
      sell: 0.12
      ranges:
        - [18, 20]
    standard:
      buy: 0.28
      sell: 0.10
      ranges:
        - [7, 17]
        - [21, 22]
    offpeak:
      buy: 0.20
      sell: 0.08
      ranges: []
```

> Reduce `steps` for quick tests, change `kafka_topic` if you need to read from another stream, or edit `price_bands` to experiment with new tariffs. Every change takes effect at the next launch of `ems_realtime_kafka.py`.

---

## 4. Running the simulation

1. Start or connect to the Kafka broker and make sure the configured topic publishes tuples `(load, pv, timestamp)`.
2. Activate the virtual environment (see section 1).
3. Run the EMS:
   ```bash
   py ems_realtime_kafka.py      # Windows
   # or
   python ems_realtime_kafka.py  # macOS/Linux
   ```
4. For each step the script will:
   - pull the latest load/PV values and timestamp from Kafka,
   - compute the current TOU price band,
   - update the `pymgrid` microgrid state with realtime data,
   - apply the rule-based control (discharge if load > PV, charge if PV > load),
   - gather metrics from all modules (load met, curtailment, loss load, battery state, grid import/export),
   - print a full Step Report to the console.
5. At the end of the run it will:
   - save a CSV `ems_results_YYYYMMDD_HHMMSS.csv` containing all step fields,
   - generate five PNG charts (`_power`, `_grid`, `_prices`, `_battery`, `_economics`),
   - try opening the charts with the OS default image viewer (Windows uses `os.startfile`).

CSV/PNG outputs are ignored by Git (`.gitignore`). Move or rename them if you want to keep results between runs.

---

## 5. Understanding the outputs

- **Console**: realtime log with Kafka readings, applied actions, energy metrics (load_met, renewable_used, curtailment, loss_load), battery SOC/charge and economics (cost, revenue, balance, reward).
- **CSV**: step-by-step dataset for post-processing (Excel, pandas). Includes fields like `battery_current_charge_kwh`, `grid_import_kwh`, `economic_balance_eur`, `reward`, price bands and more.
- **Charts**:
  - `*_power.png`: load, PV, battery and grid power profiles.
  - `*_grid.png`: step energy import/export and cumulative totals.
  - `*_prices.png`: buy/sell prices with highlighted TOU bands.
  - `*_battery.png`: SOC evolution and charge/discharge energy per step.
  - `*_economics.png`: step costs/revenues and cumulative balance.

---

## 6. Common customisations

- **Tariffs and TOU bands**: edit `ems.price_bands` in `params.yml`.
- **Simulation length**: change `ems.steps`.
- **Battery/grid limits**: tweak the `battery` and `grid` sections (capacity, power limits, initial SOC).
- **Control strategy**: replace `rule_based_control` in `ems_realtime_kafka.py` with your own logic (MPC, RL, etc.), keeping the control dictionary structure (`{"battery": [...], "grid": [...]}`).
- **Additional metrics**: use the helper `get_logger_last` to read extra fields from `pymgrid` module loggers and include them in console output or CSV.
- **Alternative data source**: if Kafka is unavailable, populate the consumer deques manually or adapt `generator_and_consumer/consumer_class.py` to read from files.

---

## 7. Troubleshooting

- **Logger length mismatches**: ensure you are on the latest version (uses `get_logger_last`) and that the microgrid is reset before each new run.
- **Charts do not open automatically**: associate the `.png` extension with an image viewer; files are still saved in the project root.
- **Kafka topic empty**: double-check endpoint and credentials in `generator_and_consumer/consumer_class.py` and verify the upstream producer.
- **Early interruption**: press `Ctrl+C`; the script will still call `consumer.stop()` to cleanly stop the background thread.

---

## 8. Contributing

1. Create a dedicated branch (`git checkout -b feature/...`).
2. Always run at least one simulation and `py -m py_compile ems_realtime_kafka.py` before committing.
3. Update `README.md` and/or `ems_realtime_kafka_guide.txt` if you change the workflow.
4. Open a pull request against the relevant branch (e.g. `Alessio`).

---

Happy simulating!
