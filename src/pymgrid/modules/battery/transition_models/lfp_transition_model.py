import yaml

from .unipi_transition_model import UnipiChemistryTransitionModel


class LfpTransitionModel(UnipiChemistryTransitionModel):
    """LFP chemistry model matching ESS_UNIPI_LFP Voc/R0 logic."""

    yaml_dumper = yaml.SafeDumper
    yaml_loader = yaml.SafeLoader
    yaml_tag = u"!LfpTransitionModel"

    def __init__(self, **kwargs):
        super().__init__(
            parameters_mat="parameters_cell_LFP.mat",
            reference_cell_capacity_ah=3.704,
            nominal_cell_voltage=3.2,
            **kwargs,
        )
