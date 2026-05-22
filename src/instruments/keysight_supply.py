from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any

from src.instruments.scpi_profiles import KEYSIGHT_E36300_PROFILE, SCPIProfile
from src.instruments.visa_manager import MOCK_RESOURCE, VisaManager
from src.measurements.safety import SafetyLimits
from src.utils.units import CHANNELS, normalize_channel


LOGGER = logging.getLogger(__name__)
CHANNEL_NUMBERS = {"CH1": 1, "CH2": 2, "CH3": 3}


@dataclass
class MockChannelState:
    voltage_v: float = 0.0
    current_limit_a: float = 0.1
    output_on: bool = False
    load_ohm: float = 1_000.0


@dataclass
class MockVisaResource:
    """Deterministic SCPI-like mock for GUI and test runs without hardware."""

    selected_channel: str = "CH1"
    model: str = "resistor"
    channels: dict[str, MockChannelState] = field(
        default_factory=lambda: {channel: MockChannelState() for channel in CHANNELS}
    )
    closed: bool = False

    def write(self, command: str) -> None:
        command = command.strip()
        upper = command.upper()
        if self.closed:
            raise RuntimeError("Mock resource is closed")

        if upper.startswith("INST:SEL"):
            self.selected_channel = normalize_channel(command.split()[-1])
            return

        channel = self._channel_from_command(command)
        state = self.channels[channel]
        if upper.startswith("SOUR:FUNC"):
            return
        if upper.startswith(("SOUR:VOLT", "VOLT ")):
            state.voltage_v = self._first_float(command)
            return
        if upper.startswith(("SOUR:CURR", "CURR ")):
            state.current_limit_a = self._first_float(command)
            return
        if upper.startswith("OUTP ON"):
            state.output_on = True
            return
        if upper.startswith("OUTP OFF"):
            state.output_on = False
            return
        if upper in {"*CLS", "*RST"}:
            return
        raise RuntimeError(f"Unsupported mock SCPI write: {command}")

    def query(self, command: str) -> str:
        command = command.strip()
        upper = command.upper()
        if self.closed:
            raise RuntimeError("Mock resource is closed")

        if upper == "*IDN?":
            return "KEYSIGHT TECHNOLOGIES,E36312A,MOCK0000,1.0"
        channel = self._channel_from_command(command)
        if upper.startswith("MEAS:VOLT?"):
            return f"{self._measured_voltage(channel):.9g}"
        if upper.startswith("MEAS:CURR?"):
            return f"{self._measured_current(channel):.9g}"
        if upper.startswith("VOLT?"):
            return f"{self.channels[channel].voltage_v:.9g}"
        if upper.startswith("CURR?"):
            return f"{self.channels[channel].current_limit_a:.9g}"
        if upper.startswith("OUTP?"):
            return "1" if self.channels[channel].output_on else "0"
        if upper == "SYST:ERR?":
            return '0,"No error"'
        raise RuntimeError(f"Unsupported mock SCPI query: {command}")

    def close(self) -> None:
        self.closed = True

    def set_model(self, model: str) -> None:
        normalized = model.strip().lower()
        if normalized not in {"resistor", "diode", "nmos"}:
            raise ValueError(f"Unsupported mock model: {model!r}")
        self.model = normalized

    def _measured_current(self, channel: str) -> float:
        state = self.channels[channel]
        if not state.output_on:
            return 0.0
        ideal_current = self._ideal_current(channel)
        limit = abs(state.current_limit_a)
        if ideal_current >= 0:
            return min(ideal_current, limit)
        return max(ideal_current, -limit)

    def _measured_voltage(self, channel: str) -> float:
        state = self.channels[channel]
        if not state.output_on:
            return 0.0
        ideal_current = self._ideal_current(channel)
        if self.model == "resistor" and ideal_current > state.current_limit_a:
            return state.current_limit_a * state.load_ohm
        return state.voltage_v

    def _ideal_current(self, channel: str) -> float:
        if self.model == "diode":
            return self._diode_current(channel)
        if self.model == "nmos":
            return self._nmos_current(channel)
        state = self.channels[channel]
        return state.voltage_v / state.load_ohm

    def _diode_current(self, channel: str) -> float:
        voltage = self.channels[channel].voltage_v
        if voltage <= 0:
            return 0.0
        saturation_current = 1e-12
        n_vt = 0.052
        exponent = min(voltage / n_vt, 60.0)
        return saturation_current * (math.exp(exponent) - 1.0)

    def _nmos_current(self, channel: str) -> float:
        if channel == "CH2":
            return 1e-9 if self.channels[channel].output_on else 0.0
        if channel != "CH1":
            return 0.0
        vds = max(self.channels["CH1"].voltage_v, 0.0)
        vgs = max(self.channels["CH2"].voltage_v, 0.0)
        threshold = 1.0
        k = 0.02
        overdrive = vgs - threshold
        if overdrive <= 0:
            return 1e-9
        if vds < overdrive:
            return k * (overdrive * vds - (vds**2) / 2.0)
        return 0.5 * k * overdrive**2

    def _channel_from_command(self, command: str) -> str:
        match = re.search(r"@\s*([1-3])", command)
        if match:
            return normalize_channel(match.group(1))
        return self.selected_channel

    @staticmethod
    def _first_float(command: str) -> float:
        match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?", command)
        if not match:
            raise RuntimeError(f"No numeric value found in mock SCPI command: {command}")
        return float(match.group(0))


