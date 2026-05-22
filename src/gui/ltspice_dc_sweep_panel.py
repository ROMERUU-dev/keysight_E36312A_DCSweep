from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.measurements.ltspice_dc_sweep import (
    SweepSource,
    generate_dc_directive,
    generate_nested_sweep_points,
    parse_values_list,
)
from src.measurements.sweep_engine import (
    DEFAULT_CURRENT_LIMIT_A,
    FixedSource,
    SweepRunConfig,
    preset_sweep_configs,
    sweep_run_config_from_dict,
    sweep_run_config_to_dict,
)
from src.utils.units import CHANNELS


AXIS_OPTIONS = [
    ("Source1 value", "source1_value"),
    ("Source2 value", "source2_value"),
    ("Source3 value", "source3_value"),
    ("CH1 Vmeas", "CH1_Vmeas"),
    ("CH2 Vmeas", "CH2_Vmeas"),
    ("CH3 Vmeas", "CH3_Vmeas"),
    ("time", "t_s"),
]

Y_OPTIONS = [
    ("CH1 Imeas", "CH1_Imeas"),
    ("CH2 Imeas", "CH2_Imeas"),
    ("CH3 Imeas", "CH3_Imeas"),
    ("CH1 Vmeas", "CH1_Vmeas"),
    ("CH2 Vmeas", "CH2_Vmeas"),
    ("CH3 Vmeas", "CH3_Vmeas"),
    ("CH1 P", "CH1_P"),
    ("CH2 P", "CH2_P"),
    ("CH3 P", "CH3_P"),
]

GROUP_OPTIONS = [
    ("Source2", "source2_value"),
    ("Source3", "source3_value"),
    ("None", "none"),
]


