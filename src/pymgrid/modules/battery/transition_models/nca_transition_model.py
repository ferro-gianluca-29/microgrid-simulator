import yaml

from .unipi_transition_model import UnipiChemistryTransitionModel


class NcaTransitionModel(UnipiChemistryTransitionModel):
    """NCA chemistry model matching ESS_UNIPI_NCA Voc/R0 logic."""

    yaml_dumper = yaml.SafeDumper
    yaml_loader = yaml.SafeLoader
    yaml_tag = u"!NcaTransitionModel"

    def __init__(self, **kwargs):
        super().__init__(
            parameters_mat="parameters_cell_NCA.mat",
           # reference_cell_capacity_ah=100.0,
            reference_cell_capacity_ah=87.671,
            nominal_cell_voltage=3.65,
            **kwargs,
        )
