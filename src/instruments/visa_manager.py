from __future__ import annotations

import logging
from typing import Any


LOGGER = logging.getLogger(__name__)
MOCK_RESOURCE = "MOCK::E36312A::INSTR"


class VisaManager:
    """Small wrapper around PyVISA resource discovery/opening."""

    def __init__(self, backend: str | None = None) -> None:
        self.backend = backend
        self._resource_manager: Any | None = None

    def _manager(self) -> Any:
        if self._resource_manager is None:
            try:
                import pyvisa
            except ImportError as exc:
                raise RuntimeError(
                    "PyVISA is not installed. Install dependencies with "
                    "`python -m pip install -r requirements.txt`."
                ) from exc

            try:
                self._resource_manager = (
                    pyvisa.ResourceManager(self.backend)
                    if self.backend
                    else pyvisa.ResourceManager()
                )
            except Exception:
                if self.backend:
                    raise
                LOGGER.warning("Default VISA backend unavailable; falling back to pyvisa-py (@py)")
                self.backend = "@py"
                self._resource_manager = pyvisa.ResourceManager(self.backend)
        return self._resource_manager

    def list_resources(self, include_mock: bool = False) -> list[str]:
        resources: list[str] = []
        if include_mock:
            resources.append(MOCK_RESOURCE)

        try:
            resources.extend(str(item) for item in self._manager().list_resources())
        except Exception as exc:  # pragma: no cover - depends on host VISA setup
            LOGGER.warning("Could not list VISA resources: %s", exc)

        return resources

    def open_resource(self, resource_name: str, timeout_ms: int = 5000) -> Any:
        resource = self._manager().open_resource(resource_name)
        try:
            resource.timeout = timeout_ms
        except Exception:
            LOGGER.debug("VISA resource does not expose a timeout attribute")
        return resource
