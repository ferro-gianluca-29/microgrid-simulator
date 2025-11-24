"""
Consumer Kafka - Buffer Real-Time

1. Configura parametri
2. Connetti a Kafka
3. Ricevi dati e riempi buffer
4. Stampa statistiche quando pieno
"""

from confluent_kafka import Consumer
import json
import requests
import pandas as pd
from collections import deque


# ============================================================================
# CONFIGURAZIONE
# ============================================================================

ODA_URL = "http://oda-nest.bologna.enea.it:50005"
TOPIC = "test_topic_661"
BUFFER_SIZE = 96  # 24 ore (96 x 15min) simulate


# ============================================================================
# BUFFER (semplici deque, si aggiornano automaticamente)
# ============================================================================

timestamps = deque(maxlen=BUFFER_SIZE)
solar = deque(maxlen=BUFFER_SIZE)
load = deque(maxlen=BUFFER_SIZE)
total_messages = 0


# ============================================================================
# CONNESSIONE KAFKA
# ============================================================================

print("=" * 70)
print("  CONSUMER KAFKA - BUFFER REAL-TIME")
print("=" * 70)
print()

print(" Connessione a ODA...")
response = requests.get(f"{ODA_URL}/register/dc")      # Ottieni endpoint Kafka
kafka_endpoint = response.json()["KAFKA_ENDPOINT"]     # Estrai endpoint Kafka

consumer = Consumer({
    'bootstrap.servers': kafka_endpoint,
    'group.id': 'consumer_semplice',             # Identificatore del consumer group
    'auto.offset.reset': 'latest'                # Inizia a leggere dai messaggi più recenti
})

consumer.subscribe([TOPIC])
print(f" Connesso: {kafka_endpoint}")
print(f" Topic: {TOPIC}")
print(f" Buffer: {BUFFER_SIZE} timesteps (24h)\n")
print(" Streaming attivo...\n")


# ============================================================================
# LOOP PRINCIPALE
# ============================================================================

try:
    while True:
        
        # Ricevi messaggio
        msg = consumer.poll(1.0)       # Timeout di 1 secondo
        
        if msg is None:
            continue
        
        if msg.error():                              # Gestione errori messaggio
            print(f" Errore: {msg.error()}")
            continue
        
        # Parse messaggio
        try:
            data = json.loads(msg.value().decode('utf-8'))        # Decodifica JSON 
            timestamp = pd.to_datetime(data['timestamp'])         # Estrai timestamp
            dati = json.loads(data['data'])                       # Estrai dati interni
            
            s = max(0.0, float(dati['solar']['value']))           # Estrai solar dai dati
            l = max(0.0, float(dati['load']['value']))            # Estrai load dai dati
        
        except Exception as e:                                    # Gestione errori parsing
            print(f" Errore parsing: {e}")
            continue
        
        # Aggiungi a buffer
        timestamps.append(timestamp)              # Aggiungi timestamp al buffer
        solar.append(s)                           # Aggiungi solar al buffer
        load.append(l)                            # Aggiungi load al buffer
        total_messages += 1                       # Incrementa contatore messaggi
        
        # Stampa progresso
        print(f"[{total_messages:4d}] {timestamp.strftime('%Y-%m-%d %H:%M:%S')} | "          # Stampa timestamp
              f"Solar: {s:5.2f} kWh | Load: {l:5.2f} kWh | "                                   # Stampa valori
              f"Buffer: {len(solar):2d}/{BUFFER_SIZE}")                                      # Stampa stato buffer
        
        # Quando buffer è pieno, stampa statistiche
        if len(solar) >= BUFFER_SIZE:                       # Buffer pieno, calcola statistiche
            
            # Converti a DataFrame
            df = pd.DataFrame({                          # Crea DataFrame dai buffer perchè pandas non supporta deque
                'datetime': list(timestamps),
                'solar': list(solar),
                'load': list(load)
            })
            
            # Calcola statistiche
            solar_avg = df['solar'].mean()      # Media solar
            solar_max = df['solar'].max()       # Max solar
            load_avg = df['load'].mean()        # Media load
            load_max = df['load'].max()         # Max load
            
            # Stampa
            print(f"\n           Statistiche 24h:")
            print(f"         Solar: media {solar_avg:.2f} kWh, max {solar_max:.2f} kWh")       # Stampa statistiche solar di 96 timesteps
            print(f"         Load:  media {load_avg:.2f} kWh, max {load_max:.2f} kWh\n")       # Stampa statistiche load di 96 timesteps


except KeyboardInterrupt:              # Gestione interruzione manuale con Ctrl+C
    print("\n Interrotto\n")

finally:
    consumer.close()               # Chiudi connessione Kafka


# ============================================================================
# STATISTICHE FINALI (relative ai dati dell'ultimo buffer)
# ============================================================================

print("=" * 70)
print("  STATISTICHE FINALI")
print("=" * 70)
print(f"   Messaggi ricevuti: {total_messages}")          # Stampa numero totale messaggi ricevuti
print(f"   Buffer finale: {len(solar)} valori")           # Stampa numero valori nel buffer finale 

if len(solar) > 0:            # Se ci sono dati nel buffer
    
    # Salva buffer finale
    df_finale = pd.DataFrame({              # Crea DataFrame dai buffer perchè pandas non supporta deque
        'datetime': list(timestamps),
        'solar': list(solar),
        'load': list(load)
    })
    
    print(f"\n   Periodo: {df_finale['datetime'].min()} → {df_finale['datetime'].max()}")                    # Stampa periodo coperto dai dati dell'ultimo buffer
    print(f"   Solar: media {df_finale['solar'].mean():.2f} kWh, max {df_finale['solar'].max():.2f} kWh")      # Stampa statistiche solar dell'ultimo buffer
    print(f"   Load:  media {df_finale['load'].mean():.2f} kWh, max {df_finale['load'].max():.2f} kWh")        # Stampa statistiche load dell'ultimo buffer
    
    df_finale.to_csv('buffer_finale.csv', index=False)          # Salva buffer finale in CSV
    print(f"\n Salvato: buffer_finale.csv")                
