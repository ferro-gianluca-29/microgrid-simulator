# -*- coding: utf-8 -*-


import numpy as np
import scipy.io as sio
import os
from scipy.interpolate import RegularGridInterpolator

class ESS:
    def __init__(self, model, p_S_max, a, b, B, eta_inverter, C_n, Ns_batt, Np_batt, SoC_0, SoC_min, SoC_max, T):
        self.model = model
        self.p_S_max = p_S_max
        self.a = a
        self.b = b
        self.B = B
        self.SoE_0 = SoC_0
        self.SoC_min = SoC_min
        self.SoC_max = SoC_max
        self.SoE = self.SoE_0
        self.SoC_0 = SoC_0
        self.SoC = self.SoC_0
        self.Ns_batt = Ns_batt
        self.Np_batt = Np_batt
        self.T = T
        self.V_n = 3.7 # nominal value for NMC cells
        self.C_n = C_n
        self.eta_inverter = eta_inverter
        self.Q_n = self.C_n * self.V_n * self.Ns_batt * self.Np_batt / 1000
        self.Q = self.Q_n * self.SoE_0
        self.parameters = sio.loadmat(os.path.join("ESS_package_UNIPI", "parameters_cell_NMC.mat"))["parameters_cell_NMC"]
        self.SoC_interpol = np.linspace(0, 1, len(self.parameters))
        self.T_interpol = np.array([20, 40])
        self.R0_table = self.parameters[:, 1:3] * (self.Ns_batt / self.Np_batt) *4.5/self.C_n # scaled from base-paramters of a 4.5 Ah NMC cell
        self.interpolator_R0 = RegularGridInterpolator((self.SoC_interpol, self.T_interpol), self.R0_table)
        self.Voc_table = self.parameters[:, 4:6] * self.Ns_batt
        self.interpolator_Voc = RegularGridInterpolator((self.SoC_interpol, self.T_interpol), self.Voc_table)
        self.Voc_start = self.interpolator_Voc((self.SoC, self.T))

    def update_I_batt(self, p_GL_S, V_prev):
        """Calculate the battery current based on previous voltage."""
        self.I = 1000 * p_GL_S / V_prev  # battery current value in A
        return self.I

    def update_V_batt(self, I_batt):
        """Calculate battery voltage."""
        self.Voc = self.interpolator_Voc((self.SoC, self.T))
        self.R0 = self.interpolator_R0((self.SoC, self.T))
        self.V = self.Voc - self.R0 * I_batt # battery voltage value in V
        return self.V

    def update_SoC(self, I_batt, delta_t):
        """Calculate battery SOC."""
        self.SoC -= (I_batt * delta_t) / (self.C_n*self.Np_batt) # battery SOC as fraction of nominal capacity    
        if self.SoC > self.SoC_max:
            self.SoC = self.SoC_max             
        if self.SoC < self.SoC_min:
            self.SoC = self.SoC_min   
        return self.SoC

    def calculate_excess(self,I_batt, V_batt, delta_t):
        """Calculate excess energy in kWh if SOC max is reached."""
        self.excess = 0
        if self.SoC == self.SoC_max:
            self.excess = I_batt * V_batt * delta_t / 1000
        return self.excess
        
    def calculate_lack(self,I_batt, V_batt, delta_t):
        """Calculate lack energy in kWh if SOC min is reached."""
        self.lack = 0 
        if self.SoC == self.SoC_min:
            self.lack = I_batt * V_batt * delta_t / 1000
        return self.lack
 
    def calculate_eta(self,I_batt, V_batt, delta_t):
        """Calculate battery + inverter dynamic efficiency."""
        self.eta = 1
        if I_batt > 0:
            self.eta = self.eta_inverter*(1-self.R0*I_batt**2/(I_batt*self.Voc))
            return self.eta
        if I_batt < 0:
            self.eta = self.eta_inverter*(1-self.R0*I_batt**2/(-I_batt*V_batt))
            return self.eta #battery efficiency 
    
 
    def update_SoE(self, I_batt, delta_t):
        """Calculate battery SOE."""
        self.SoE -= (I_batt * self.Voc * delta_t / 1000) / self.Q_n
        return self.SoE #battery SOE as fraction of nominal energy


    def get_wear_cost(self, SoC_prev, p_GL_S, delta_t): #on SOC based
        """
            Estimates the battery wear cost, by implementing to an empirical cost model.

        """
        W_SoC_k_prec = (self.B / (2 * self.Q * self.eta)) * (self.b * pow((1 - SoC_prev), (self.b - 1))) / self.a
        W_SoC_k = (self.B / (2 * self.Q * self.eta)) * (self.b * pow((1 - self.SoC), (self.b - 1))) / self.a
        C_b_k = ((delta_t / 2) * (W_SoC_k_prec + W_SoC_k)) * (abs(p_GL_S))
        return C_b_k