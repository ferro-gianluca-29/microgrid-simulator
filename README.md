# Microgrid Simulator EMS

Questo repository contiene uno script EMS (Energy Management System) che integra una simulazione `pymgrid` con dati realtime da Kafka e produce report energetici/economici e grafici automatici.

---

## Prerequisiti

- Python 3.10+
- Ambiente virtuale consigliato
- Broker Kafka con endpoint configurato in `consumer_class.py` (default: `http://localhost:50005/register/dc`)

---

## Installazione

```bash
python -m venv mio_env_ems
.\mio_env_ems\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

Per necessità di sviluppo avanzato esiste anche `requirements_full.txt`, ma non è richiesto per l’EMS.

---

## Configurazione

Le impostazioni principali sono in `params.yml`.

```yaml
battery:
  soc_min: 0.2
  ...

grid:
  max_import_power: 8
  max_export_power: 8

ems:
  kafka_topic: test_topic_661
  buffer_size: 96
  timezone: Europe/Rome
  steps: 5

  price_bands:
    peak:
      buy: 0.35
      sell: 0.12
      ranges:
        - [18, 20]     # intervalli orari
    standard:
      ...
    offpeak:
      ...
```

- `battery` e `grid` vengono letti da `microgrid_simulator.py`
- sezione `ems` controlla consumer Kafka, loop step e fasce prezzo (TOU) usate dallo script

---

## Esecuzione

Attiva l’ambiente e lancia lo script:

```bash
.\mio_env_ems\Scripts\activate
py ems_gui.py
```

Lo script:

1. Avvia un consumer Kafka in background
2. Costruisce la microgrid (`pymgrid`)
3. Per ogni step:
   - legge load/PV da Kafka
   - calcola prezzi TOU in base alla fascia oraria
   - applica un controllo rule-based
   - stampa un report completo su console
4. A fine simulazione:
   - salva i dati in `ems_results_YYYYMMDD_HHMMSS.csv`
   - genera cinque grafici (`_power`, `_grid`, `_prices`, `_battery`, `_economics`)
   - apre automaticamente i PNG con il viewer di sistema

Puoi modificare il numero di step (o gli altri parametri) direttamente in `params.yml` senza toccare il codice.

---

## Output

- CSV con tutti i campi step-by-step: load/PV da Kafka e microgrid, controlli, energia import/export, SOC, costi e reward.
- Grafici riepilogativi in PNG.
- Le stampe a console permettono un monitoraggio step-by-step in tempo reale.

NB: i file `ems_results_*.csv/png` sono ignorati da Git tramite `.gitignore`. Copia o rinomina ciò che ti serve prima di fare nuovi run se vuoi conservarli.

---

## Altri script

- `consumer_class.py`: simple wrapper basato su `confluent-kafka`
- `microgrid_simulator.py`: costruisce i moduli pymgrid partendo dal config YAML
- `requirements_full.txt`: lista estesa usata in precedenza (TensorFlow, Torch, ecc.)

---

## Troubleshooting

- Terminare sempre gli script con `Ctrl+C` o lasciare che completino `consumer.stop()` per evitare thread zombie.
- Se i grafici non si aprono automaticamente, verifica che l’estensione `.png` sia associata a un visualizzatore (su Windows `os.startfile` usa il default del sistema).
- Per modificare i costi/ricompense, interveni su `params.yml` (fasce prezzo, costi bilanciamento) o implementa un tuo `reward_shaping_func` in `MicrogridSimulator`.

---

Buona simulazione! 😊

