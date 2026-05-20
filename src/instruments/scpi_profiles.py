from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SCPIProfile:
    """Editable SCPI command profile for the Keysight E36300 family."""

    identify: str = "*IDN?"
    select_channel: str = "INST:SEL {channel}"
    source_voltage_mode: str = "SOUR:FUNC VOLT"
    set_voltage: str = "SOUR:VOLT {value:.9g}"
    set_current: str = "SOUR:CURR {value:.9g}"
    output_on: str = "OUTP ON"
    output_off: str = "OUTP OFF"
    measure_voltage: str = "MEAS:VOLT?"
    measure_current: str = "MEAS:CURR?"
    query_error: str = "SYST:ERR?"
    clear_status: str = "*CLS"

    def format(self, command_name: str, **kwargs: object) -> str:
        template = getattr(self, command_name)
        return template.format(**kwargs)


KEYSIGHT_E36300_PROFILE = SCPIProfile()
