from .apply_methods import apply
from .copy_methods import copy_thermalbits, deepcopy_dunder
from ._init_method import init_thermalbits
from .generate_overview import generate_overview, write_json
from .overview_to_verilog import write_verilog
from .update_entropy import update_entropy
from .visualize_dag import visualize_dag


class ThermalBits:
    __init__ = init_thermalbits
    copy = copy_thermalbits
    __copy__ = copy_thermalbits
    __deepcopy__ = deepcopy_dunder
    generate_overview = generate_overview
    write_json = write_json
    write_verilog = write_verilog
    visualize_dag = visualize_dag
    update_entropy = update_entropy
    apply = apply
