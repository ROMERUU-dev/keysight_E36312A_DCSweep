from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SCPIProfile:
    """Editable SCPI command profile for the Keysight E36300 family."""

    identify: str = "*IDN?"
    select_channel: str = "INST:SEL {channel}"
    source_voltage_mode: str = ""
    set_voltage: str = "VOLT {value:.9g},(@{channel_number})"
    set_current: str = "CURR {value:.9g},(@{channel_number})"
    output_on: str = "OUTP ON,(@{channel_number})"
    output_off: str = "OUTP OFF,(@{channel_number})"
    measure_voltage: str = "MEAS:VOLT? (@{channel_number})"
    measure_current: str = "MEAS:CURR? (@{channel_number})"
    query_voltage: str = "VOLT? (@{channel_number})"
    query_current: str = "CURR? (@{channel_number})"
    query_output: str = "OUTP? (@{channel_number})"
    query_error: str = "SYST:ERR?"
    clear_status: str = "*CLS"

    def format(self, command_name: str, **kwargs: object) -> str:
        template = getattr(self, command_name)
        return template.format(**kwargs)


KEYSIGHT_E36300_PROFILE = SCPIProfile()
