import sys
import os
import json
import logging
import sys
import glob
from io import StringIO

from MG_SIMULATOR.MG import MG
from MG_SIMULATOR import ESS



# delete previous results_mg from the specific folder
folder_path = 'results_mg'
files = glob.glob(os.path.join(folder_path, '*'))
for file in files:
    if os.path.isfile(file):
        os.remove(file)


# set unit tests data (input and parameters)
test_data = {
    '1': [0, 0, 0.15, 1.00],
    '2': [1, 0, 0.15, 1.00],
    '3': [0, 1, 0.15, 1.00],
    '4': [0, 0, 0.95, 1.00],
    '5': [1, 0, 0.95, 1.00],
    '6': [0, 1, 0.95, 1.00],
    '7': [0, 0, 0.15, 0.00],
    '8': [1, 0, 0.15, 0.00],
    '9': [0, 1, 0.15, 0.00],
    '10': [0, 0, 0.95, 0.00],
    '11': [1, 0, 0.95, 0.00],
    '12': [0, 1, 0.95, 0.00],
    '13': [0, 0, 0.15, 0.50],
    '14': [1, 0, 0.15, 0.50],
    '15': [0, 1, 0.15, 0.50],
    '16': [0, 0, 0.95, 0.50],
    '17': [1, 0, 0.95, 0.50],
    '18': [0, 1, 0.95, 0.50],
    '19': [0, 0, 0.15, 1.00],
    '20': [8, 0, 0.15, 1.00],
    '21': [0, 8, 0.15, 1.00],
    '22': [0, 0, 0.95, 1.00],
    '23': [8, 0, 0.95, 1.00],
    '24': [0, 8, 0.95, 1.00]
}


def unit_test_mg(data, t_class, index):

    # extract input and parameters
    dataset = [data[f'{index}'][0]], [data[f'{index}'][1]]
    soe_0 = data[f'{index}'][2]
    alpha = data[f'{index}'][3]

    # load architectural data
    file_path = os.path.abspath('./data/data.json')
    with open(file_path, 'r') as file:
        data = json.load(file)

    # create the MG objects and simulate them
    tariffs = data['economic_params']
    simulation_data = data['simulation']
    n_mgs = 0
    if t_class == "A":
        n_mgs = 1
    elif t_class == "B":
        n_mgs = 2
    mg_costs = []
    revenues = []
    inv_costs = []
    ess_costs = []
    purch_costs = []
    no_pv_costs = []
    for i in range(n_mgs):
        mg_name = f"mg{i}"
        mg_data = data['architecture'][mg_name]
        # create the MG object
        mg = MG(tariffs, simulation_data, mg_data)
        mg.ESS.SoE_0 = soe_0
        mg.ESS.SoE = soe_0
        # simulate the MG
        print(f'[*CIPAR*] test script | Data for mg{i} start:')
        mg_costs.append(round(mg.simulate(dataset, alpha), 2))
        revenues.append(round(sum(mg.revenues), 2))
        # set revenues to 0 €, if one single mg is simulated (no REC)
        if t_class == "A":
            mg_costs[-1] = mg_costs[-1] + revenues[-1]
        inv_costs.append(round(sum(mg.inv_costs), 2))
        ess_costs.append(round(sum(mg.C_b_ks), 2))
        purch_costs.append(round(sum(mg.purch_costs), 2))
        no_pv_costs.append(round(sum(mg.no_pv_costs), 2))
        # print results_mg
        print(f'[*CIPAR*] test script | Total cost mg{i} = {mg_costs[i]} [€]')
        print(f'[*CIPAR*] test script | Revenues mg{i} = {revenues[i]} [€]')
        print(f'[*CIPAR*] test script | Investment costs mg{i} = {inv_costs[i]} [€]')
        print(f'[*CIPAR*] test script | ESS costs mg{i} = {ess_costs[i]} [€]')
        print(f'[*CIPAR*] test script | Purchase costs mg{i} = {purch_costs[i]} [€]')
        print(f'[*CIPAR*] test script | No PV costs mg{i} = {no_pv_costs[i]} [€]')
        print(f'[*CIPAR*] test script | Data for mg{i} end.')
        print(f'')



def test(t_cl):
    for test_index in range(len(test_data)):

        # configure the logger
        log_file_path = f'results_mg/test_#{t_cl}{test_index + 1}_results.txt'
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)
        # create file handler which logs even debug messages
        fh = logging.FileHandler(log_file_path)
        fh.setLevel(logging.DEBUG)
        # create console handler with a higher log level
        ch = logging.StreamHandler()
        ch.setLevel(logging.ERROR)
        # create formatter and add it to the handlers
        formatter = logging.Formatter('%(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        # add the handlers to the logger
        logger.addHandler(fh)
        logger.addHandler(ch)
        # redirect stdout to capture print statements
        original_stdout = sys.stdout
        sys.stdout = StringIO()

        try:
            # perform the test
            unit_test_mg(test_data, t_cl, test_index + 1)
            # write the captured stdout to the log file
            with open(log_file_path, 'a') as f:
                f.write(sys.stdout.getvalue())
        finally:
            # restore the original stdout
            sys.stdout = original_stdout
            # remove handlers from logger
            logger.removeHandler(fh)
            logger.removeHandler(ch)


# perform test
test('A')
test('B')