class KeysightSupply:
    """High-level Keysight E36312A/E36300 supply driver."""

    def __init__(
        self,
        resource_name: str | None = None,
        *,
        mock: bool = False,
        profile: SCPIProfile = KEYSIGHT_E36300_PROFILE,
        visa_manager: VisaManager | None = None,
        safety_limits: SafetyLimits | None = None,
    ) -> None:
        self.resource_name = resource_name or (MOCK_RESOURCE if mock else "")
        self.mock = mock or self.resource_name.upper().startswith("MOCK")
        self.profile = profile
        self.visa_manager = visa_manager or VisaManager()
        self.safety_limits = safety_limits or SafetyLimits()
        self.resource: Any | None = None

    @property
    def connected(self) -> bool:
        return self.resource is not None

    def connect(self, resource_name: str | None = None) -> None:
        if resource_name:
            self.resource_name = resource_name
            self.mock = resource_name.upper().startswith("MOCK")

        if self.connected:
            return

        if self.mock:
            self.resource = MockVisaResource()
        else:
            if not self.resource_name:
                raise RuntimeError("No VISA resource selected")
            self.resource = self.visa_manager.open_resource(self.resource_name)

        self._write(self.profile.clear_status)
        LOGGER.info("Connected to %s", self.resource_name)

    def disconnect(self) -> None:
        if self.resource is not None:
            try:
                self.resource.close()
            finally:
                LOGGER.info("Disconnected from %s", self.resource_name)
                self.resource = None

    def identify(self) -> str:
        return self._query(self.profile.identify)

    def select_channel(self, channel: str | int) -> str:
        normalized = normalize_channel(channel)
        self._write(self.profile.format("select_channel", channel=normalized))
        return normalized

    def set_voltage(self, channel: str | int, voltage: float) -> None:
        normalized = self.select_channel(channel)
        self.safety_limits.validate_voltage(normalized, voltage)
        if self.profile.source_voltage_mode:
            self._write(self.profile.source_voltage_mode)
        self._write(
            self.profile.format(
                "set_voltage",
                value=voltage,
                channel_number=self._channel_number(normalized),
            )
        )

    def set_current_limit(self, channel: str | int, current: float) -> None:
        normalized = self.select_channel(channel)
        self.safety_limits.validate_current(normalized, current)
        self._write(
            self.profile.format(
                "set_current",
                value=current,
                channel_number=self._channel_number(normalized),
            )
        )

    def output_on(self, channel: str | int) -> None:
        normalized = self.select_channel(channel)
        self._write(self.profile.format("output_on", channel_number=self._channel_number(normalized)))

    def output_off(self, channel: str | int) -> None:
        normalized = self.select_channel(channel)
        self._write(self.profile.format("output_off", channel_number=self._channel_number(normalized)))

    def output_all_off(self) -> None:
        for channel in CHANNELS:
            try:
                self.output_off(channel)
            except Exception as exc:
                LOGGER.warning("Could not turn %s off: %s", channel, exc)

    def measure_voltage(self, channel: str | int) -> float:
        normalized = self.select_channel(channel)
        return float(
            self._query(
                self.profile.format(
                    "measure_voltage",
                    channel_number=self._channel_number(normalized),
                )
            )
        )

    def measure_current(self, channel: str | int) -> float:
        normalized = self.select_channel(channel)
        return float(
            self._query(
                self.profile.format(
                    "measure_current",
                    channel_number=self._channel_number(normalized),
                )
            )
        )

    def query_error(self) -> str:
        return self._query(self.profile.query_error)

    def query_voltage_setpoint(self, channel: str | int) -> float:
        normalized = self.select_channel(channel)
        return float(
            self._query(
                self.profile.format(
                    "query_voltage",
                    channel_number=self._channel_number(normalized),
                )
            )
        )

    def query_current_limit(self, channel: str | int) -> float:
        normalized = self.select_channel(channel)
        return float(
            self._query(
                self.profile.format(
                    "query_current",
                    channel_number=self._channel_number(normalized),
                )
            )
        )

    def query_output_state(self, channel: str | int) -> bool:
        normalized = self.select_channel(channel)
        response = self._query(
            self.profile.format(
                "query_output",
                channel_number=self._channel_number(normalized),
            )
        )
        return response.strip().upper() in {"1", "ON"}

    def ramp_to_zero_and_off(
        self,
        channel: str | int,
        *,
        step_v: float = 0.1,
        delay_s: float = 0.03,
    ) -> None:
        normalized = normalize_channel(channel)
        try:
            current_voltage = max(0.0, self.measure_voltage(normalized))
        except Exception:
            current_voltage = 0.0

        step = max(abs(step_v), 0.001)
        while current_voltage > 0:
            current_voltage = max(0.0, current_voltage - step)
            self.set_voltage(normalized, current_voltage)
            if delay_s:
                time.sleep(delay_s)
        self.output_off(normalized)

    def safe_shutdown(self, *, close: bool = False) -> None:
        if not self.connected:
            return
        for channel in CHANNELS:
            try:
                self.set_voltage(channel, 0.0)
            except Exception as exc:
                LOGGER.warning("Could not set %s to 0 V during shutdown: %s", channel, exc)
        self.output_all_off()
        if close:
            self.disconnect()

    def set_mock_model(self, model: str) -> None:
        if not self.mock:
            return
        resource = self._require_resource()
        if hasattr(resource, "set_model"):
            resource.set_model(model)

    def _require_resource(self) -> Any:
        if self.resource is None:
            raise RuntimeError("Instrument is not connected")
        return self.resource

    def _write(self, command: str) -> None:
        LOGGER.debug("SCPI >> %s", command)
        self._require_resource().write(command)
        self._raise_on_scpi_error(command)

    def _query(self, command: str) -> str:
        LOGGER.debug("SCPI ?? %s", command)
        response = str(self._require_resource().query(command)).strip()
        LOGGER.debug("SCPI << %s", response)
        return response

    @staticmethod
    def _channel_number(channel: str | int) -> int:
        return CHANNEL_NUMBERS[normalize_channel(channel)]

    def _raise_on_scpi_error(self, command: str) -> None:
        if command.strip().upper() == self.profile.query_error:
            return
        response = str(self._require_resource().query(self.profile.query_error)).strip()
        LOGGER.debug("SCPI << %s", response)
        if response.startswith(("+0", "0,")):
            return
        raise RuntimeError(f"SCPI error after {command!r}: {response}")
