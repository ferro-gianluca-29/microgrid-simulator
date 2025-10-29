
import numpy as np
import pandas as pd

from pandasgui import show

from microgrid_simulator import MicrogridSimulator 


present_grid_prices = np.array([0.15, 0.05, 0.0, 1.0])


def test_online_real_time_simulation():
    #rng = np.random.default_rng(42)

    steps = 5
    
    simulator = MicrogridSimulator(config_path='params.yml', time_series = None, online = True)

    microgrid = simulator.build_microgrid()
    
    microgrid.reset()

    records = []
    for step in range(steps):
        #load_value = rng.uniform(0.0, 3.0)
        #pv_value = rng.uniform(0.0, 3.0)

        load_value = 2.3
        pv_value = 2

        records.append({'load_consumption': load_value, 'pv_production': pv_value})
        
        data = pd.DataFrame(records)

        
        microgrid.ingest_real_time_data({'load': load_value, 'pv': pv_value, 'grid': [present_grid_prices]})

        e_grid = 0

        e_batt = 1

        if pv_value + e_grid <= abs(e_batt):

            e_batt = abs(e_batt) - pv_value + e_grid

        else: e_batt = - (pv_value + e_grid - abs(e_batt))

        control = {"battery" : [e_batt] ,
                   "grid": [e_grid] 
           }

        observations, reward, done, info = microgrid.step(control, normalized = False)

 
    microgrid_df = simulator.get_simulation_log(microgrid)
    
    microgrid_df['load_consumption'] = data['load_consumption']
    microgrid_df['pv_production'] = data['pv_production']


    show(microgrid_df=microgrid_df)


test_online_real_time_simulation()













