"""
Generatore Kafka - Invio Dati Real-Time

1. Configura parametri
2. Registra a ODA
3. Carica CSV
4. Invia dati a Kafka ogni 15 secondi
"""

from pathlib import Path
from confluent_kafka import Producer
import pandas as pd
import time
import json
import requests
import pytz  # Per gestire fusi orari
from pytz import NonExistentTimeError, AmbiguousTimeError


# ============================================================================
# CONFIGURAZIONE
# ============================================================================

API_GATEWAY_URL = "http://localhost:50005"    # Indirizzo API Gateway ODA
TOPIC = "test_topic_661"                      # Topic Kafka
GENERATOR_ID = "casa_661"                     # Identificatore univoco del generatore

DELTA_T_SEC = 0.5  # Secondi tra un invio e l'altro (simula dati quartorari)
SAMPLE_TIME_HOURS = 0.25  # Durata dello step rappresentato dai campioni (15 minuti)
DATA_FILE = Path(__file__).resolve().parent / 'data' / 'processed_data_661_formatted.csv'  # CSV con potenze medie (kW) per intervallo

# FUSO ORARIO ITALIANO
TIMEZONE_ITALIA = pytz.timezone('Europe/Rome')  # CET/CEST

# ============================================================================
# REGISTRAZIONE A ODA
# ============================================================================

print("=" * 70)
print("  GENERATORE KAFKA SEMPLICE")
print("=" * 70)
print()

print(" Registrazione a ODA...")

response = requests.post(                   # Registra generatore a ODA
    f"{API_GATEWAY_URL}/register/dg",       # Endpoint registrazione generatore
    json={"topics": [TOPIC]},               # Topic di interesse
    timeout=10                              # Timeout richiesta
)

kafka_endpoint = response.json()["KAFKA_ENDPOINT"]       # Estrai endpoint Kafka

print(f" Registrato!")
print(f" Kafka endpoint: {kafka_endpoint}")


# ============================================================================
# CARICAMENTO CSV
# ============================================================================

print(f"\n Caricamento dati da {DATA_FILE}...")

df = pd.read_csv(DATA_FILE, parse_dates=['datetime'])         # Carica CSV in DataFrame con pandas e parse colonna timestamp


def normalize_timestamp(ts):
    if pd.isna(ts):
        return pd.NaT
    ts = pd.Timestamp(ts)
    if ts.tzinfo is not None:
        return ts.tz_convert(TIMEZONE_ITALIA)
    try:
        return ts.tz_localize(TIMEZONE_ITALIA, ambiguous=True, nonexistent='shift_forward')
    except NonExistentTimeError:
        adjusted = ts + pd.Timedelta(hours=1)
        return adjusted.tz_localize(TIMEZONE_ITALIA, ambiguous=True, nonexistent='shift_forward')
    except AmbiguousTimeError:
        return ts.tz_localize(TIMEZONE_ITALIA, ambiguous=True)


df['datetime'] = df['datetime'].apply(normalize_timestamp)
invalid_datetimes = df['datetime'].isna().sum()
if invalid_datetimes:
    print(f" ATTENZIONE: {invalid_datetimes} timestamp non validi saranno ignorati.")
    df = df.dropna(subset=['datetime']).reset_index(drop=True)

# Converte solar/load in numerici (potenze medie kW) e gestisce eventuali valori non validi
df['solar'] = pd.to_numeric(df['solar'], errors='coerce')
df['load'] = pd.to_numeric(df['load'], errors='coerce')
invalid_energy = df[['solar', 'load']].isna().sum().sum()
if invalid_energy:
    print(f" ATTENZIONE: trovati {int(invalid_energy)} valori energy non validi (solar/load); verranno ignorati.")
    df = df.dropna(subset=['solar', 'load']).reset_index(drop=True)

# Verifica colonne
required_columns = {'datetime', 'solar', 'load'}
missing_columns = required_columns.difference(df.columns)   # Trova colonne mancanti nel file CSV rispetto a quelle richieste

if missing_columns:           # Controlla colonne necessarie, altrimenti esci
    print(f" ERRORE: CSV deve avere colonne {', '.join(sorted(required_columns))}!")
    exit(1)

