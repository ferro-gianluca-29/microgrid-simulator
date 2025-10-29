
import numpy as np
import pandas as pd

from pandasgui import show

from microgrid_simulator import MicrogridSimulator 

present_grid_prices = np.array([0.15, 0.05, 0.0, 1.0])


def test_online_real_time_simulation():
    #rng = np.random.default_rng(42)

    steps = 2
    
    simulator = MicrogridSimulator(config_path='params.yml', time_series = None, online = True)

    microgrid = simulator.build_microgrid()

    load_module = microgrid.modules['load'][0]
    pv_module = microgrid.modules['pv'][0]
    
    microgrid.reset()

    records = []


    for _ in range(steps):
        #load_value = rng.uniform(0.0, 3.0)
        #pv_value = rng.uniform(0.0, 3.0)

        load_value = 6
        pv_value = 2

    
        microgrid.ingest_real_time_data({'load': load_value, 'pv': pv_value, 'grid': [present_grid_prices]})

        load_mg = load_module.current_load
        pv_mg = pv_module.current_renewable

        records.append({'load_consumption': load_mg, 'pv_production': pv_mg})
        data_log = pd.DataFrame(records)

        e_grid = 0

        e_batt = 0

        ################# RULE-BASED CONTROL (SELF CONSUMPTION) ###############################

        ####### DEFICIT (LOAD > PV) 

        if load_mg > pv_mg:
            # discharge the battery with energy available
            e_batt =  microgrid.battery[0].max_production

            # if battery energy available is not enough, import from grid
            if load_mg - pv_mg - e_batt > 0:
                e_grid = load_mg - pv_mg - e_batt
            else: e_grid = 0 


        ####### SURPLUS (PV > LOAD) 

        if pv_mg > load_mg:
           # charge the battery until reaches maximum charge
           e_batt =  -(microgrid.battery[0].max_consumption)

           # if battery is fully charged and there is residual PV energy, export to grid
           if pv_mg - load_mg - abs(e_batt) > 0:
               e_grid = -(pv_mg - load_mg - abs(e_batt))
           else: e_grid = 0 


        control = {"battery" : [e_batt] ,
                   "grid": [e_grid] 
           }
        
        ########################################################
        
        observations, reward, done, info = microgrid.step(control, normalized = False)


    microgrid_df = simulator.get_simulation_log(microgrid)
    
    microgrid_df['load_consumption'] = data_log['load_consumption']
    microgrid_df['pv_production'] = data_log['pv_production']


    show(microgrid_df=microgrid_df)


test_online_real_time_simulation()













