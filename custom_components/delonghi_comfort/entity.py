"""Shared coordinator typing and state refresh for De'Longhi entities.

HA's CoordinatorEntity.available is a dynamic property, while platform entities
inherit Entity.available as a cached_property. Narrow Pyright overrides on the
platform classes/availability getters acknowledge this framework mismatch; keep
availability dynamic so a failed poll immediately marks retained data unavailable.
"""

from collections.abc import Callable
from functools import wraps
from types import CoroutineType
from typing import Any, Concatenate

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import DeLonghiCoordinator
from .exceptions import DeLonghiAuthError, DeLonghiConnectionError


class DeLonghiEntity(CoordinatorEntity[DeLonghiCoordinator]):
    """Refresh platform backing attributes before HA publishes state."""

    def _update_attributes(self) -> None:
        """Populate platform-specific attributes from the current snapshot."""
        raise NotImplementedError

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        super()._handle_coordinator_update()


def async_handle_command_errors[EntityT: DeLonghiEntity, **P](
    method: Callable[Concatenate[EntityT, P], CoroutineType[Any, Any, None]],
) -> Callable[Concatenate[EntityT, P], CoroutineType[Any, Any, None]]:
    """Expose command failures to HA actions and start credential recovery."""
    @wraps(method)
    async def wrapped(self: EntityT, /, *args: P.args, **kwargs: P.kwargs) -> None:
        try:
            await method(self, *args, **kwargs)
        except DeLonghiAuthError as err:
            self.coordinator.api.access_token = None
            if entry := self.coordinator.config_entry:
                entry.async_start_reauth(self.coordinator.hass)
            raise HomeAssistantError(
                "De'Longhi credentials were rejected; reauthenticate the integration"
            ) from err
        except DeLonghiConnectionError as err:
            raise HomeAssistantError("Unable to communicate with De'Longhi") from err

    return wrapped