first_valid_idx = df['datetime'].first_valid_index()
if first_valid_idx is None:
    print(" ERRORE: nessun timestamp valido nel CSV!")
    exit(1)

start_timestamp = df.at[first_valid_idx, 'datetime']
print(f" Caricati {len(df)} record")


# ============================================================================
# CREAZIONE KAFKA PRODUCER
# ============================================================================

print(f"\n Connessione a Kafka...")

producer = Producer({                             # Crea Kafka Producer 
    'bootstrap.servers': kafka_endpoint,          # Endpoint Kafka
    'client.id': GENERATOR_ID                     # Identificatore univoco del generatore
})

print(" Producer creato")


# ============================================================================
# INVIO DATI
# ============================================================================

print(f"\n Avvio invio dati")
print(f"   Intervallo: {DELTA_T_SEC} secondi")         # Stampa intervallo di invio
print(f"   Topic: {TOPIC}")                            # Stampa topic
print(f"   Generator ID: {GENERATOR_ID}")              # Stampa generator ID
print(f"   Timestamp iniziale: {start_timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print(f"   Premi Ctrl+C per terminare\n")

iteration = 0                # Contatore invii
start_wallclock = time.time()     # Tempo inizio invio reale

try:
    
    for idx, row in df.iterrows():        # Itera righe DataFrame

        timestamp = row['datetime']       # Timestamp proveniente dal CSV
        if pd.isna(timestamp):
            print(f" ATTENZIONE: timestamp mancante alla riga {idx}, salto il record")
            continue

        # Leggi potenze medie (kW) e trasformale in energie per intervallo (kWh)
        solar_kw = max(0.0, float(row['solar']))
        load_kw = max(0.0, float(row['load']))
        solar_kwh = solar_kw * SAMPLE_TIME_HOURS
        load_kwh = load_kw * SAMPLE_TIME_HOURS

        iteration += 1                    # Incrementa contatore solo se invio effettuato
        
        # Crea pacchetto dati
        packet = {                                                          # Crea dizionario pacchetto come messaggio
            "timestamp": timestamp.isoformat(),                        # Timestamp in formato ISO 8601 dal CSV
            "generator_id": GENERATOR_ID,                                   # Identificatore generatore
            "topic": TOPIC,                                                 # Topic
            "data": json.dumps({                                            # Dati interni in JSON
                "solar": {"value": float(solar_kwh), "unit": "kWh"},        # Energia solar per intervallo
                "load": {"value": float(load_kwh), "unit": "kWh"}           # Energia load per intervallo
            })
        }
        
        # Invia a Kafka
        producer.produce(                                  # Invia messaggio
            TOPIC,                                         # Topic
            value=json.dumps(packet).encode('utf-8')       # Messaggio in formato JSON codificato in UTF-8
        )
        
        producer.poll(0)     # Processa callback (non blocca)
        
        # Stampa progresso
        print(f"[{iteration:4d}] {timestamp.strftime('%Y-%m-%d %H:%M:%S')} | "
              f"Solar: {solar_kw:6.2f} kW ({solar_kwh:5.2f} kWh) | "
              f"Load: {load_kw:6.2f} kW ({load_kwh:5.2f} kWh)")
        
        # Aspetta prima di inviare il prossimo
        time.sleep(DELTA_T_SEC)


except KeyboardInterrupt:                       # Gestione interruzione manuale con Ctrl+C
    print("\n\n  Generatore interrotto\n")

except Exception as e:                          # Gestione altri errori
    print(f"\n Errore: {e}\n")

finally:                                        # Viene sempre eseguito alla fine del blocco try
   
    print(" Invio messaggi rimanenti...")    
    producer.flush()                            # Invia messaggi rimanenti che non sono stati ancora inviati


# ============================================================================
# STATISTICHE FINALI
# ============================================================================

elapsed = time.time() - start_wallclock     # Finestra temporale invio dati (istante attuale - istante iniziale)

print("\n" + "=" * 70)
print("   STATISTICHE")
print("=" * 70)
print(f"   Record inviati: {iteration}/{len(df)}")
print(f"   Timestamp iniziale (CSV): {start_timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print(f"   Tempo totale: {elapsed:.1f} secondi")
print(f"   Throughput: {iteration/elapsed:.2f} record/sec")

