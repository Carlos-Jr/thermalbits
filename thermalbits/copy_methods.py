from copy import deepcopy


def copy_thermalbits(self):
    clone = self.__class__()
    clone.verilog_path = self.verilog_path
    clone.file_name = self.file_name
    clone.pi = deepcopy(self.pi)
    clone.po = deepcopy(self.po)
    clone.node = deepcopy(self.node)
    return clone


def deepcopy_dunder(self, _memo: dict):
    return copy_thermalbits(self)
