import os
from typing import Tuple

import numpy as np
import scipy.io as sio
from scipy.interpolate import RegularGridInterpolator
import yaml

import math
import matplotlib.pyplot as plt
from pathlib import Path

from .transition_model import BatteryTransitionModel


class UnipiChemistryTransitionModel(BatteryTransitionModel):
    """Base class for UNIPI chemistry-aware battery transition models.

    This reproduces the Voc/R0 interpolation and dynamic efficiency logic of
    the "ALTRO SIMULATORE" ESS_UNIPI_* classes while keeping the standard
    :class:`BatteryTransitionModel` API. The model uses lookup tables loaded
    from MATLAB ``.mat`` files to compute the open-circuit voltage (Voc) and
    internal resistance (R0) as a function of state-of-charge (SoC) and
    temperature, then derives a step-level round-trip efficiency accordingly.

    Parameters
    ----------
    parameters_mat : str
        File name of the MATLAB parameter table to load (placed in the local
        ``data`` directory next to this module).
    reference_cell_capacity_ah : float
        Nominal capacity (in Ah) of the reference cell for which the R0 table
        was generated. Used to scale R0 when modelling packs with a different
        nominal capacity ``c_n``.
    nominal_cell_voltage : float
        Nominal voltage (in V) of the reference cell.
    ns_batt : int, default 1
        Cells in series.
    np_batt : int, default 1
        Cells in parallel.
    c_n : float, default None
        Nominal cell capacity (Ah) of the target pack. If None, defaults to
        ``reference_cell_capacity_ah``.
    temperature_c : float, default 25.0
        Pack temperature used for interpolation (clipped to the tabulated
        range).
    eta_inverter : float, default 1.0
        Inverter efficiency multiplier applied to the dynamic efficiency.
    delta_t_hours : float, default 1.0
        Duration (in hours) represented by each transition call. External
        energy is divided by ``delta_t_hours`` to obtain the requested power.
    wear_a, wear_b, wear_B : float or None
        Optional empirical wear coefficients; if provided, ``get_wear_cost``
        mirrors the ESS_UNIPI_* cost estimator. Otherwise, ``get_wear_cost``
        returns 0.
    """

    yaml_dumper = yaml.SafeDumper
    yaml_loader = yaml.SafeLoader

    def __init__(self,
                 parameters_mat: str,
                 reference_cell_capacity_ah: float,
                 nominal_cell_voltage: float,
                 ns_batt: int = 16,
                 np_batt: int = 1,
                 c_n: float = None,
                 temperature_c: float = 25.0,
                 eta_inverter: float = 1.0,
                 delta_t_hours: float = 0.25, 
                 wear_a: float = None,
                 wear_b: float = None,
                 wear_B: float = None):
        
        self.parameters_mat = parameters_mat
        self.reference_cell_capacity_ah = reference_cell_capacity_ah
        self.nominal_cell_voltage = nominal_cell_voltage
        self.ns_batt = ns_batt
        self.np_batt = np_batt
        self.c_n = c_n if c_n is not None else reference_cell_capacity_ah
        self.temperature_c = temperature_c
        self.eta_inverter = eta_inverter
        self.delta_t_hours = delta_t_hours
        self.wear_a = wear_a
        self.wear_b = wear_b
        self.wear_B = wear_B
        self.dyn_eta = None

        self.nominal_energy_kwh = (
            self.c_n * self.nominal_cell_voltage * self.ns_batt * self.np_batt / 1000.0
        )
        self._last_voltage = None
        self._soe = None
        self.soc = None
        self.current_a = 0
        self.last_wear_cost = 0.0
        self.last_dynamic_efficiency = None
        self._load_tables()


        self._transition_history = []

    def _load_tables(self):
        base_dir = os.path.join(os.path.dirname(__file__), "data")
        data_path = os.path.join(base_dir, self.parameters_mat)
        parameters = sio.loadmat(data_path)[os.path.splitext(self.parameters_mat)[0]]
        self.soc_grid = np.linspace(0, 1, len(parameters))
        self.temperature_grid = np.array([20, 40])
        self.voc_interpolator = RegularGridInterpolator(
            (self.soc_grid, self.temperature_grid), parameters[:, 4:6] * self.ns_batt
        )

        scaling = (self.ns_batt / self.np_batt) * (self.reference_cell_capacity_ah / self.c_n)
        self.r0_interpolator = RegularGridInterpolator(
            (self.soc_grid, self.temperature_grid), parameters[:, 1:3] * scaling
        )

    def _interp_voc_r0(self, soc: float, temperature_c: float) -> Tuple[float, float]:
        soc_clipped = float(np.clip(soc, self.soc_grid[0], self.soc_grid[-1]))
        temp_clipped = float(np.clip(temperature_c, self.temperature_grid[0], self.temperature_grid[-1]))
        voc = float(self.voc_interpolator((soc_clipped, temp_clipped)))
        r0 = float(self.r0_interpolator((soc_clipped, temp_clipped)))
        return voc, r0

    def _dynamic_efficiency(self, current_a: float, voc: float, v_batt: float) -> float:
        if np.isclose(current_a, 0.0):
            return 1.0 * self.eta_inverter

        if current_a > 0:
            base = self.eta_inverter * (1 - (self.R0 * current_a ** 2) / (current_a * max(voc, 1e-9)))
        else:
            base = self.eta_inverter * (1 - (self.R0 * current_a ** 2) / (-current_a * max(v_batt, 1e-9)))

        return max(0.0, min(1.0, base))

    def _compute_wear_cost(self,
                           soc_previous: float,
                           soc_current: float,
                           power_kw: float,
                           delta_t_hours: float) -> float:
        if None in (self.wear_a, self.wear_b, self.wear_B):
            return 0.0

        q_n = self.nominal_energy_kwh
        eta = self.dyn_eta if self.dyn_eta is not None else (self.last_dynamic_efficiency or self.eta_inverter)
        w_prev = (self.wear_B / (2 * q_n * eta)) * (self.wear_b * pow((1 - soc_previous), (self.wear_b - 1))) / self.wear_a
        w_curr = (self.wear_B / (2 * q_n * eta)) * (self.wear_b * pow((1 - soc_current), (self.wear_b - 1))) / self.wear_a
        return ((delta_t_hours / 2) * (w_prev + w_curr)) * abs(power_kw)

    def transition(self,
                   external_energy_change,
                   min_capacity,
                   max_capacity,
                   max_charge,
                   max_discharge,
                   efficiency,
                   battery_cost_cycle, 
                   current_step,
                   state_dict,
                   record_history: bool = True):
        
        """# Energy conversion from external EMS to internal battery chemical model (using dynamic efficiency)
        if external_energy_change >= 0:
            converted_energy_change = external_energy_change * (self.dyn_eta or efficiency) 
        else:
            converted_energy_change = external_energy_change / (self.dyn_eta or efficiency) """
        
        # Compute the internal battery power and current

        
        #print(f"current_step: {current_step}") # per debug
        
        # In pymgrid, there is a mismatch in the terms convention: the 'soc' variable defined in the pymgrid library, 
        # is actually the state of energy (soe), defined as the portion of the battery energy in kwh;
        # so, what in pymgrid is called 'soc', actually is the soe;
        # the actual soc, which is the portion of the battery charge (in Ah), is computed internally in this method, as the 
        # ratio between the battery_pack_current_charge and the battery_pack_nominal_charge;

        self._soe = float(state_dict.get('soc', 0.0))  # previous soe
        temperature_c = float(state_dict.get('temperature_c', self.temperature_c)) # present temperature (dict to be implemented)

        delta_t = max(self.delta_t_hours, 1e-9) # questo va reso una variabile da dare in input al battery module 

        if current_step == 0:
            self._soc = float(state_dict.get('soc', 0.0))
            voc_prev, self.R0 = self._interp_voc_r0(self._soc, temperature_c)
            v_batt = max(voc_prev, 1e-6)            

        else:
            voc_prev, self.R0 = self._interp_voc_r0(self._soc, temperature_c)
            v_batt = max(voc_prev - self.R0 * self.current_a, 1e-6)
            

        # here the minus sign is required, since the internal battery model is 
        # based on positive sign when discharging and negative when charging, which is the 
        # opposite from the pymgrid convention 

        power_kw = -external_energy_change / delta_t # [kW]   
        self.current_a = 1000.0 * power_kw / max(v_batt, 1e-9) # [A]

        battery_pack_nominal_charge = self.c_n * self.np_batt # [Ah]

        current_charge_kWh = float(state_dict.get('current_charge', self._soe * max_capacity)) # [kWh]
        
        current_charge_Ah = self._soc * battery_pack_nominal_charge + (self.current_a * delta_t)

        soc_unbounded = self._soc - (self.current_a * delta_t) / (self.c_n * self.np_batt)

        min_soc = (min_capacity * 1000) / (battery_pack_nominal_charge * (self.nominal_cell_voltage * self.ns_batt)) # questi forse vanno corretti
        max_soc = (max_capacity * 1000) / (battery_pack_nominal_charge * (self.nominal_cell_voltage * self.ns_batt)) # questi forse vanno corretti

        #min_soc = min_capacity / max_capacity   # questi forse vanno corretti, occorre decidere come settarli
        #max_soc = max_capacity / max_capacity   # questi forse vanno corretti, occorre decidere come settarli

        soc_new = float(np.clip(soc_unbounded, min_soc, max_soc))   # ricontrollare se è corretto 

        self._soc = soc_new   # aggiorno il soc

        # compute dynamic efficiency
        self.dyn_eta = max(1e-9, self._dynamic_efficiency(self.current_a, voc_prev, v_batt))  # non entra nella logica di 
                                                                                        # aggiornamento di SoC e SoE

        soe_new = self._soe - (self.current_a * voc_prev * delta_t / 1000) / self.nominal_energy_kwh   

        internal_energy_change = (soe_new - self._soe) * max_capacity

        self.last_wear_cost = self._compute_wear_cost(self._soc, self._soc, power_kw, delta_t)
        voc_next, r0_next = self._interp_voc_r0(soc_new, temperature_c)


        if record_history:
            self._transition_history.append({
                "time_hours": float(
                    current_step * self.delta_t_hours
                    if current_step is not None
                    else len(self._transition_history) * self.delta_t_hours
                ),
                "current_a": float(self.current_a),
                "internal_energy_change": float(internal_energy_change),
                "soc": float(self._soc),
                "soe": float(soe_new),
                "voltage_v": float(v_batt),
                "power_kw": float(-power_kw),
            })


        #print(f"soc = {self._soc}") # per debug

        return internal_energy_change

    def get_wear_cost(self, soc_previous: float, power_kw: float, delta_t_hours: float):
        return self._compute_wear_cost(soc_previous, soc_previous, power_kw, delta_t_hours)
    

    def get_transition_history(self):
        """Return a copy of the recorded transition history."""

        return list(self._transition_history)

    def save_transition_history(self, history_path: str):
        """Persist transition history to a JSON file for offline plotting.

        Parameters
        ----------
        history_path : str
            Destination path for the JSON file.
        """

        import json

        with open(history_path, "w", encoding="utf-8") as fp:
            json.dump(self._transition_history, fp, ensure_ascii=False, indent=2)

    @staticmethod
    def load_transition_history(history_path: str):
        """Load a transition history previously saved with :meth:`save_transition_history`."""

        import json

        with open(history_path, "r", encoding="utf-8") as fp:
            return json.load(fp)

    def plot_transition_history(self, save_path: str = None, show: bool = True, history=None):
        """Plot SoC, SoE, voltage, internal energy and power for this transition model."""

        

        history_to_plot = history if history is not None else self._transition_history

        if not history_to_plot:
            raise ValueError("No transition history to plot. Run transition() before plotting.")

        def _valid_series(key):
            time_axis, values = [], []
            for entry in history_to_plot:
                value = entry.get(key)
                if value is None or (isinstance(value, float) and math.isnan(value)):
                    continue
                time_axis.append(entry["time_hours"])
                values.append(value)
            return time_axis, values

        metric_specs = {
            "soc": ("State of charge", "State of charge [0-1]", "tab:blue"),
            "soe": ("State of energy", "State of energy [0-1]", "tab:green"),
            "voltage_v": ("Battery voltage", "Voltage [V]", "tab:red"),
            "internal_energy_change": ("Internal energy change", "Energy [kWh]", "tab:orange"),
            "power_kw": ("Battery power", "Power [kW]", "tab:purple"),
        }

        figures = {}

        def _build_save_path(base_path: str, suffix: str) -> str:
            path = Path(base_path)
            if path.suffix:
                return str(path.with_name(f"{path.stem}{suffix}{path.suffix}"))
            return f"{base_path}{suffix}"

        for key, (title, ylabel, color) in metric_specs.items():
            time_axis, values = _valid_series(key)
            if not values:
                continue

            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(time_axis, values, linestyle="-", color=color)
            ax.set_xlabel("Time [h]")
            ax.set_ylabel(ylabel)
            ax.set_title(f"{self.__class__.__name__} {title} over time")
            ax.grid(True)

            fig.tight_layout()

            if save_path:
                fig.savefig(_build_save_path(save_path, f"_{key}"), bbox_inches="tight")

            if show:
                plt.show()
            else:
                plt.close(fig)

            figures[key] = (fig, ax)

        if not figures:
            raise ValueError("No plottable metrics found in transition history.")

        return figures
