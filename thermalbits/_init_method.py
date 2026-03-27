def init_thermalbits(self, verilog_path: str | None = None) -> None:
    self.verilog_path = verilog_path
    self.file_name = ""
    self.pi = []
    self.po = []
    self.node = []
    self.entropy: float | None = None
    if verilog_path:
        self.generate_overview()
