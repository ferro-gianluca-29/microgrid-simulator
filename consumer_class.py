"""
Kafka Consumer Classe
"""

from confluent_kafka import Consumer
import json
import requests
import pandas as pd
from collections import deque
import threading
import time
import pytz


class KafkaConsumer:
    """
    Consumer Kafka con buffer rolling.
    
    Uso:
        consumer = KafkaConsumer(buffer_size=96, topic="test_topic", timezone='Europe/Rome')        # Crea consumer con i tre parametri settabili
        consumer.start_background()                                                                 # Avvia in background
        df = consumer.get_data()                                                                    # Prendi dati come DataFrame
    """
    
    def __init__(self, buffer_size=96, topic="test_topic_661", timezone='Europe/Rome'):
        """Crea consumer con parametri configurabili"""
        
        self.buffer_size = buffer_size
        self.topic = topic
        
        # TIMEZONE
        self.timezone = pytz.timezone(timezone)

        # Buffer (deque semplici)
        self.timestamps = deque(maxlen=buffer_size)
        self.solar = deque(maxlen=buffer_size)
        self.load = deque(maxlen=buffer_size)
        self.total_messages = 0
        
        # Kafka
        self.consumer = None         # Tipo: Consumer
        self.running = False         # Flag esecuzione
        self.thread = None           # Riferimento al thread di polling
        
        print(f" Consumer creato: buffer={buffer_size}, topic={topic}")
    
    
    def connect(self):
        """Connetti a Kafka"""
        
        response = requests.get("http://localhost:50005/register/dc")     # Ottieni endpoint Kafka
        kafka_endpoint = response.json()["KAFKA_ENDPOINT"]                # Estrai endpoint Kafka
        
        self.consumer = Consumer({                                  # Configurazione consumer
            'bootstrap.servers': kafka_endpoint,                    # Endpoint Kafka
            'group.id': 'consumer_classe',                          # ID gruppo consumer
            'auto.offset.reset': 'latest'                           # Inizia a leggere dai messaggi più recenti
        })
        
        self.consumer.subscribe([self.topic])                       # Iscriviti al topic
        print(f" Connesso a Kafka: {kafka_endpoint}")
    
    
    def start_background(self):
        """Avvia consumer in background (non blocca)"""
        
        self.connect()                        # Connetti a Kafka
        self.running = True                   # Imposta flag esecuzione
        
        thread = threading.Thread(target=self._loop, daemon=False)      # Crea thread in background
        thread.start()                                                  # Avvia thread
        self.thread = thread
        
        print(" Consumer in background")
    
    
    def _loop(self):
        """Loop interno che riceve messaggi (privato)"""
        
        while self.running:                     # Finché il consumer è attivo (flag True)
            
            # Ricevi messaggio
            msg = self.consumer.poll(1.0)       # Timeout 1 secondo
            
            if msg is None or msg.error():      # Nessun messaggio o errore
                continue
            
            # Parse messaggio
            try:
                data = json.loads(msg.value().decode('utf-8'))     # Decodifica JSON
                timestamp = pd.to_datetime(data['timestamp'])      # Estrai timestamp

                # Converti in timezone italiano se non lo è già
                if timestamp.tzinfo is None:
                    # Se naive, assume UTC e converti
                    timestamp = pytz.utc.localize(timestamp).astimezone(self.timezone)
                else:
                    # Se già ha timezone, converti
                    timestamp = timestamp.astimezone(self.timezone)

                dati = json.loads(data['data'])                    # Estrai dati interni
                
                s = max(0.0, float(dati['solar']['value']))        # Estrai valore solar
                l = max(0.0, float(dati['load']['value']))         # Estrai valore load
                
                # Aggiungi a buffer
                self.timestamps.append(timestamp)             # Aggiungi timestamp
                self.solar.append(s)                          # Aggiungi solar
                self.load.append(l)                           # Aggiungi load
                self.total_messages += 1                      # Incrementa contatore messaggi ricevuti
                
            except:                           # Errore nel parsing del messaggio
                continue
    
    
    def get_data(self):
        """Restituisci dati buffer come DataFrame"""
        
        return pd.DataFrame({                       # Crea DataFrame pandas con i dati del buffer
            'datetime': list(self.timestamps),      # Timestamp come lista
            'solar': list(self.solar),              # Solar come lista
            'load': list(self.load)                 # Load come lista
        })
    
    
    def is_ready(self):                                 
        """Buffer è pieno?"""
        return len(self.solar) >= self.buffer_size     # Verifica se il buffer è pieno (solar usato come riferimento)
    
    
    def stop(self):
        """Ferma consumer"""
        self.running = False                    # Imposta flag esecuzione a False per fermare il loop
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3.0)       # Attendi che il thread termini
        if self.consumer:                       # Se il consumer esiste
            self.consumer.close()               # Chiudi connessione Kafka
            self.consumer = None
