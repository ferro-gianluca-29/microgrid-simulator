"""
Script per esplorare dati disponibili in ODA
"""
import requests
import json
import csv


def query_oda(topic, start=None, stop=None):
    """Richiede i dati ODA per un topic con intervallo opzionale."""
    url = "http://oda-nest.bologna.enea.it:50005/query"
    query = {"topic": topic}
    if start:
        query["start"] = start
    if stop:
        query["stop"] = stop
    print(f"Query: {query}")
    response = requests.post(url, json=query)
    if response.status_code == 404:
        print("Nessun dato trovato")
        return []
    response.raise_for_status()
    records = response.json()
    print(f"Ricevuti {len(records)} record")
    return records


def analizza_dati(records):
    if not records:
        return

    print("\nANALISI DATI")
    print("=" * 70)

    first = records[0]
    print("\nPrimo record:")
    print(f"  Timestamp: {first.get('timestamp')}")
    print(f"  Topic: {first.get('topic')}")
    print(f"  Generator ID: {first.get('generator_id')}")

    data_str = first.get('data', '{}')
    if isinstance(data_str, str):
        data_str = data_str.replace("'", '"')
        data = json.loads(data_str)
    else:
        data = data_str

    print("\n  Campi disponibili nel 'data':")
    for key, value in data.items():
        print(f"    - {key}: {value}")

    timestamps = [r["timestamp"] for r in records]
    print("\nPeriodo dati:")
    print(f"  Inizio: {min(timestamps)}")
    print(f"  Fine: {max(timestamps)}")
    print(f"  Totale record: {len(records)}")

    generator_ids = set(r.get("generator_id") for r in records)
    print("\nGenerator IDs:")
    for gid in generator_ids:
        count = sum(1 for r in records if r.get("generator_id") == gid)
        print(f"  - {gid}: {count} record")


def parse_data(cell):
    """Parsa il campo data in dizionario."""
    if isinstance(cell, str):
        try:
            return json.loads(cell.replace("'", '"'))
        except Exception:
            return {}
    if isinstance(cell, dict):
        return cell
    return {}


def esporta_csv_per_topic(topic, records):
    """Esporta i record di un topic in CSV locale."""
    if not records:
        print(f"Nessun record da esportare per {topic}")
        return

    filename = f"{topic}.csv"
    fieldnames = [
        "timestamp",
        "generator_id",
        "topic",
        "data_raw",
        "solar_value",
        "solar_unit",
        "load_value",
        "load_unit",
    ]
    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            data = parse_data(rec.get("data", {}))
            writer.writerow(
                {
                    "timestamp": rec.get("timestamp"),
                    "generator_id": rec.get("generator_id"),
                    "topic": rec.get("topic"),
                    "data_raw": rec.get("data"),
                    "solar_value": data.get("solar", {}).get("value"),
                    "solar_unit": data.get("solar", {}).get("unit"),
                    "load_value": data.get("load", {}).get("value"),
                    "load_unit": data.get("load", {}).get("unit"),
                }
            )
    print(f"CSV scritto: {filename} ({len(records)} righe)")


if __name__ == "__main__":
    print("Connessione a ODA...")
    resp = requests.get("http://oda-nest.bologna.enea.it:50005/register/dc")
    info = resp.json()

    print("\nODA attivo")
    print(f"Kafka endpoint: {info['KAFKA_ENDPOINT']}")
    print("\nTopic disponibili:")
    for topic in info["topics"]:
        print(f"  - {topic}")

    if info["topics"]:
        start = "2000-01-01T00:00:00Z"
        stop = None

        for topic_to_explore in info["topics"]:
            print(f"\nEsploro topic: {topic_to_explore}")
            records = query_oda(topic=topic_to_explore, start=start, stop=stop)
            if records:
                analizza_dati(records)
                esporta_csv_per_topic(topic_to_explore, records)
            else:
                print("\nNessun dato disponibile per il topic selezionato")
                print("Devi prima caricare dati con un Data Generator")
    else:
        print("\nNessun topic disponibile in ODA")
        print("Devi prima caricare dati con un Data Generator")
