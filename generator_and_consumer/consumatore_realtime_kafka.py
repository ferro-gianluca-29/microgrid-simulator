from confluent_kafka import Consumer
import json
import requests
import pandas as pd
from collections import deque
import time
import os

# ============================================================================
# CONFIGURAZIONE
# ============================================================================

ODA_URL = "http://oda-nest.bologna.enea.it:50005"
TOPIC = "dhomus.aggregator.1"
BUFFER_SIZE = 960               # 24h simulati (96 x 15min)
CSV_UPDATE_INTERVAL = 960         # Salvataggio CSV ogni 50 messaggi
CSV_FILE = "misure_realtime.csv"

# ============================================================================
# BUFFER CIRCOLARE
# ============================================================================

timestamps = deque(maxlen=BUFFER_SIZE)
measurements = deque(maxlen=BUFFER_SIZE)
total_messages = 0

# ============================================================================
# CONNESSIONE KAFKA
# ============================================================================

print("=" * 70)
print("  CONSUMER KAFKA - REAL-TIME + CSV UPDATE")
print("=" * 70)

print(" Connessione a ODA...")
response = requests.get(f"{ODA_URL}/register/dc")
kafka_endpoint = response.json()["KAFKA_ENDPOINT"]

consumer = Consumer({
    'bootstrap.servers': kafka_endpoint,
    'group.id': 'consumer_realtime',
    'auto.offset.reset': 'earliest'
})

consumer.subscribe([TOPIC])
print(f" Connesso: {kafka_endpoint}")
print(f" Topic: {TOPIC}")
print(" Streaming attivo...\n")

# ============================================================================
# LOOP PRINCIPALE
# ============================================================================

try:
    while True:

        msg = consumer.poll(0.5)
        if msg is None or msg.error():
            continue

        # Parse top-level
        data = json.loads(msg.value().decode('utf-8'))
        timestamp = data['timestamp']
        inner = json.loads(data['data'])

        # Stampa misure disponibili
        print(f"\n[{total_messages+1}] {timestamp}")
        for key, obj in inner.items():
            print(f"  {key}: {obj['value']} {obj['unit']}")

        # Costruisci record
        record = {"timestamp": timestamp}
        for key, obj in inner.items():
            record[key] = obj["value"]

        # Aggiorna buffer
        timestamps.append(timestamp)
        measurements.append(record)
        total_messages += 1

        # Salvataggio CSV periodico
        if total_messages % CSV_UPDATE_INTERVAL == 0:
            df = pd.DataFrame(measurements)
            if os.path.exists(CSV_FILE):
                df.to_csv(CSV_FILE, mode='w', index=False)
            else:
                df.to_csv(CSV_FILE, index=False)
            print(f"\n ✅ CSV aggiornato ({CSV_FILE}) con {len(df)} righe\n")

        # Buffer pieno → statistiche
        if len(measurements) == BUFFER_SIZE:
            df = pd.DataFrame(measurements)
            print("\n=== STATISTICHE SU 24H ===")
            for col in df.columns:
                if col != "timestamp":
                    print(f"{col}: media={df[col].mean():.2f}  max={df[col].max():.2f}")

except KeyboardInterrupt:
    print("\n Interrotto\n")

finally:
    consumer.close()

print("=" * 70)
print("  STATISTICHE FINALI")
print("=" * 70)
print(f"  Messaggi totali: {total_messages}")

if len(measurements) > 0:
    df_final = pd.DataFrame(measurements)
    df_final.to_csv(CSV_FILE, index=False)
    print(f" ✅ CSV salvato definitivamente: {CSV_FILE}")
