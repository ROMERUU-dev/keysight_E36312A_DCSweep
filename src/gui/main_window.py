from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QMainWindow, QMessageBox, QSplitter, QTabWidget

from src.gui.connection_panel import ConnectionPanel
from src.gui.ltspice_dc_sweep_panel import LtspiceDCSweepPanel
from src.gui.manual_control_panel import ManualControlPanel
from src.gui.plot_panel import PlotPanel
from src.gui.settings_panel import SettingsPanel
from src.gui.sweep_panel import SweepPanel
from src.gui.transistor_panel import TransistorPanel
from src.instruments.keysight_supply import KeysightSupply
from src.instruments.visa_manager import MOCK_RESOURCE, VisaManager
from src.measurements.data_export import export_sweep_csv
from src.measurements.dc_sweep import SweepParameters, SweepPoint, run_dc_sweep
from src.measurements.ltspice_dc_sweep import generate_dc_directive, generate_nested_sweep_points
from src.measurements.safety import SafetyError, SafetyLimits
from src.measurements.sweep_engine import (
    SweepMeasurementPoint,
    SweepRunConfig,
    SweepRunResult,
    run_ltspice_dc_sweep,
    validate_sweep_run_config,
)
from src.utils.units import CHANNELS


LOGGER = logging.getLogger(__name__)


class SweepWorker(QObject):
    point_ready = Signal(object)
    error = Signal(str)
    finished = Signal(object)

    def __init__(
        self,
        supply: KeysightSupply,
        params: SweepParameters,
        limits: SafetyLimits,
    ) -> None:
        super().__init__()
        self.supply = supply
        self.params = params
        self.limits = limits
        self._stop_requested = False

    @Slot()
    def run(self) -> None:
        points: list[SweepPoint] = []
        try:
            points = run_dc_sweep(
                self.supply,
                self.params,
                self.limits,
                stop_requested=lambda: self._stop_requested,
                on_point=self.point_ready.emit,
            )
            try:
                self.supply.ramp_to_zero_and_off(self.params.channel, step_v=0.2, delay_s=0.0)
            except Exception as exc:
                LOGGER.warning("Could not ramp channel down after sweep: %s", exc)
        except Exception as exc:
            LOGGER.exception("Sweep failed")
            try:
                self.supply.safe_shutdown(close=True)
            except Exception as shutdown_exc:
                LOGGER.warning("Safe shutdown after sweep error failed: %s", shutdown_exc)
            self.error.emit(str(exc))
        finally:
            self.finished.emit(points)

    def stop(self) -> None:
        self._stop_requested = True


