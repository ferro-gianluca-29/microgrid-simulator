from .ESS import ESS
import math

class ESS_empirical(ESS):

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
                 SoC_min,
                 SoC_max,
                 Q_n,
                 C_n,
                 eta_inverter,
                 Ns_batt,
                 Np_batt,
                 SoC_0,
                 T
                 ):
        super().__init__(model,
                         Q,
                         p_S_max,
                         a,
                         b,
                         B,
                         eta,
                         SoE_0,
                         V_n,
                         SoC_min,
                         SoC_max,
                         Q_n,
                         C_n,
                         eta_inverter,
                         Ns_batt,
                         Np_batt,
                         SoC_0,
                         T
                         )

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
        i, x, Qr = self.get_req_quant(p_GL_S)
        SoC_coulomb = self.SoE + (i / self.Q_n) * delta_t
        y = SoC_coulomb
        self.SoE = self.compute_ECM(i,x,y,Qr,delta_t)
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
        i, x, Qr = self.get_req_quant(p_GL_S)
        DoD_coulomb = ((abs(i) / self.Q_n) * delta_t) / self.Q_n
        y = 1 - DoD_coulomb
        self.SoE = self.compute_ECM(i, x, y, Qr, delta_t)
        lack = 0
        if self.SoE < self.SoE_max:
            self.SoE = self.SoE_min
            lack = (self.SoE_min - self.SoE) * self.Q
        return lack

    '''
    Calculates quantities need in the computation
    :param p_GL_S: Power flow between GL and S
    :type p_GL_S: float
    '''
    def get_req_quant(self, p_GL_S):
        i = p_GL_S / self.V_n
        Qr = self.SoE * self.Q_n
        if Qr == 0:
            rate = 1000
        else:
            rate = abs(i/Qr)
        x = rate
        return i, x, Qr

    '''
    Simulates the ECM model
    :param i: The current
    :type i: float
    :param x: The C-rate
    :type x: float
    :param y: The current SoC
    :type y: float
    :param Qr: The residual capacity
    :param Qr: float
    :param delta_t: Simulation timestep
    :type delta_t: float
    '''
    def compute_ECM(self, i, x, y, Qr, delta_t):
        # charging
        if i >= 0:
            param = [0, 0, 0, 1.83, 0, 0, 0, 1.59, 0, 1.02, 1.33, 0, 0, 0, 0.66, 0, 0, 7.29, 5.23, 0, 0,
                     4.42, 0, 0, 5.91, 0, 0, 6.34, 0, 0, 0]
        # discharging
        if i < 0:
            param = [0, 0, 0, 0, 0, 0, 0, 0, 4.15, 4.13, 0, 0, 2.90, 0.86, 0, 0, 0, 0, 0.12, 0, 0, 0, 0, 0, 2.31, 0, 0,
                     3.13, -0.36, 0, 0]
        # parameteric computation
        R0 = (param[0] + param[1] * x + param[2] * pow(x, 2)) * math.exp(-param[3] * y) + (
                    param[4] + param[5] * x + param[6] * pow(x, 2))  # [Ohm]
        Rp = (param[7] + param[8] * x + param[9] * pow(x, 2)) * math.exp(-param[10] * y) + (
                    param[11] + param[12] * x + param[13] * pow(x, 2))  # [Ohm]
        Cp = -(param[14] + param[15] * x + param[16] * pow(x, 2)) * math.exp(-param[17] * y) + (
                    param[18] + param[19] * x + param[20] * pow(x, 2))  # [F]
        Vocv = (param[21] + param[22] * x + param[23] * pow(x, 2)) * math.exp(-param[24] * y) + (
                    param[25] + param[26] * y + param[27] * pow(y, 2) + param[28] * pow(y, 3)) - param[29] * x + param[
                   30] * pow(x, 2)  # [V]

        # calculate OCV
        try:
            Vterm = ((Qr / Cp + i * Rp) * math.exp(-delta_t / (Rp * Cp))) + Vocv - (i * (R0 + Rp))
        except:
            Vterm = 10
        # calculate SoC from OCV-SoC regression curve
        c2 = 0.03
        c3 = 1.08
        q = -4.15  # (Ah)
        try:
            SoC_calc = round(c2 * pow(Vterm, 2) + c3 * Vterm + q, 2)
            if SoC_calc < 0:
                SoC_calc = pow(abs(SoC_calc), 2)
            if SoC_calc > 1:
                SoC_calc = pow(abs(SoC_calc - 1), 2)
        except:
            SoC_calc = 10
        return SoC_calc

    '''
    Calulates operational costs.
    :param SoE_prev: The SoE (or SoC) in the previous timeslot
    :type SoE_prev: float
    :param p_S_k: The battery power flow
    :type p_S_k: float
    :param delta_t: Simulation timestep
    :type delta_t: float
    '''
    def get_wear_cost(self, SoE_prev, p_S_k, delta_t):
        return super().get_wear_cost(SoE_prev, p_S_k, delta_t)