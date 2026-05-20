from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MosfetOutputConfig:
    drain_channel: str = "CH1"
    gate_channel: str = "CH2"
    source_node: str = "COMMON_GND"


@dataclass(frozen=True)
class MosfetTransferConfig:
    drain_channel: str = "CH1"
    gate_channel: str = "CH2"
    vds_fixed_v: float = 1.0


@dataclass(frozen=True)
class BjtCurveTracerConfig:
    collector_channel: str = "CH1"
    base_channel: str = "CH2"
    base_resistor_ohm: float = 100_000.0


def run_mosfet_output_curves(*args: object, **kwargs: object) -> None:
    """TODO: Stage 2 - ID vs VDS for multiple VGS values and CSV export."""
    raise NotImplementedError("MOSFET output curves are planned for stage 2")


def run_mosfet_transfer_curve(*args: object, **kwargs: object) -> None:
    """TODO: Stage 2 - ID vs VGS, approximate gm, Vth, and sqrt(ID) plot."""
    raise NotImplementedError("MOSFET transfer curves are planned for stage 2")


def run_bjt_curve_tracer(*args: object, **kwargs: object) -> None:
    """TODO: Stage 2 - IC vs VCE for approximate IB steps using an external base resistor."""
    raise NotImplementedError("BJT curve tracer is planned for stage 2")
