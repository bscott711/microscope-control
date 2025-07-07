# Import the necessary packages
from typing import Optional

from pymmcore_plus import CMMCorePlus
from pymmcore_widgets import (
    CameraRoiWidget,
    ChannelGroupWidget,
    ChannelTable,
    ChannelWidget,
    ConfigurationWidget,
    ConfigWizard,
    CoreLogWidget,
    DefaultCameraExposureWidget,
    ExposureWidget,
    GridPlanWidget,
    GroupPresetTableWidget,
    ImagePreview,
    InstallWidget,
    LiveButton,
    MDASequenceWidget,
    MDAWidget,
    ObjectivesPixelConfigurationWidget,
    ObjectivesWidget,
    PixelConfigurationWidget,
    PositionTable,
    PresetsWidget,
    PropertiesWidget,
    PropertyBrowser,
    PropertyWidget,
    SnapButton,
    StageWidget,
    TimePlanWidget,
    ZPlanWidget,
)
from qtpy.QtWidgets import (
    QApplication,
    QGridLayout,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


# Create a QWidget class named MyWidget
class MyWidget(QWidget):
    """An example QWidget that uses a specific list of widgets."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent=parent)
        self.setWindowTitle("pymmcore-widgets Full Demo (Curated List)")

        core = CMMCorePlus.instance()
        core.loadSystemConfiguration()

        # --- Create an instance of each available widget ---

        # Main image and controls
        image_preview = ImagePreview()
        snap_button = SnapButton()
        live_button = LiveButton()

        # Configuration and Presets
        cfg_widget = ConfigurationWidget()
        presets_widget = PresetsWidget(group="Channel")
        group_preset_table = GroupPresetTableWidget()
        ch_group_widget = ChannelGroupWidget()
        ch_widget = ChannelWidget()
        channel_table = ChannelTable()

        # Camera & Exposure
        default_exp_widget = DefaultCameraExposureWidget()
        exp_widget = ExposureWidget()
        roi_widget = CameraRoiWidget()

        # Stage & Objectives
        objectives_widget = ObjectivesWidget()
        stage_widget = StageWidget(device="XY")
        position_table = PositionTable()

        # Multi-Dimensional Acquisition (MDA)
        mda_widget = MDAWidget()
        mda_sequence_widget = MDASequenceWidget()
        time_plan_widget = TimePlanWidget()
        grid_plan_widget = GridPlanWidget()
        z_plan_widget = ZPlanWidget()

        # Setup & Tools
        install_widget = InstallWidget()
        config_wizard = ConfigWizard()
        pixel_config_widget = PixelConfigurationWidget()
        obj_pixel_config_widget = ObjectivesPixelConfigurationWidget()
        core_log_widget = CoreLogWidget()

        # Property Editors
        prop_browser = PropertyBrowser()
        properties_widget = PropertiesWidget()
        # PropertyWidget requires a specific device and property to edit
        prop_widget = PropertyWidget(device_label="Camera", prop_name="Binning")

        # --- Organize widgets into a clear layout ---
        self.tabs = QTabWidget()

        # Tab 1: Configuration
        config_tab = QWidget()
        config_layout = QVBoxLayout(config_tab)
        config_layout.addWidget(cfg_widget)
        config_layout.addWidget(presets_widget)
        config_layout.addWidget(group_preset_table)
        config_layout.addWidget(ch_group_widget)
        config_layout.addWidget(ch_widget)
        config_layout.addWidget(channel_table)
        self.tabs.addTab(self._make_scrollable(config_tab), "Configuration")

        # Tab 2: Camera
        camera_tab = QWidget()
        camera_layout = QVBoxLayout(camera_tab)
        camera_layout.addWidget(default_exp_widget)
        camera_layout.addWidget(exp_widget)
        camera_layout.addWidget(roi_widget)
        self.tabs.addTab(camera_tab, "Camera")

        # Tab 3: Stage/Objectives
        stage_tab = QWidget()
        stage_layout = QVBoxLayout(stage_tab)
        stage_layout.addWidget(objectives_widget)
        stage_layout.addWidget(stage_widget)
        stage_layout.addWidget(position_table)
        self.tabs.addTab(stage_tab, "Stage/Objectives")

        # Tab 4: MDA
        mda_tab = QWidget()
        mda_layout = QVBoxLayout(mda_tab)
        mda_layout.addWidget(mda_widget)
        # also adding MDASequenceWidget for completeness as requested
        mda_layout.addWidget(mda_sequence_widget)
        mda_layout.addWidget(time_plan_widget)
        mda_layout.addWidget(grid_plan_widget)
        mda_layout.addWidget(z_plan_widget)
        self.tabs.addTab(self._make_scrollable(mda_tab), "MDA")

        # Tab 5: Setup & Tools
        tools_tab = QWidget()
        tools_layout = QVBoxLayout(tools_tab)
        tools_layout.addWidget(install_widget)
        tools_layout.addWidget(config_wizard)
        tools_layout.addWidget(pixel_config_widget)
        tools_layout.addWidget(obj_pixel_config_widget)
        tools_layout.addWidget(core_log_widget)
        self.tabs.addTab(self._make_scrollable(tools_tab), "Setup & Tools")

        # Tab 6: Property Editors
        props_tab = QWidget()
        props_layout = QVBoxLayout(props_tab)
        props_layout.addWidget(prop_browser)
        props_layout.addWidget(properties_widget)
        props_layout.addWidget(prop_widget)
        self.tabs.addTab(self._make_scrollable(props_tab), "Property Editors")

        # --- Set up the main application layout ---
        main_layout = QGridLayout(self)
        self.setLayout(main_layout)
        self.resize(1100, 850)

        main_layout.addWidget(image_preview, 0, 0, 1, 1)
        button_layout = QVBoxLayout()
        button_layout.addWidget(snap_button)
        button_layout.addWidget(live_button)
        main_layout.addLayout(button_layout, 1, 0)

        main_layout.addWidget(self.tabs, 0, 1, 2, 1)

        main_layout.setColumnStretch(0, 3)
        main_layout.setColumnStretch(1, 2)
        main_layout.setRowStretch(0, 1)

    def _make_scrollable(self, widget: QWidget) -> QScrollArea:
        """Helper function to wrap a widget in a scroll area."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        return scroll


# Create a QApplication and show MyWidget
if __name__ == "__main__":
    app = QApplication([])
    widget = MyWidget()
    widget.show()
    app.exec_()