class LtspiceSweepWorker(QObject):
    point_ready = Signal(object)
    error = Signal(str)
    finished = Signal(object)

    def __init__(
        self,
        supply: KeysightSupply,
        config: SweepRunConfig,
        limits: SafetyLimits,
    ) -> None:
        super().__init__()
        self.supply = supply
        self.config = config
        self.limits = limits
        self._stop_requested = False

    @Slot()
    def run(self) -> None:
        result = SweepRunResult(points=[])
        try:
            result = run_ltspice_dc_sweep(
                self.supply,
                self.config,
                self.limits,
                stop_requested=lambda: self._stop_requested,
                on_point=self.point_ready.emit,
            )
        except Exception as exc:
            LOGGER.exception("LTspice-style sweep failed")
            try:
                self.supply.safe_shutdown(close=True)
            except Exception as shutdown_exc:
                LOGGER.warning("Safe shutdown after LTspice sweep error failed: %s", shutdown_exc)
            self.error.emit(str(exc))
        finally:
            self.finished.emit(result)

    def stop(self) -> None:
        self._stop_requested = True


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        mock: bool = False,
        config_path: str | Path = "config.json",
    ) -> None:
        super().__init__()
        self.setWindowTitle("Keysight E36312A DC Sweep")
        self.resize(1180, 760)

        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.visa_manager = VisaManager()
        self.safety_limits = SafetyLimits()
        self.supply = KeysightSupply(mock=mock, safety_limits=self.safety_limits)
        self.sweep_points: list[SweepPoint] = []
        self.ltspice_sweep_points: list[SweepMeasurementPoint] = []
        self.sweep_thread: QThread | None = None
        self.sweep_worker: SweepWorker | LtspiceSweepWorker | None = None

        self.connection_panel = ConnectionPanel()
        self.manual_panel = ManualControlPanel()
        self.sweep_panel = SweepPanel()
        self.ltspice_panel = LtspiceDCSweepPanel()
        self.transistor_panel = TransistorPanel()
        self.settings_panel = SettingsPanel(self.safety_limits)
        self.plot_panel = PlotPanel()

        tabs = QTabWidget()
        tabs.addTab(self.connection_panel, "Connection")
        tabs.addTab(self.manual_panel, "Manual")
        tabs.addTab(self.sweep_panel, "Simple DC Sweep")
        tabs.addTab(self.ltspice_panel, "LTspice DC Sweep")
        tabs.addTab(self.transistor_panel, "Transistor")
        tabs.addTab(self.settings_panel, "Settings")

        splitter = QSplitter()
        splitter.addWidget(tabs)
        splitter.addWidget(self.plot_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        self.setCentralWidget(splitter)

        self._connect_signals()
        self.refresh_resources()
        self._apply_styles()

        if mock:
            self.connection_panel.select_mock()
            QTimer.singleShot(0, lambda: self.connect_resource(MOCK_RESOURCE, True))
        elif self.config.get("last_resource"):
            self.connection_panel.set_resources(
                self.visa_manager.list_resources(include_mock=True),
                str(self.config["last_resource"]),
            )
    def _connect_signals(self) -> None:
        self.connection_panel.refresh_requested.connect(self.refresh_resources)
        self.connection_panel.connect_requested.connect(self.connect_resource)
        self.connection_panel.disconnect_requested.connect(self.disconnect_resource)
        self.connection_panel.emergency_stop_requested.connect(self.emergency_stop)

        self.manual_panel.set_voltage_requested.connect(self.set_voltage)
        self.manual_panel.set_current_requested.connect(self.set_current_limit)
        self.manual_panel.output_requested.connect(self.set_output)
        self.manual_panel.measure_requested.connect(self.measure_channel)
        self.manual_panel.all_off_requested.connect(self.all_off)
        self.manual_panel.ramp_zero_requested.connect(self.ramp_all_to_zero)

        self.sweep_panel.start_requested.connect(self.start_sweep)
        self.sweep_panel.stop_requested.connect(self.stop_sweep)
        self.sweep_panel.export_requested.connect(self.export_current_sweep)

        self.ltspice_panel.start_requested.connect(self.start_ltspice_sweep)
        self.ltspice_panel.stop_requested.connect(self.stop_sweep)
        self.ltspice_panel.emergency_stop_requested.connect(self.emergency_stop)
        self.ltspice_panel.validate_requested.connect(self.validate_ltspice_sweep)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QPushButton#emergencyButton {
                background-color: #b00020;
                color: white;
                font-weight: 700;
                padding: 8px;
            }
            """
        )

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            LOGGER.warning("Could not read config file: %s", exc)
            return {}

    def _save_config(self) -> None:
        data = {
            "last_resource": self.connection_panel.resource_combo.currentText().strip(),
            "shutdown_on_close": self.settings_panel.should_shutdown_on_close(),
        }
        self.config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @Slot()
    def refresh_resources(self) -> None:
        resources = self.visa_manager.list_resources(include_mock=True)
        preferred = str(self.config.get("last_resource", "")) or None
        self.connection_panel.set_resources(resources, preferred)

    @Slot(str, bool)
    def connect_resource(self, resource: str, mock: bool) -> None:
        try:
            if self.supply.connected:
                self.supply.safe_shutdown(close=True)

            resource = resource or MOCK_RESOURCE
            self.supply = KeysightSupply(
                resource,
                mock=mock or resource.upper().startswith("MOCK"),
                safety_limits=self.safety_limits,
            )
            self.supply.connect()
            self.supply.output_all_off()
            identity = self.supply.identify()
            self.connection_panel.set_identity(identity)
            self.connection_panel.set_connected(True)
            self.connection_panel.set_status(f"Connected: {resource}")
            self._save_config()
        except Exception as exc:
            LOGGER.exception("Connection failed")
            self.connection_panel.set_status(f"Connection failed: {exc}")
            QMessageBox.critical(self, "Connection error", str(exc))

    @Slot()
    def disconnect_resource(self) -> None:
        try:
            if self.supply.connected:
                self.supply.safe_shutdown(close=True)
        finally:
            self.connection_panel.set_connected(False)
            self.connection_panel.set_status("Disconnected")
            self.connection_panel.set_identity("")

    @Slot()
    def emergency_stop(self) -> None:
        self.stop_sweep()
        try:
            if self.supply.connected:
                self.supply.safe_shutdown(close=False)
            self.connection_panel.set_status("Emergency stop executed")
        except Exception as exc:
            LOGGER.exception("Emergency stop failed")
            self.connection_panel.set_status(f"Emergency stop failed: {exc}")

    @Slot(str, float)
    def set_voltage(self, channel: str, voltage: float) -> None:
        self._instrument_action(lambda: self.supply.set_voltage(channel, voltage))

    @Slot(str, float)
    def set_current_limit(self, channel: str, current: float) -> None:
        self._instrument_action(lambda: self.supply.set_current_limit(channel, current))

    @Slot(str, bool)
    def set_output(self, channel: str, on: bool) -> None:
        if on:
            self._instrument_action(lambda: self.supply.output_on(channel))
        else:
            self._instrument_action(lambda: self.supply.output_off(channel))

    @Slot(str)
    def measure_channel(self, channel: str) -> None:
        def action() -> None:
            voltage = self.supply.measure_voltage(channel)
            current = self.supply.measure_current(channel)
            self.manual_panel.set_measurements(channel, voltage, current)

        self._instrument_action(action)

    @Slot()
    def all_off(self) -> None:
        self._instrument_action(self.supply.output_all_off)

    @Slot()
    def ramp_all_to_zero(self) -> None:
        def action() -> None:
            for channel in CHANNELS:
                self.supply.ramp_to_zero_and_off(channel)

        self._instrument_action(action)

    def _instrument_action(self, action: Any) -> None:
        if not self.supply.connected:
            QMessageBox.warning(self, "Instrument not connected", "Connect an instrument first.")
            return
        try:
            action()
            self.connection_panel.set_status("OK")
        except SafetyError as exc:
            LOGGER.warning("Safety validation rejected action: %s", exc)
            self.connection_panel.set_status(f"Safety limit: {exc}")
            QMessageBox.warning(self, "Safety limit", str(exc))
        except Exception as exc:
            LOGGER.exception("Instrument action failed")
            try:
                self.supply.safe_shutdown(close=True)
            except Exception as shutdown_exc:
                LOGGER.warning("Safe shutdown after action error failed: %s", shutdown_exc)
            self.connection_panel.set_connected(self.supply.connected)
            self.connection_panel.set_status(f"Error: {exc}")
            QMessageBox.critical(self, "Instrument error", str(exc))

    @Slot(object)
    def start_sweep(self, params: SweepParameters) -> None:
        if not self.supply.connected:
            QMessageBox.warning(self, "Instrument not connected", "Connect an instrument first.")
            return
        if self.sweep_thread is not None:
            QMessageBox.warning(self, "Sweep running", "Stop the active sweep before starting another.")
            return

        self.sweep_points.clear()
        self.plot_panel.clear()
        self.sweep_panel.set_running(True)
        self.sweep_panel.set_status("Running")
        self.manual_panel.set_controls_enabled(False)

        self.sweep_thread = QThread(self)
        self.sweep_worker = SweepWorker(self.supply, params, self.safety_limits)
        self.sweep_worker.moveToThread(self.sweep_thread)
        self.sweep_thread.started.connect(self.sweep_worker.run)
        self.sweep_worker.point_ready.connect(self.on_sweep_point)
        self.sweep_worker.error.connect(self.on_sweep_error)
        self.sweep_worker.finished.connect(self.on_sweep_finished)
        self.sweep_worker.finished.connect(self.sweep_thread.quit)
        self.sweep_worker.finished.connect(self.sweep_worker.deleteLater)
        self.sweep_thread.finished.connect(self.sweep_thread.deleteLater)
        self.sweep_thread.start()

    @Slot(object)
    def validate_ltspice_sweep(self, config: SweepRunConfig) -> None:
        try:
            config = validate_sweep_run_config(config, self.safety_limits)
            point_count = len(generate_nested_sweep_points(config.sources))
            directive = generate_dc_directive(config.sources)
            self.ltspice_panel.set_status(f"Valid: {point_count} points, {directive}")
        except Exception as exc:
            self.ltspice_panel.set_status(f"Invalid sweep: {exc}")
            QMessageBox.warning(self, "Invalid sweep", str(exc))

    @Slot(object)
    def start_ltspice_sweep(self, config: SweepRunConfig) -> None:
        if not self.supply.connected:
            QMessageBox.warning(self, "Instrument not connected", "Connect an instrument first.")
            return
        if self.sweep_thread is not None:
            QMessageBox.warning(self, "Sweep running", "Stop the active sweep before starting another.")
            return

        try:
            config = validate_sweep_run_config(config, self.safety_limits)
        except Exception as exc:
            self.ltspice_panel.set_status(f"Invalid sweep: {exc}")
            QMessageBox.warning(self, "Invalid sweep", str(exc))
            return

        self.ltspice_sweep_points.clear()
        self.plot_panel.configure_ltspice(config)
        self.ltspice_panel.set_running(True)
        self.sweep_panel.set_running(True)
        self.ltspice_panel.set_status("Running")
        self.ltspice_panel.set_output_dir(None)
        self.manual_panel.set_controls_enabled(False)

        self.sweep_thread = QThread(self)
        self.sweep_worker = LtspiceSweepWorker(self.supply, config, self.safety_limits)
        self.sweep_worker.moveToThread(self.sweep_thread)
        self.sweep_thread.started.connect(self.sweep_worker.run)
        self.sweep_worker.point_ready.connect(self.on_ltspice_sweep_point)
        self.sweep_worker.error.connect(self.on_ltspice_sweep_error)
        self.sweep_worker.finished.connect(self.on_ltspice_sweep_finished)
        self.sweep_worker.finished.connect(self.sweep_thread.quit)
        self.sweep_worker.finished.connect(self.sweep_worker.deleteLater)
        self.sweep_thread.finished.connect(self.sweep_thread.deleteLater)
        self.sweep_thread.start()

    @Slot()
    def stop_sweep(self) -> None:
        if self.sweep_worker is not None:
            self.sweep_worker.stop()
            self.sweep_panel.set_status("Stopping")
            self.ltspice_panel.set_status("Stopping")

    @Slot(object)
    def on_sweep_point(self, point: SweepPoint) -> None:
        self.sweep_points.append(point)
        self.plot_panel.append_point(point)
        flag = " compliance" if point.compliance_flag else ""
        self.sweep_panel.set_status(
            f"{len(self.sweep_points)} points, V={point.Vmeas_V:.6g} V, "
            f"I={point.Imeas_A:.6g} A{flag}"
        )

    @Slot(str)
    def on_sweep_error(self, message: str) -> None:
        QMessageBox.critical(self, "Sweep error", message)
        self.connection_panel.set_status(f"Sweep error: {message}")
        self.connection_panel.set_connected(self.supply.connected)

    @Slot(object)
    def on_sweep_finished(self, points: list[SweepPoint]) -> None:
        self.sweep_points = list(points)
        self.sweep_panel.set_running(False)
        self.ltspice_panel.set_running(False)
        self.manual_panel.set_controls_enabled(True)
        self.sweep_panel.set_status(f"Finished with {len(self.sweep_points)} points")
        self.sweep_worker = None
        self.sweep_thread = None

    @Slot(object)
    def on_ltspice_sweep_point(self, point: SweepMeasurementPoint) -> None:
        self.ltspice_sweep_points.append(point)
        self.plot_panel.append_point(point)
        source_text = ""
        if point.source1_name:
            source_text = f"{point.source1_name}={point.source1_value:.6g}"
        flag = " compliance" if point.compliance_flag else ""
        self.ltspice_panel.set_status(
            f"{len(self.ltspice_sweep_points)} points, {source_text}, "
            f"CH1 I={point.CH1_Imeas:.6g} A{flag}"
        )

    @Slot(str)
    def on_ltspice_sweep_error(self, message: str) -> None:
        QMessageBox.critical(self, "LTspice sweep error", message)
        self.connection_panel.set_status(f"LTspice sweep error: {message}")
        self.connection_panel.set_connected(self.supply.connected)

    @Slot(object)
    def on_ltspice_sweep_finished(self, result: SweepRunResult) -> None:
        self.ltspice_sweep_points = list(result.points)
        self.ltspice_panel.set_running(False)
        self.sweep_panel.set_running(False)
        self.manual_panel.set_controls_enabled(True)
        self.ltspice_panel.set_output_dir(result.output_dir)
        if result.output_dir:
            try:
                self.plot_panel.save_png(Path(result.output_dir) / "plot.png")
            except Exception as exc:
                LOGGER.warning("Could not save LTspice sweep plot: %s", exc)
        self.ltspice_panel.set_status(f"Finished with {len(self.ltspice_sweep_points)} points")
        self.sweep_worker = None
        self.sweep_thread = None

    @Slot()
    def export_current_sweep(self) -> None:
        if not self.sweep_points:
            QMessageBox.information(self, "No data", "Run a sweep before exporting.")
            return
        output = Path("runs") / "sweeps" / "dc_sweep_latest.csv"
        try:
            path = export_sweep_csv(self.sweep_points, output)
            self.sweep_panel.set_csv_path(str(path))
            self.connection_panel.set_status(f"Exported {path}")
        except Exception as exc:
            LOGGER.exception("Export failed")
            QMessageBox.critical(self, "Export error", str(exc))

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        try:
            self.stop_sweep()
            if self.sweep_thread is not None:
                self.sweep_thread.quit()
                self.sweep_thread.wait(1500)
            if self.supply.connected:
                shutdown = self.settings_panel.should_shutdown_on_close()
                reply = QMessageBox.question(
                    self,
                    "Close application",
                    "Turn all outputs off before closing?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes if shutdown else QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    self.supply.safe_shutdown(close=True)
                else:
                    self.supply.disconnect()
            self._save_config()
        finally:
            event.accept()

    def current_points_as_dicts(self) -> list[dict[str, object]]:
        return [asdict(point) for point in self.sweep_points]
