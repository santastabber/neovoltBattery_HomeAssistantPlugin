"""Binary sensor platform for Byte-Watt integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ByteWattDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Byte-Watt binary sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([ByteWattOffGridModeBinarySensor(coordinator, entry)])


class ByteWattOffGridModeBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Off-grid mode as shown by the ByteWatt/Neovolt web UI.

    The official web app displays the text "off-grid" when the
    /report/energyStorage/getLastPowerData response has upsModel == 1.
    """

    _attr_name = "ByteWatt Off Grid Mode"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:transmission-tower-off"

    def __init__(self, coordinator: ByteWattDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_off_grid_mode"

    @property
    def is_on(self) -> bool | None:
        battery = (self.coordinator.data or {}).get("battery", {})
        ups_model = battery.get("upsModel")
        if ups_model is None:
            return None
        return ups_model == 1 or str(ups_model).lower() in {"1", "true", "off-grid", "off_grid"}

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        battery = (self.coordinator.data or {}).get("battery", {})
        return {
            "upsModel": battery.get("upsModel"),
            "grid_power_w": battery.get("pgrid"),
            "house_load_w": battery.get("pload"),
            "battery_power_w": battery.get("pbat"),
            "solar_power_w": battery.get("ppv"),
            "battery_soc": battery.get("soc"),
            "inverterMode": battery.get("inverterMode"),
            "forceChargeMode": battery.get("forceChargeMode"),
        }

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "ByteWatt Battery System",
            "manufacturer": "ByteWatt",
            "model": "Battery Management System",
            "sw_version": "1.0.0",
        }
