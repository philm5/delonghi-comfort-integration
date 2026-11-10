"""Shared coordinator typing and state refresh for De'Longhi entities.

HA's CoordinatorEntity.available is a dynamic property, while platform entities
inherit Entity.available as a cached_property. Narrow Pyright overrides on the
platform classes/availability getters acknowledge this framework mismatch; keep
availability dynamic so a failed poll immediately marks retained data unavailable.
"""

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import DeLonghiCoordinator


class DeLonghiEntity(CoordinatorEntity[DeLonghiCoordinator]):
    """Refresh platform backing attributes before HA publishes state."""

    def _update_attributes(self) -> None:
        """Populate platform-specific attributes from the current snapshot."""
        raise NotImplementedError

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        super()._handle_coordinator_update()
