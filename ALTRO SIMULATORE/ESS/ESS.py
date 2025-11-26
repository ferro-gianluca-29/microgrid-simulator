class ESS:

    def __init__(self,
                 model,
                 Q,
                 p_S_max,
                 a,
                 b,
                 B,
                 eta,
                 SoE_0,
                 V_n,
                 SoE_min,
                 SoE_max,
                 Q_n,
                 C_n,
                 eta_inverter,
                 Ns_batt,
                 Np_batt,
                 SoC_0,
                 T
                 ):
        self.model = model
        self.Q = Q
        self.p_S_max = p_S_max
        self.a = a
        self.b = b
        self.B = B
        self.eta = eta
        self.SoE_0 = SoE_0
        self.V_n = V_n
        self.SoE_min = SoE_min
        self.SoE_max = SoE_max
        self.SoE = self.SoE_0
        self.Q_n = Q_n
        self.C_n = C_n,
        self.eta_inverter = eta_inverter,
        self.Ns_batt = Ns_batt,
        self.Np_batt = Np_batt,
        self.SoC_0 = SoC_0,
        self.T = T

    '''
    Updates SoC in charging
    :param p_GL_S: Power flow between GL and S
    :type p_GL_S: float
    :param p_GL: Power from GL 
    :type p_GL: float
    :param delta_t: Simulation timestep
    :type delta_t: float
    '''
    def update_SoE_ch(self, p_GL_S, p_GL, delta_t):
        p_GL_S = p_GL_S * self.eta
        en = abs(p_GL_S * delta_t) / self.Q
        self.SoE = self.SoE + en
        excess = 0
        if self.SoE > self.SoE_max:
            self.SoE = self.SoE_max
            excess = (self.SoE_max - self.SoE) * self.Q
        return excess

    '''
    Updates SoC in discharging
    :param p_GL_S: Power flow between GL and S
    :type p_GL_S: float
    :param delta_t: Simulation timestep
    :type delta_t: float
    '''
    def update_SoE_dch(self, p_GL_S, delta_t):
        p_GL_S = p_GL_S / self.eta
        en = abs(p_GL_S * delta_t) / self.Q
        self.SoE = self.SoE - en
        lack = 0
        if self.SoE < self.SoE_min:
            self.SoE = self.SoE_min
            lack = (self.SoE_min - self.SoE) * self.Q
        return lack

    '''
    Returns wear cost.
    :param p_GL_S: Power flow between GL and S
    :type p_GL_S: float
    :param delta_t: Simulation timestep
    :type delta_t: float
    :return C_b_k: Battery wear cost.
    :rtype C_b_k: float
    '''
    def get_wear_cost(self, SoE_prev, p_S_k, delta_t):
        W_SoC_k_prec = (self.B / (2 * self.Q * self.eta)) * (self.b * pow((1 - SoE_prev), (self.b - 1))) / self.a
        W_SoC_k = (self.B / (2 * self.Q * self.eta)) * (self.b * pow((1 - self.SoE), (self.b - 1))) / self.a
        C_b_k = ((delta_t / 2) * (W_SoC_k_prec + W_SoC_k)) * (abs(p_S_k))
        return C_b_k

