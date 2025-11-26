#from PV.PV import PV


from ESS.ESS_linear import ESS_linear
from ESS.ESS_empirical import ESS_empirical
import logging

from MG_SIMULATOR.ESS import ESS



class MG:

    def __init__(self, tariffs, simulation_data, mg_data, ess_model):
        min_2_h = 0.0166
        self.delta_t = simulation_data["delta_t"] * min_2_h
        self.PV = PV(mg_data["pv_plant"]["pv_price"])
        attrs = [mg_data["ESS"]["Q"],
                mg_data["ESS"]["P_S_max"],
                mg_data["ESS"]["a"],
                mg_data["ESS"]["b"],
                mg_data["ESS"]["B"],
                mg_data["ESS"]["eta"],
                mg_data["ESS"]["SoE_0"],
                mg_data["ESS"]["V_n"],
                mg_data["ESS"]["SoE_min"],
                mg_data["ESS"]["SoE_max"],
                mg_data["ESS"]["Q_n"],
                mg_data["ESS"]["C_n"],
                mg_data["ESS"]["eta_inverter"],
                mg_data["ESS"]["Ns_batt"],
                mg_data["ESS"]["Np_batt"],
                mg_data["ESS"]["SoC_0"],
                mg_data["ESS"]["T"]
                ]
        self.ess_model = ess_model
        if self.ess_model == "linear":
            self.ESS = ESS_linear(*attrs)
        if self.ess_model == "empirical":
            self.ESS = ESS_empirical(*attrs)
        if self.ess_model == "lfp":
            self.ESS = ESS_empirical(*attrs)
        if self.ess_model == "nca":
            self.ESS = ESS_empirical(*attrs)
            self.ESS.eta_inverter
        if self.ess_model == "nmc":
            self.ESS = ESS_empirical(*attrs)
        self.power_flows = {
            "p_L": [],
            "p_GL": [],
            "p_GL_S": [],
            "p_GL_N": []
        }
        self.tariffs = tariffs
        self.SoE_values = []
        self.alpha_values = []
        self.cost_values = []
        self.revenues = []
        self.inv_costs = []
        self.C_b_ks = []
        self.purch_costs = []
        self.oper_costs = []
        self.no_pv_costs = []

    '''
    Simulates the Microgrid for a single timeslot.
    :param dataset: The dataset.
    :type dataset: list
    :param alpha: The EMS decision.
    :type alpha: float
    '''
    def simulate(self, dataset, alpha):
        for tsl in range(len(dataset[0])):
            p_GL_S = 0
            p_GL_N = 0
            ess_losses = 0
            # register the initial default SoE value
            if tsl == 0:
                self.SoE_values.append(self.ESS.SoE_0)
            logging.debug(f'[*CIPAR*] MG Class | MG simulation starts...')
            logging.debug(f'[*CIPAR*] MG Class | SoE_before={self.SoE_values[-1]}')
            p_G = dataset[0][tsl]
            p_L = dataset[1][tsl]
            p_GL = p_G - p_L
            p_GL = round(p_GL, 2)
            Q_res = round(self.ESS.Q * (self.ESS.SoE_max - self.ESS.SoE), 2)
            e_S_res = round(self.ESS.Q * (self.ESS.SoE - self.ESS.SoE_min), 2)
            # manage the case of equilibrium between generation and consumption
            if p_GL == 0:
                logging.debug('[*CIPAR*] MG Class | Equilibrium between generation and load')
                p_GL_S = 0
                p_GL_N = 0
                self.register(p_L, p_GL, p_GL_S, p_GL_N, alpha)
            # manage the case of overproduction
            elif p_GL > 0:
                # the ESS has enough space for energy excess and its max power limit is not exceeded
                if p_GL * self.delta_t <= Q_res and p_GL <= self.ESS.p_S_max:
                    logging.debug('[*CIPAR*] MG Class | Generation excess - ESS enough space - ESS under Pmax')
                    p_GL_S = round(alpha * p_GL, 2) * self.ESS.eta
                    ess_losses = + round(alpha * p_GL, 2) * (1 - self.ESS.eta)
                    p_GL_N = p_GL - p_GL_S - ess_losses
                    excess = self.ESS.update_SoE_ch(p_GL_S, p_GL, self.delta_t)
                    # charge the ESS as far as it is possible and give the rest to the Main Grid
                    if excess > 0:
                        p_GL_S = p_GL_S - excess / self.delta_t
                        p_GL_N = p_GL - p_GL_S
                    self.register(p_L, p_GL, p_GL_S, p_GL_N, alpha)
                # the ESS has not enough space for energy excess and its max power limit is not exceeded
                elif p_GL * self.delta_t > Q_res and p_GL <= self.ESS.p_S_max:
                    logging.debug('[*CIPAR*] MG Class | Generation excess - ESS not enough space - ESS under Pmax')
                    p_GL_S = round(alpha * Q_res / self.delta_t, 2) * self.ESS.eta
                    p_GL_N = p_GL - p_GL_S
                    excess = self.ESS.update_SoE_ch(p_GL_S, p_GL, self.delta_t)
                    # charge the ESS as far as it is possible and give the rest to the Main Grid
                    if excess > 0:
                        p_GL_S = p_GL_S - excess / self.delta_t
                        p_GL_N = p_GL - p_GL_S
                    self.register(p_L, p_GL, p_GL_S, p_GL_N, alpha)
                # the ESS has not enough space for energy excess and its max power limit is exceeded
                elif ((p_GL * self.delta_t > Q_res and p_GL > self.ESS.p_S_max)
                        or (p_GL * self.delta_t <= Q_res and p_GL > self.ESS.p_S_max)):
                    logging.debug('[*CIPAR*] MG Class | Generation excess - ESS not enough space - ESS over Pmax')
                    logging.debug('[*CIPAR*] MG Class | Generation excess - ESS enough space - ESS over Pmax')
                    # check if, at its max power, the ESS has enough remaining capacity
                    if (alpha * self.ESS.p_S_max * self.delta_t * self.ESS.eta) <= Q_res:
                        p_GL_S = alpha * self.ESS.p_S_max
                    else:
                        p_GL_S = 0
                    p_GL_N = p_GL - p_GL_S
                    excess = self.ESS.update_SoE_ch(p_GL_S, p_GL, self.delta_t)
                    # charge the ESS as far as it is possible and give the rest to the Main Grid
                    if excess > 0:
                        p_GL_S = p_GL_S - excess / self.delta_t
                        p_GL_N = p_GL - p_GL_S
                    self.register(p_L, p_GL, p_GL_S, p_GL_N, alpha)
                else:
                    raise ValueError('[*CIPAR*] MG Class | Case not covered!')
            # manage the case of underproduction
            elif p_GL < 0:
                # the ESS has enough energy to provide and its max power limit is not exceeded
                if (alpha * abs(p_GL * self.delta_t)/self.ESS.eta) <= e_S_res and abs(p_GL) <= self.ESS.p_S_max:
                    logging.debug('[*CIPAR*] MG Class | Generation lack - ESS enough energy - ESS under Pmax')
                    p_GL_S = -round(alpha * abs(p_GL), 2) / self.ESS.eta
                    ess_losses =  round(alpha * p_GL, 2) * (1 - self.ESS.eta)
                    p_GL_N = p_GL - p_GL_S - ess_losses
                    lack = self.ESS.update_SoE_dch(p_GL_S, self.delta_t)
                    # discharge the ESS as far as it is possible and take the rest from the Main Grid
                    if lack != 0:
                        p_GL_S = p_GL_S + lack / self.delta_t
                        p_GL_N = p_GL - p_GL_S
                    self.register(p_L, p_GL, p_GL_S, p_GL_N, alpha)
                # the ESS has nout enough energy to provide and its max power limit is not exceeded
                elif (alpha * abs(p_GL * self.delta_t)/self.ESS.eta) > e_S_res and abs(p_GL) <= self.ESS.p_S_max:
                    logging.debug('[*CIPAR*] MG Class | Generation lack - ESS not enough energy - ESS under Pmax')
                    p_GL_S = -round(alpha * e_S_res / self.delta_t, 2) / self.ESS.eta
                    p_GL_N = p_GL - p_GL_S
                    lack = self.ESS.update_SoE_dch(p_GL_S, self.delta_t)
                    # discharge the ESS as far as it is possible and take the rest from the Main Grid
                    if lack != 0:
                        p_GL_S = p_GL_S + lack / self.delta_t
                        p_GL_N = p_GL - p_GL_S
                    self.register(p_L, p_GL, p_GL_S, p_GL_N, alpha)
                # the ESS has not enough energy to provide and its max power limit is exceeded
                elif (alpha * abs(p_GL * self.delta_t)/self.ESS.eta) > e_S_res and abs(p_GL) > self.ESS.p_S_max:
                    logging.debug('[*CIPAR*] MG Class | Generation lack - ESS not enough energy - ESS over Pmax')
                    # check if, at the max power, the ESS has enough remaining energy
                    if (alpha * self.ESS.p_S_max * self.delta_t/self.ESS.eta) <= e_S_res:
                        p_GL_S = alpha * self.ESS.p_S_max
                    else:
                        p_GL_S = 0
                    p_GL_N = p_GL - p_GL_S
                    lack = self.ESS.update_SoE_dch(p_GL_S, self.delta_t)
                    # discharge the ESS as far as it is possible and take the rest from the Main Grid
                    if lack != 0:
                        p_GL_S = p_GL_S + lack / self.delta_t
                        p_GL_N = p_GL - p_GL_S
                    self.register(p_L, p_GL, p_GL_S, p_GL_N, alpha)
                # the ESS has enough energy to provide and its max power limit is exceeded
                elif (alpha * abs(p_GL * self.delta_t)/self.ESS.eta) <= e_S_res and abs(p_GL) > self.ESS.p_S_max:
                    logging.debug('[*CIPAR*] MG Class | Generation lack - ESS enough energy - ESS over Pmax')
                    p_GL_S = -round(alpha * self.ESS.p_S_max, 2) / self.ESS.eta
                    p_GL_N = p_GL - p_GL_S
                    lack = self.ESS.update_SoE_dch(p_GL_S, self.delta_t)
                    # discharge the ESS as far as it is possible and take the rest from the Main Grid
                    if lack != 0:
                        p_GL_S = p_GL_S + lack / self.delta_t
                        p_GL_N = p_GL - p_GL_S
                    self.register(p_L, p_GL, p_GL_S, p_GL_N, alpha)
                else:
                    raise ValueError("[*CIPAR*] MG Class | Case not covered!")
            logging.debug(f'[*CIPAR*] MG Class | p_G={p_G}; p_L={p_L}; p_GL={p_GL}; p_GL_S={round(p_GL_S, 2)}; p_GL_N={round(p_GL_N, 2)}  all in [kW]')
            logging.debug(f'[*CIPAR*] MG Class | SoE_after={round(self.SoE_values[-1], 2)}')
            self.check_SoE()
            self.check_e_bal(p_GL, p_GL_N, p_GL_S, ess_losses)
            cost, revenue, inv_cost, C_b_k, purch_cost, no_green_cost = self.get_cost(p_G, p_GL_S, p_L, p_GL_N)
            self.cost_values.append(cost)
            self.revenues.append(revenue)
            self.inv_costs.append(inv_cost)
            self.C_b_ks.append(C_b_k)
            self.purch_costs.append(purch_cost)
            oper_cost = inv_cost + C_b_k
            self.oper_costs.append(oper_cost)
            self.no_pv_costs.append(no_green_cost)
        return float(sum(self.cost_values))

    '''
    Registers Microgrid power flows and EMS decisions.
    :param p_L: Power flow from L.
    :type p_L: float
    :param p_GL: Power flow from GL.
    :type p_GL: float
    :param p_GL_S: Power flow from GL to S.
    :type p_GL_S: float
    :param p_GL_N: Power flow from GL to N.
    :type p_GL_N: float
    :param alpha: The EMS decision.
    :type alpha: float
    '''
    def register(self, p_L, p_GL, p_GL_S, p_GL_N, alpha):
        self.power_flows["p_L"].append(p_L)
        self.power_flows["p_GL"].append(p_GL)
        self.power_flows["p_GL_S"].append(p_GL_S)
        self.power_flows["p_GL_N"].append(p_GL_N)
        self.SoE_values.append(self.ESS.SoE)
        self.alpha_values.append(alpha)

    '''
    Checks SoE feasibility.
    '''
    def check_SoE(self):
        if round(self.ESS.SoE, 2) > self.ESS.SoE_max or round(self.ESS.SoE, 2) < self.ESS.SoE_min:
            raise ValueError('[*CIPAR*] SoE out of bounds!')

    '''
    Checks energy balance feasibility.
    '''
    def check_e_bal(self, p_GL, p_GL_N, p_GL_S, ess_losses):
        bal = p_GL - p_GL_N - p_GL_S - ess_losses
        if round(bal, 2) != 0:
            raise ValueError('[*CIPAR*] Non-zero energy balance!')

    '''
    Calculates Microgrid cost.
    :param p_G: Power flow from G.
    :type p_G: float
    :param p_GL_S: Power flow from GL to S.
    :type p_GL_S: float
    :param p_L: Power flow from L.
    :type p_L: float
    :param p_GL_N: Power flow from GL to N.
    :type p_GL_N: float
    :return cost, revenue, inv_cost, C_b_k, purch_cost, no_green_cost: Microgrid costs
    :rtype cost, revenue, inv_cost, C_b_k, purch_cost, no_green_cost: list
    '''
    def get_cost(self, p_G, p_GL_S, p_L, p_GL_N):
        MW_2_kW = 0.001
        E_prod = self.delta_t * (p_G)
        logging.debug(f'[*CIPAR*] MG Class | Local energy production={round(E_prod, 2)} [kWh]')
        E_draw = 0
        if p_GL_S > 0:
            E_draw = self.delta_t * (p_L + p_GL_S) 
        if p_GL_S <= 0:
            E_draw = self.delta_t * (p_L)
        logging.debug(f'[*CIPAR*] MG Class | Drawn energy={round(E_draw, 2)} [kWh]')
        E_sha = min(E_prod, E_draw)  # REC shared energy
        logging.debug(f'[*CIPAR*] MG Class | Shared energy={round(E_sha, 2)} [kWh]')
        p_sold = 0
        if p_GL_N >= 0:
            p_sold = p_GL_N
        p_purch = 0
        if p_GL_N < 0:
            p_purch = abs(p_GL_N)
        logging.debug(f'[*CIPAR*] MG Class | Sold power ={round(p_sold, 2)} [kW]')
        logging.debug(f'[*CIPAR*] MG Class | Purchased power ={round(p_purch, 2)} [kW]')
        logging.debug(f'[*CIPAR*] MG Class | MG simulation ends.')
        logging.debug('')
        I_ret = self.tariffs["PR_3"] * MW_2_kW * self.delta_t * p_sold
        CU_af_m = (self.tariffs["TRAS_e"] + self.tariffs["max_BTAU_m"]) * MW_2_kW
        I_rest = CU_af_m * E_sha
        I_sha = self.tariffs["TP_CE"] * MW_2_kW * E_sha  
        revenue = I_sha + I_rest + I_ret  
        inv_cost = self.tariffs["u_pv"] * p_G * self.delta_t
        C_b_k = self.ESS.get_wear_cost(self.SoE_values[-2], abs(p_GL_S), self.delta_t)
        purch_cost = 0
        if p_purch != 0:
            purch_cost = ((p_purch * self.delta_t * self.tariffs["P_pur"] + self.tariffs["bill_fixed_costs"]) *
                          (1 + self.tariffs["VAT"]))
        cost = - revenue + inv_cost + C_b_k + purch_cost
        no_green_cost = (p_L * self.delta_t * self.tariffs["P_pur"] + self.tariffs["bill_fixed_costs"]) * (1 + self.tariffs["VAT"])
        return cost, revenue, inv_cost, C_b_k, purch_cost, no_green_cost

    '''
    Resets the Microgrid state.
    '''
    def reset_state(self):
        self.SoE_values = []
        self.alpha_values = []
        self.cost_values = []
        self.revenues = []
        self.inv_costs = []
        self.C_b_ks = []
        self.purch_costs = []
        self.oper_costs = []
        self.no_pv_costs = []
        self.ESS.SoE = self.ESS.SoE_0

    '''
    Saves the Microgrid state (needed only for online simulation).
    '''
    def save_online_state(self):
        self.SoE_values_on = self.SoE_values
        self.alpha_values_on = self.alpha_values
        self.cost_values_on = self.cost_values
        self.revenues_on = self.revenues
        self.inv_costs_on = self.inv_costs
        self.C_b_ks_on =  self.C_b_ks
        self.purch_costs_on = self.purch_costs
        self.oper_costs_on = self.oper_costs
        self.no_green_costs_on = self.no_pv_costs
        self.ESS.SoE_on = self.ESS.SoE

    '''
    Loads the Microgrid state (needed only for online simulation).
    '''
    def recover_online_state(self):
        self.SoE_values = self.SoE_values_on
        self.alpha_values = self.alpha_values_on
        self.cost_values = self.cost_values_on
        self.revenues = self.revenues_on
        self.inv_costs = self.inv_costs_on
        self.C_b_ks =  self.C_b_ks_on
        self.purch_costs = self.purch_costs_on
        self.oper_costs = self.oper_costs_on
        self.no_pv_costs = self.no_green_costs_on
        self.ESS.SoE = self.ESS.SoE_on


    def get_ess_insights(self):
        """
        Returns ESS insights.
        :return: The ESS SoE values, the ESS costs, the ESS power flows.
        :rtype: tuple
        """
        return self.SoE_values, self.C_b_ks, self.power_flows["p_GL_S"]


