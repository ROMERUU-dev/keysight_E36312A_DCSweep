from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


SWEEP_COLUMNS = [
    "timestamp_iso",
    "t_s",
    "channel",
    "Vset_V",
    "Vmeas_V",
    "Imeas_A",
    "P_W",
    "compliance_flag",
    "notes",
]


def _point_to_dict(point: Any) -> dict[str, Any]:
    if is_dataclass(point):
        return asdict(point)
    return dict(point)


def points_to_dataframe(points: Iterable[Any]) -> pd.DataFrame:
    rows = [_point_to_dict(point) for point in points]
    return pd.DataFrame(rows, columns=SWEEP_COLUMNS)


def export_sweep_csv(points: Iterable[Any], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe = points_to_dataframe(points)
    dataframe.to_csv(output_path, index=False)
    return output_path
