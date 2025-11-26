from .ESS import ESS


class ESS_linear(ESS):

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

    def update_SoE_ch(self, p_GL_S, p_GL, delta_t):
        return super().update_SoE_ch(p_GL_S, p_GL, delta_t)

    def update_SoE_dch(self, p_GL_S, delta_t):
        return super().update_SoE_dch(p_GL_S, delta_t)

    def get_wear_cost(self, SoE_prev, p_S_k, delta_t):
        return super().get_wear_cost(SoE_prev, p_S_k, delta_t)
