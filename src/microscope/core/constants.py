class HardwareConstants:
    def __init__(self):
        self.cfg_path = "hardware_profiles/20250523-OPM.cfg"
        self.galvo_a_label = "Scanner:AB:33"
        self.piezo_a_label = "PiezoStage:P:34"
        self.camera_a_label = "Camera-1"
        self.plogic_label = "PLogic:E:36"
        self.tiger_comm_hub_label = "TigerCommHub"
        self.plogic_trigger_ttl_addr = 41
        self.plogic_4khz_clock_addr = 192
        self.plogic_laser_on_cell = 10
        self.plogic_camera_cell = 11
        self.plogic_always_on_cell = 12
        self.plogic_bnc3_addr = 35
        self.pulses_per_ms = 4.0
        self.plogic_laser_preset_num = 30
        self.slice_calibration_slope_um_per_deg = 100.0
        self.line_scans_per_slice = 1
        self.delay_before_scan_ms = 0.0
        self.line_scan_duration_ms = 1.0
        self.delay_before_side_ms = 0.0
