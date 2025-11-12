

import numpy as np
import pandas as pd

from src.pymgrid import Microgrid
from src.pymgrid.modules import GridModule, LoadModule, RenewableModule, BatteryModule

from pandasgui import show

import yaml


class MicrogridSimulator():

    def __init__(self, config_path, time_series, online):

        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.time_series = time_series
        self.online = online

        # Parametri batteria
        battery_cfg = self.config['battery']
        soc_min = battery_cfg['soc_min']
        soc_max = battery_cfg['soc_max']
        capacity = battery_cfg['capacity']
        power_max = battery_cfg['power_max']
        sample_time = battery_cfg['sample_time']

        self.nominal_capacity = capacity
        self.min_capacity = soc_min * capacity
        self.max_capacity = soc_max * capacity
        self.max_charge_per_step = power_max * sample_time
        self.max_discharge_per_step = power_max * sample_time
        self.battery_efficiency = battery_cfg['efficiency']
        self.init_soc = battery_cfg['init_soc']

        # Parametri rete
        grid_cfg = self.config['grid']
        self.max_grid_import_power = grid_cfg['max_import_power']
        self.max_grid_export_power = grid_cfg['max_export_power']

        self.present_grid_prices = np.array(grid_cfg['prices'])


    def build_microgrid(self):

        battery = BatteryModule(      
                              min_capacity = self.min_capacity, # [kWh]
                              max_capacity = self.max_capacity, # [kWh]
                              max_charge = self.max_charge_per_step, # [kWh]
                              max_discharge = self.max_discharge_per_step, # [kWh]
                              efficiency = self.battery_efficiency,
                              init_soc = self.init_soc      
                                                        )
        
        load_module = LoadModule(
        time_series=self.time_series,
        online=self.online,
        initial_time_series_value=0.0,
        )

        pv_module = RenewableModule(
            time_series=self.time_series,
            online=self.online,
            initial_time_series_value=0.0,
        )

        grid_module = GridModule(
                                    max_import = self.max_grid_import_power,
                                    max_export = self.max_grid_export_power, 
                                    time_series=self.time_series,
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

        return microgrid_df
        
        
