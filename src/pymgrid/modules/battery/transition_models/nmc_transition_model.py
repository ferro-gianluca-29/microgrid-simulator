import yaml

from .unipi_transition_model import UnipiChemistryTransitionModel


class NmcTransitionModel(UnipiChemistryTransitionModel):
    """NMC chemistry model matching ESS_UNIPI_NMC Voc/R0 logic."""

    yaml_dumper = yaml.SafeDumper
    yaml_loader = yaml.SafeLoader
    yaml_tag = u"!NmcTransitionModel"

    def __init__(self, **kwargs):
        super().__init__(
            parameters_mat="parameters_cell_NMC.mat",
            reference_cell_capacity_ah=3.2,
            nominal_cell_voltage=3.7,
            **kwargs,
        )