class LtspiceDCSweepPanel(QWidget):
    start_requested = Signal(object)
    stop_requested = Signal()
    emergency_stop_requested = Signal()
    validate_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.source_controls: list[dict[str, Any]] = []
        self.fixed_controls: dict[str, dict[str, Any]] = {}
        self.presets = preset_sweep_configs()

        self.sweep_name = QLineEdit("ltspice_dc_sweep")
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(self.presets.keys())
        self.mock_model_combo = QComboBox()
        self.mock_model_combo.addItem("Resistor", "resistor")
        self.mock_model_combo.addItem("Diode", "diode")
        self.mock_model_combo.addItem("NMOS", "nmos")

        top_form = QFormLayout()
        top_form.addRow("Sweep name", self.sweep_name)
        top_form.addRow("Preset", self._preset_row())
        top_form.addRow("Mock model", self.mock_model_combo)

        self.source_tabs = QTabWidget()
        for index, title in enumerate(("1st Source", "2nd Source", "3rd Source"), start=1):
            tab, controls = self._source_tab(index)
            self.source_controls.append(controls)
            self.source_tabs.addTab(tab, title)

        fixed_group = self._fixed_sources_group()
        timing_group = self._timing_group()
        plot_group = self._plot_group()

        self.directive_label = QLabel(".dc")
        self.directive_label.setTextInteractionFlags(self.directive_label.textInteractionFlags())
        self.point_count_label = QLabel("Points: -")
        preview_group = QGroupBox("DC Directive Preview")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.addWidget(self.directive_label)
        preview_layout.addWidget(self.point_count_label)

        buttons = QHBoxLayout()
        self.validate_button = QPushButton("Validate Sweep")
        self.start_button = QPushButton("Start Sweep")
        self.stop_button = QPushButton("Stop")
        self.emergency_button = QPushButton("Emergency Stop")
        self.emergency_button.setObjectName("emergencyButton")
        self.save_button = QPushButton("Save Config")
        self.load_button = QPushButton("Load Config")
        for button in (
            self.validate_button,
            self.start_button,
            self.stop_button,
            self.emergency_button,
            self.save_button,
            self.load_button,
        ):
            buttons.addWidget(button)

        self.status_label = QLabel("Idle")
        self.output_label = QLabel("Run folder: -")

        layout = QVBoxLayout(self)
        layout.addLayout(top_form)
        layout.addWidget(self.source_tabs)
        layout.addWidget(fixed_group)
        layout.addWidget(timing_group)
        layout.addWidget(plot_group)
        layout.addWidget(preview_group)
        layout.addLayout(buttons)
        layout.addWidget(self.status_label)
        layout.addWidget(self.output_label)
        layout.addStretch(1)

        self.validate_button.clicked.connect(self._emit_validate)
        self.start_button.clicked.connect(self._emit_start)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.emergency_button.clicked.connect(self.emergency_stop_requested.emit)
        self.save_button.clicked.connect(self._save_config)
        self.load_button.clicked.connect(self._load_config)

        self.set_running(False)
        self.set_config(self.presets["NMOS Output Curves"])

    def config(self) -> SweepRunConfig:
        return SweepRunConfig(
            sweep_name=self.sweep_name.text().strip() or "ltspice_dc_sweep",
            sources=[self._source_from_controls(controls) for controls in self.source_controls],
            fixed_sources=[self._fixed_source_from_controls(channel) for channel in CHANNELS],
            settle_time_s=self.settle_time.value(),
            compliance_tolerance=self.compliance_tolerance.value(),
            stop_on_compliance=self.stop_on_compliance.isChecked(),
            ramp_down_enabled=self.ramp_down_enabled.isChecked(),
            output_off_when_done=self.output_off_when_done.isChecked(),
            auto_export=self.auto_export.isChecked(),
            output_root=self.output_root.text().strip() or "runs",
            notes=self.notes.toPlainText().strip(),
            mock_model=str(self.mock_model_combo.currentData()),
            x_axis=str(self.x_axis_combo.currentData()),
            y_axis=str(self.y_axis_combo.currentData()),
            group_by=str(self.group_combo.currentData()),
            clear_plot_before_run=self.clear_plot_before_run.isChecked(),
            hold_previous_traces=self.hold_previous_traces.isChecked(),
            autoscale=self.autoscale.isChecked(),
            log_x=self.log_x.isChecked(),
            log_y=self.log_y.isChecked(),
        )

    def set_config(self, config: SweepRunConfig) -> None:
        self.sweep_name.setText(config.sweep_name)
        self._set_combo_data(self.mock_model_combo, config.mock_model)
        for index, controls in enumerate(self.source_controls):
            source = config.sources[index] if index < len(config.sources) else None
            self._set_source_controls(controls, source)

        fixed_by_channel = {source.channel: source for source in config.fixed_sources}
        for channel in CHANNELS:
            fixed_source = fixed_by_channel.get(
                channel,
                FixedSource(channel=channel, mode="off", current_limit=DEFAULT_CURRENT_LIMIT_A),
            )
            self._set_fixed_controls(channel, fixed_source)

        self.settle_time.setValue(config.settle_time_s)
        self.compliance_tolerance.setValue(config.compliance_tolerance)
        self.stop_on_compliance.setChecked(config.stop_on_compliance)
        self.ramp_down_enabled.setChecked(config.ramp_down_enabled)
        self.output_off_when_done.setChecked(config.output_off_when_done)
        self.auto_export.setChecked(config.auto_export)
        self.output_root.setText(config.output_root)
        self.notes.setPlainText(config.notes)
        self._set_combo_data(self.x_axis_combo, config.x_axis)
        self._set_combo_data(self.y_axis_combo, config.y_axis)
        self._set_combo_data(self.group_combo, config.group_by)
        self.clear_plot_before_run.setChecked(config.clear_plot_before_run)
        self.hold_previous_traces.setChecked(config.hold_previous_traces)
        self.autoscale.setChecked(config.autoscale)
        self.log_x.setChecked(config.log_x)
        self.log_y.setChecked(config.log_y)
        self._sync_fixed_modes_from_sources()
        self._update_preview()

    def set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.validate_button.setEnabled(not running)
        self.load_button.setEnabled(not running)
        self.save_button.setEnabled(not running)

    def set_status(self, status: str) -> None:
        self.status_label.setText(status)

    def set_output_dir(self, output_dir: str | None) -> None:
        self.output_label.setText(f"Run folder: {output_dir or '-'}")

    def _preset_row(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        load_button = QPushButton("Load Preset")
        layout.addWidget(self.preset_combo)
        layout.addWidget(load_button)
        load_button.clicked.connect(self._load_selected_preset)
        return widget

    def _source_tab(self, index: int) -> tuple[QWidget, dict[str, Any]]:
        widget = QWidget()
        controls: dict[str, Any] = {}
        controls["enabled"] = QCheckBox("Enable source")
        controls["enabled"].setChecked(index == 1)
        controls["name"] = QLineEdit("VIN" if index == 1 else f"SRC{index}")
        controls["channel"] = QComboBox()
        controls["channel"].addItems(CHANNELS)
        controls["mode"] = QComboBox()
        controls["mode"].addItem("Voltage", "voltage")
        controls["mode"].addItem("Current (future)", "current")
        current_item = controls["mode"].model().item(1)
        if current_item is not None:
            current_item.setEnabled(False)
        controls["sweep_type"] = QComboBox()
        controls["sweep_type"].addItem("Linear", "linear")
        controls["sweep_type"].addItem("Decade", "decade")
        controls["sweep_type"].addItem("Octave", "octave")
        controls["sweep_type"].addItem("List", "list")
        controls["start"] = self._double_spin(-25.0, 25.0, 0.0, " V")
        controls["stop"] = self._double_spin(-25.0, 25.0, 1.0, " V")
        controls["increment"] = self._double_spin(-25.0, 25.0, 0.1, " V")
        controls["points"] = QSpinBox()
        controls["points"].setRange(1, 1000)
        controls["points"].setValue(10)
        controls["list_values"] = QPlainTextEdit("0, 0.1, 0.2, 0.5, 1")
        controls["list_values"].setMaximumHeight(76)

        form = QFormLayout(widget)
        form.addRow(controls["enabled"])
        form.addRow("Name of source to sweep", controls["name"])
        form.addRow("Physical channel", controls["channel"])
        form.addRow("Source mode", controls["mode"])
        form.addRow("Type of sweep", controls["sweep_type"])
        form.addRow("Start value", controls["start"])
        form.addRow("Stop value", controls["stop"])
        form.addRow("Increment", controls["increment"])
        form.addRow("Points per decade/octave", controls["points"])
        form.addRow("List values", controls["list_values"])

        for control in (
            controls["enabled"],
            controls["name"],
            controls["channel"],
            controls["mode"],
            controls["sweep_type"],
            controls["start"],
            controls["stop"],
            controls["increment"],
            controls["points"],
            controls["list_values"],
        ):
            self._connect_change(control)
        controls["enabled"].stateChanged.connect(self._sync_fixed_modes_from_sources)
        controls["channel"].currentIndexChanged.connect(self._sync_fixed_modes_from_sources)
        return widget, controls

    def _fixed_sources_group(self) -> QGroupBox:
        group = QGroupBox("Fixed Sources")
        layout = QGridLayout(group)
        layout.addWidget(QLabel("Channel"), 0, 0)
        layout.addWidget(QLabel("Mode"), 0, 1)
        layout.addWidget(QLabel("Fixed voltage"), 0, 2)
        layout.addWidget(QLabel("Current limit"), 0, 3)
        for row, channel in enumerate(CHANNELS, start=1):
            mode = QComboBox()
            mode.addItem("Off", "off")
            mode.addItem("Fixed voltage", "fixed_voltage")
            mode.addItem("Swept source", "swept_source")
            voltage = self._double_spin(0.0, 25.0, 0.0, " V")
            current_limit = self._double_spin(0.000001, 5.0, DEFAULT_CURRENT_LIMIT_A, " A", decimals=6)
            self.fixed_controls[channel] = {
                "mode": mode,
                "voltage": voltage,
                "current_limit": current_limit,
            }
            layout.addWidget(QLabel(channel), row, 0)
            layout.addWidget(mode, row, 1)
            layout.addWidget(voltage, row, 2)
            layout.addWidget(current_limit, row, 3)
            self._connect_change(mode)
            self._connect_change(voltage)
            self._connect_change(current_limit)
        return group

    def _timing_group(self) -> QGroupBox:
        group = QGroupBox("Run Options")
        self.settle_time = self._double_spin(0.0, 60.0, 0.1, " s", decimals=3)
        self.compliance_tolerance = self._double_spin(0.0, 0.95, 0.02, "", decimals=3)
        self.stop_on_compliance = QCheckBox("Stop on compliance")
        self.stop_on_compliance.setChecked(True)
        self.ramp_down_enabled = QCheckBox("Ramp down to 0 V")
        self.ramp_down_enabled.setChecked(True)
        self.output_off_when_done = QCheckBox("Output off when done")
        self.output_off_when_done.setChecked(True)
        self.auto_export = QCheckBox("Auto export run folder")
        self.auto_export.setChecked(True)
        self.output_root = QLineEdit("runs")
        self.notes = QPlainTextEdit()
        self.notes.setMaximumHeight(58)

        form = QFormLayout(group)
        form.addRow("Settle time", self.settle_time)
        form.addRow("Compliance tolerance", self.compliance_tolerance)
        form.addRow(self.stop_on_compliance)
        form.addRow(self.ramp_down_enabled)
        form.addRow(self.output_off_when_done)
        form.addRow(self.auto_export)
        form.addRow("Output root", self.output_root)
        form.addRow("Notes", self.notes)

        for control in (
            self.settle_time,
            self.compliance_tolerance,
            self.stop_on_compliance,
            self.ramp_down_enabled,
            self.output_off_when_done,
            self.auto_export,
            self.output_root,
            self.notes,
        ):
            self._connect_change(control)
        return group

    def _plot_group(self) -> QGroupBox:
        group = QGroupBox("Plot Options")
        self.x_axis_combo = QComboBox()
        for label, value in AXIS_OPTIONS:
            self.x_axis_combo.addItem(label, value)
        self.y_axis_combo = QComboBox()
        for label, value in Y_OPTIONS:
            self.y_axis_combo.addItem(label, value)
        self.group_combo = QComboBox()
        for label, value in GROUP_OPTIONS:
            self.group_combo.addItem(label, value)
        self.clear_plot_before_run = QCheckBox("Clear plot before run")
        self.clear_plot_before_run.setChecked(True)
        self.hold_previous_traces = QCheckBox("Hold previous traces")
        self.autoscale = QCheckBox("Autoscale")
        self.autoscale.setChecked(True)
        self.log_x = QCheckBox("Log X")
        self.log_y = QCheckBox("Log Y")

        layout = QGridLayout(group)
        layout.addWidget(QLabel("X axis"), 0, 0)
        layout.addWidget(self.x_axis_combo, 0, 1)
        layout.addWidget(QLabel("Y axis"), 0, 2)
        layout.addWidget(self.y_axis_combo, 0, 3)
        layout.addWidget(QLabel("Group curves by"), 1, 0)
        layout.addWidget(self.group_combo, 1, 1)
        layout.addWidget(self.clear_plot_before_run, 2, 0)
        layout.addWidget(self.hold_previous_traces, 2, 1)
        layout.addWidget(self.autoscale, 2, 2)
        layout.addWidget(self.log_x, 3, 0)
        layout.addWidget(self.log_y, 3, 1)

        for control in (
            self.x_axis_combo,
            self.y_axis_combo,
            self.group_combo,
            self.clear_plot_before_run,
            self.hold_previous_traces,
            self.autoscale,
            self.log_x,
            self.log_y,
        ):
            self._connect_change(control)
        return group

    def _source_from_controls(self, controls: dict[str, Any]) -> SweepSource:
        sweep_type = str(controls["sweep_type"].currentData())
        values_list: list[float] = []
        if controls["enabled"].isChecked() and sweep_type == "list":
            values_list = parse_values_list(controls["list_values"].toPlainText())
        return SweepSource(
            name=controls["name"].text().strip(),
            channel=controls["channel"].currentText(),
            mode=str(controls["mode"].currentData()),
            sweep_type=sweep_type,
            start=controls["start"].value(),
            stop=controls["stop"].value(),
            increment=controls["increment"].value(),
            points_per_decade=controls["points"].value(),
            points_per_octave=controls["points"].value(),
            values_list=values_list,
            enabled=controls["enabled"].isChecked(),
        )

    def _fixed_source_from_controls(self, channel: str) -> FixedSource:
        controls = self.fixed_controls[channel]
        return FixedSource(
            channel=channel,
            mode=str(controls["mode"].currentData()),
            voltage=controls["voltage"].value(),
            current_limit=controls["current_limit"].value(),
        )

    def _set_source_controls(self, controls: dict[str, Any], source: SweepSource | None) -> None:
        source = source or SweepSource(name="", channel="CH1", enabled=False)
        controls["enabled"].setChecked(source.enabled)
        controls["name"].setText(source.name)
        self._set_combo_text(controls["channel"], source.channel)
        self._set_combo_data(controls["mode"], source.mode)
        self._set_combo_data(controls["sweep_type"], source.sweep_type)
        controls["start"].setValue(source.start)
        controls["stop"].setValue(source.stop)
        controls["increment"].setValue(source.increment if source.increment is not None else 0.1)
        controls["points"].setValue(source.points_per_decade or source.points_per_octave or 10)
        controls["list_values"].setPlainText(", ".join(f"{value:g}" for value in source.values_list or []))

    def _set_fixed_controls(self, channel: str, source: FixedSource) -> None:
        controls = self.fixed_controls[channel]
        self._set_combo_data(controls["mode"], source.mode)
        controls["voltage"].setValue(source.voltage)
        controls["current_limit"].setValue(source.current_limit)

    def _emit_start(self) -> None:
        try:
            self.start_requested.emit(self.config())
        except Exception as exc:
            QMessageBox.warning(self, "Invalid sweep", str(exc))
            self.set_status(f"Invalid sweep: {exc}")

    def _emit_validate(self) -> None:
        try:
            self.validate_requested.emit(self.config())
        except Exception as exc:
            QMessageBox.warning(self, "Invalid sweep", str(exc))
            self.set_status(f"Invalid sweep: {exc}")

    def _load_selected_preset(self) -> None:
        config = self.presets[self.preset_combo.currentText()]
        self.set_config(config)

    def _save_config(self) -> None:
        try:
            config = self.config()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid sweep", str(exc))
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save LTspice sweep config",
            str(Path("configs") / f"{config.sweep_name}.json"),
            "JSON files (*.json)",
        )
        if not path:
            return
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(sweep_run_config_to_dict(config), indent=2), encoding="utf-8")
        self.set_status(f"Saved {output}")

    def _load_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load LTspice sweep config",
            "configs",
            "JSON files (*.json)",
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self.set_config(sweep_run_config_from_dict(data))
            self.set_status(f"Loaded {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Load config error", str(exc))

    def _sync_fixed_modes_from_sources(self) -> None:
        swept_channels = {
            controls["channel"].currentText()
            for controls in self.source_controls
            if controls["enabled"].isChecked()
        }
        for channel in CHANNELS:
            mode_combo = self.fixed_controls[channel]["mode"]
            mode = str(mode_combo.currentData())
            if channel in swept_channels and mode != "fixed_voltage":
                self._set_combo_data(mode_combo, "swept_source")
            elif channel not in swept_channels and mode == "swept_source":
                self._set_combo_data(mode_combo, "off")
        self._update_preview()

    def _update_preview(self) -> None:
        try:
            config = self.config()
            directive = generate_dc_directive(config.sources)
            points = generate_nested_sweep_points(config.sources)
            self.directive_label.setText(directive)
            self.point_count_label.setText(f"Points: {len(points)}")
        except Exception as exc:
            self.directive_label.setText(f"Invalid: {exc}")
            self.point_count_label.setText("Points: -")

    def _connect_change(self, widget: QWidget) -> None:
        if isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(self._update_preview)
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(self._update_preview)
        elif isinstance(widget, QDoubleSpinBox):
            widget.valueChanged.connect(self._update_preview)
        elif isinstance(widget, QSpinBox):
            widget.valueChanged.connect(self._update_preview)
        elif isinstance(widget, QCheckBox):
            widget.stateChanged.connect(self._update_preview)
        elif isinstance(widget, QPlainTextEdit):
            widget.textChanged.connect(self._update_preview)

    @staticmethod
    def _double_spin(
        minimum: float,
        maximum: float,
        value: float,
        suffix: str,
        *,
        decimals: int = 6,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(0.1)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def _set_combo_text(combo: QComboBox, value: str) -> None:
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)
