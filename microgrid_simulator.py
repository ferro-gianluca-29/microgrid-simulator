

import numpy as np
import pandas as pd

from src.pymgrid import Microgrid
from src.pymgrid.modules import GridModule, LoadModule, RenewableModule, BatteryModule
from src.pymgrid.modules.battery.transition_models import (
    LfpTransitionModel,
    NcaTransitionModel,
    NmcTransitionModel,
)

from pandasgui import show
import yaml

# Registra i costruttori YAML per le classi di transizione della batteria
from src.pymgrid.modules.battery.transition_models.unipi_transition_model import register_transition_model_yaml_constructors

register_transition_model_yaml_constructors()


class MicrogridSimulator():

    def __init__(self, config_path, online, load_time_series = None, pv_time_series = None, grid_time_series = None, battery_chemistry=None):

        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.online = online

        # Time Series

        self.load_time_series = load_time_series
        self.pv_time_series = pv_time_series
        self.grid_time_series = grid_time_series

        # Parametri batteria
        battery_cfg = self.config['battery']
        capacity = battery_cfg['capacity']
        power_max = battery_cfg['power_max']
        sample_time = battery_cfg['sample_time']
        self.state_of_health = battery_cfg.get('state_of_health', 1.0)  # Default 1.0 se non specificato

        # Chimica batteria o modello di transizione esplicito
        self.battery_chemistry = battery_chemistry or battery_cfg.get('chemistry') or battery_cfg.get('type') or 'generic'
        self.battery_transition_model = battery_cfg.get('transition_model')
        
        # Se il transition_model è definito, estrai la chimica dal nome della classe
        if self.battery_transition_model is not None:
            transition_class_name = self.battery_transition_model.__class__.__name__
            # Estrae la chimica dal nome: LfpTransitionModel -> LFP, NmcTransitionModel -> NMC, etc.
            if 'Lfp' in transition_class_name:
                self.battery_chemistry = 'LFP'
            elif 'Nmc' in transition_class_name:
                self.battery_chemistry = 'NMC'
            elif 'Nca' in transition_class_name:
                self.battery_chemistry = 'NCA'

        self.nominal_capacity = capacity
        self.max_charge_per_step = power_max * sample_time
        self.max_discharge_per_step = power_max * sample_time
        self.battery_efficiency = battery_cfg['efficiency']
        self.init_charge = battery_cfg['init_charge']

        # Parametri rete
        grid_cfg = self.config['grid']
        self.max_grid_import_power = grid_cfg['max_import_power']
        self.max_grid_export_power = grid_cfg['max_export_power']

        self.present_grid_prices = np.array(grid_cfg['prices'])


    def build_microgrid(self):

        transition_model = self.battery_transition_model
        if transition_model is None:
            chemistry_upper = str(self.battery_chemistry).upper()
            if chemistry_upper == 'LFP':
                transition_model = LfpTransitionModel(soh=self.state_of_health)
            elif chemistry_upper == 'NMC':
                transition_model = NmcTransitionModel(soh=self.state_of_health)
            elif chemistry_upper == 'NCA':
                transition_model = NcaTransitionModel(soh=self.state_of_health)
            # Otherwise, leave `transition_model` as None to use the default BatteryTransitionModel
        else:
            # Se il transition_model è già stato creato dal YAML, aggiorna il SOH se non è già stato specificato
            if hasattr(transition_model, 'soh') and transition_model.soh == 1.0:
                # Se il SOH è al valore di default, aggiornalo con il valore da params.yml
                transition_model.soh = self.state_of_health

        battery = BatteryModule(
                              min_capacity = 0, # [kWh]
                              max_capacity = self.nominal_capacity, # [kWh]
                              max_charge = self.max_charge_per_step, # [kWh]
                              max_discharge = self.max_discharge_per_step, # [kWh]
                              efficiency = self.battery_efficiency,
                              init_charge = self.init_charge,
                              battery_transition_model=transition_model
                                                        )
        
        load_module = LoadModule(
        time_series=self.load_time_series,
        online=self.online,
        initial_time_series_value=0.0,
        )

        pv_module = RenewableModule(
            time_series=self.pv_time_series,
            online=self.online,
            initial_time_series_value=0.0,
        )

        grid_module = GridModule(
                                    max_import = self.max_grid_import_power,
                                    max_export = self.max_grid_export_power, 
                                    time_series=self.grid_time_series,
                                    online=self.online,
                                    initial_time_series_value=self.present_grid_prices,
                                    normalized_action_bounds=( -self.max_grid_import_power, self.max_grid_import_power ))
        

        microgrid = Microgrid(  modules=[
                                    battery,
                                    ('load', load_module), 
                                    ('pv', pv_module), 
                                    grid_module
                                                ]     )
        
        return microgrid
        

    def get_simulation_log(self, microgrid):

        log = microgrid.log.copy()
        log.columns = ['{}_{}_{}'.format(*col) for col in log.columns]

        microgrid_df = microgrid.log[
            [
                ('load', 0, 'load_met'),
                ('pv', 0, 'renewable_used'),
                ('pv', 0, 'curtailment'),
                ('balancing', 0, 'loss_load'),
                ('battery', 0, 'soc'),
                ('battery', 0, 'current_charge'),
                ('battery', 0, 'discharge_amount'),
                ('battery', 0, 'charge_amount'),
                ('grid', 0, 'grid_import'),
                ('grid', 0, 'grid_export')  # opzionale
            ]
        ]

        return microgrid_df, log
    

    def sum_module_info(self, info_dict, module_name, key):
        """
        Somma un determinato campo di info per tutte le istanze del modulo richiesto.
        """
        total = 0.0
        for entry in info_dict.get(module_name, []):    # Itera su tutte le istanze del modulo
            if not isinstance(entry, dict):             # Salta se l'entry non e' un dizionario valido
                continue
            value = entry.get(key)                      # Prende il valore del campo specificato
            if value is None:                           # Salta se il campo non esiste
                continue
            try:
                total += float(value)                   # Aggiunge il valore convertito a float
            except (TypeError, ValueError):             # Salta se la conversione fallisce
                continue
        return total                                    # Restituisce il totale calcolato
        
        
