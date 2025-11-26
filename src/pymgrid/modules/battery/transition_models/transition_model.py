import inspect
import yaml
from pathlib import Path
import math
import matplotlib.pyplot as plt


class BatteryTransitionModel(yaml.YAMLObject):
    """
    A simple battery transition model.

    In this model, the amount of energy retained is given by ``efficiency``.

    For example, if a microgrid requests 100 kWh of energy and ``efficiency=0.5``, the battery must use
    200 kWh of energy. Alternatively, if a microgrid sends a battery 100 kWh of energy and ``efficiency=0.5``,
    the battery's charge will increase by 50 kWh.

    Parameters
    ----------
    external_energy_change : float
        Amount of energy that is being requested externally.
        If ``energy > 0``, it is energy that is absorbed by the battery -- a charge.
        If ``energy < 0``, it is energy provided by the battery: a discharge.

    min_capacity : float
        Minimum energy that must be contained in the battery.

    max_capacity : float
        Maximum energy that can be contained in the battery.
        If ``soc=1``, capacity is at this maximum.

    max_charge : float
        Maximum amount the battery can be charged in one step.

    max_discharge : float
        Maximum amount the battery can be discharged in one step.

    efficiency : float
        Efficiency of the battery.

    battery_cost_cycle : float
        Marginal cost of charging and discharging.

    state_dict : dict
        State dictionary, with state of charge and current capacity information.

    Returns
    -------
    internal_energy : float
        Amount of energy that the battery must use or will retain given the external amount of energy.

    """

    yaml_dumper = yaml.SafeDumper
    yaml_loader = yaml.SafeLoader
    yaml_tag = u"!BatteryTransitionModel"


    def __init__(self):
        self._transition_history = []

    def __call__(self,
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
        return self.transition(
            external_energy_change=external_energy_change,
            min_capacity=min_capacity,
            max_capacity=max_capacity,
            max_charge=max_charge,
            max_discharge=max_discharge,
            efficiency=efficiency,
            battery_cost_cycle=battery_cost_cycle,
            current_step=current_step,
            state_dict=state_dict,
            record_history=record_history,
        )

    def transition(self, external_energy_change, efficiency, 
                   current_step=None, record_history: bool = True, **kwargs):
        if external_energy_change < 0:
            internal_energy_change = external_energy_change / efficiency
        else:
            internal_energy_change = external_energy_change * efficiency

        state_dict = kwargs.get("state_dict", {}) or {}
        soc = state_dict.get("soc")
        current_charge = state_dict.get("current_charge")
        max_capacity = kwargs.get("max_capacity")
        soe = None
        if current_charge is not None and max_capacity not in (None, 0):
            soe = current_charge / max_capacity

        power_kw = kwargs.get("power_kw")

        if record_history:
            self._transition_history.append({
                "time_hours": float(
                    current_step if current_step is not None else len(self._transition_history)
                ),
                "internal_energy_change": float(internal_energy_change),
                "soc": float(soc) if soc is not None else None,
                "soe": float(soe) if soe is not None else None,
                "power_kw": float(power_kw) if power_kw is not None else None,
            })

        return internal_energy_change

    def new_kwargs(self):
        params = inspect.signature(self.__init__).parameters
        params = {k: getattr(self, k) for k in params.keys() if k not in ('args', 'kwargs')}
        return params

    def __repr__(self):
        params = self.new_kwargs()
        formatted_params = ', '.join([f'{p}={v}' for p, v in params.items()])
        return f'{self.__class__.__name__}({formatted_params})'

    def __eq__(self, other):
        if type(self) != type(other):
            return NotImplemented
        return repr(self) == repr(other)

    @classmethod
    def to_yaml(cls, dumper, data):
        return dumper.represent_mapping(cls.yaml_tag, data.new_kwargs(), flow_style=cls.yaml_flow_style)

    @classmethod
    def from_yaml(cls, loader, node):
        mapping = loader.construct_mapping(node, deep=True)
        if mapping:
            return cls(**mapping)
        else:
            return cls()
        

    def get_transition_history(self):
        """Return a copy of the recorded transition history."""

        return list(self._transition_history)

    def save_transition_history(self, history_path: str):
        """Persist transition history to a JSON file for offline plotting."""

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
        """Plot state of charge, state of energy, terminal voltage, energy and power."""

        import matplotlib.pyplot as plt

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
