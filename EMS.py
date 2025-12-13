

class Rule_Based_EMS:
    def __init__(self, microgrid):

        self.microgrid = microgrid

    def control(self, load_kwh, pv_kwh, band=None, allow_night_grid_charge=False):
        """Controllo greedy che decide quanta energia usare da batteria e rete nello step corrente."""
        battery = self.microgrid.battery[0]
        e_grid = 0.0
        e_batt = 0.0

        tolerance = 1e-6  # Evita oscillazioni dovute alle approssimazioni floating point.
        max_discharge = max(0.0, min(battery.max_production, battery.max_discharge))    
        max_charge = max(0.0, min(battery.max_consumption, battery.max_charge))   
        band_normalized = (band or "").upper()               
        night_grid_mode = allow_night_grid_charge and band_normalized == 'OFFPEAK'     # Modalita' notte attiva o no

        if load_kwh > pv_kwh + tolerance:
            # Carico maggiore della produzione FV: scarica la batteria finché possibile e importa il resto.
            deficit = load_kwh - pv_kwh
            if night_grid_mode:
                # Di notte si preferisce importare dalla rete economica invece di scaricare la batteria.
                e_batt = 0.0
                e_grid = deficit
            else:
                discharge = min(deficit, max_discharge)     # Limita la scarica della batteria al massimo consentito
                e_batt = discharge
                e_grid = max(deficit - discharge, 0.0)      # Importa il resto dalla rete, se necessario
        elif pv_kwh > load_kwh + tolerance:
            # Surplus FV: carica la batteria entro i limiti e riversa l'eccesso verso la rete.
            surplus = pv_kwh - load_kwh
            charge = min(surplus, max_charge)          # Limita la carica della batteria al massimo consentito
            e_batt = -charge
            e_grid = -max(surplus - charge, 0.0)       # Esporta il resto alla rete, se necessario

        if night_grid_mode:
            # In fascia off-peak possiamo importare energia extra per ricaricare la batteria.
            available_headroom = max(0.0, battery.max_capacity - battery.current_charge)         # Spazio disponibile in batteria (kWh) per la carica
            already_planned_charge = max(0.0, -e_batt)                                           # Energia gia' pianificata per la carica in questo step (kWh)
            available_headroom = max(0.0, available_headroom - already_planned_charge)           # Spazio residuo in batteria dopo la carica pianificata

            extra_charge = min(max_charge, available_headroom)            # Energia extra che possiamo caricare in batteria (kWh), limitata dal max charge
            if extra_charge > tolerance:                # Evita di fare operazioni inutili se l'energia extra e' trascurabile
                e_batt -= extra_charge                  # Aggiunge la carica extra alla batteria (negativo per carica)
                e_grid += extra_charge                  # Aumenta l'import dalla rete per coprire la carica extra

        return e_batt, e_grid