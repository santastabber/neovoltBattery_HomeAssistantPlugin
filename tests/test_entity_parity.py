"""Entity inventory and off-grid mode tests for the Byte-Watt integration."""
from __future__ import annotations

import ast
import asyncio
import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_DIR = REPO_ROOT / "custom_components" / "bytewatt"

EXPECTED_SENSOR_TYPES = {
    "SENSOR_SOC",
    "SENSOR_GRID_CONSUMPTION",
    "SENSOR_HOUSE_CONSUMPTION",
    "SENSOR_BATTERY_POWER",
    "SENSOR_PV",
    "SENSOR_LAST_UPDATE",
    "SENSOR_TOTAL_SOLAR",
    "SENSOR_TOTAL_FEED_IN",
    "SENSOR_TOTAL_BATTERY_CHARGE",
    "SENSOR_TOTAL_BATTERY_DISCHARGE",
    "SENSOR_PV_POWER_HOUSE",
    "SENSOR_PV_CHARGING_BATTERY",
    "SENSOR_TOTAL_HOUSE_CONSUMPTION",
    "SENSOR_GRID_BATTERY_CHARGE",
    "SENSOR_GRID_POWER_CONSUMPTION",
    "SENSOR_PV_GENERATED_TODAY",
    "SENSOR_CONSUMED_TODAY",
    "SENSOR_FEED_IN_TODAY",
    "SENSOR_GRID_IMPORT_TODAY",
    "SENSOR_BATTERY_CHARGED_TODAY",
    "SENSOR_BATTERY_DISCHARGED_TODAY",
    "SENSOR_SELF_CONSUMPTION",
    "SENSOR_SELF_SUFFICIENCY",
    "SENSOR_TREES_PLANTED",
    "SENSOR_CO2_REDUCTION",
}


def _load_ast(filename: str) -> ast.Module:
    return ast.parse((INTEGRATION_DIR / filename).read_text(), filename=filename)


def test_integration_loads_original_sensor_platforms_plus_off_grid_binary_sensor() -> None:
    """The fork must keep the original platforms and load the off-grid binary sensor."""
    module = _load_ast("__init__.py")
    platforms = None
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "PLATFORMS":
                    platforms = ast.literal_eval(node.value)

    assert platforms == ["sensor", "binary_sensor", "number", "time", "switch"]


def test_sensor_inventory_matches_original_hacs_integration() -> None:
    """The sensor platform must expose the original 25 sensor entities."""
    module = _load_ast("sensor.py")
    sensor_types: list[str] = []
    sensor_classes = {"ByteWattSensor", "ByteWattGridSensor", "ByteWattLastUpdateSensor"}

    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id not in sensor_classes:
            continue
        if len(node.args) >= 3 and isinstance(node.args[2], ast.Name):
            sensor_types.append(node.args[2].id)

    assert len(sensor_types) == 25
    assert set(sensor_types) == EXPECTED_SENSOR_TYPES


def _install_homeassistant_stubs(monkeypatch) -> None:
    modules = {
        "homeassistant": types.ModuleType("homeassistant"),
        "homeassistant.components": types.ModuleType("homeassistant.components"),
        "homeassistant.components.binary_sensor": types.ModuleType(
            "homeassistant.components.binary_sensor"
        ),
        "homeassistant.config_entries": types.ModuleType("homeassistant.config_entries"),
        "homeassistant.core": types.ModuleType("homeassistant.core"),
        "homeassistant.helpers": types.ModuleType("homeassistant.helpers"),
        "homeassistant.helpers.entity_platform": types.ModuleType(
            "homeassistant.helpers.entity_platform"
        ),
        "homeassistant.helpers.update_coordinator": types.ModuleType(
            "homeassistant.helpers.update_coordinator"
        ),
    }

    class BinarySensorDeviceClass:
        PROBLEM = "problem"

    class BinarySensorEntity:
        pass

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

    class ConfigEntry:
        pass

    class HomeAssistant:
        pass

    modules["homeassistant.components.binary_sensor"].BinarySensorDeviceClass = (
        BinarySensorDeviceClass
    )
    modules["homeassistant.components.binary_sensor"].BinarySensorEntity = BinarySensorEntity
    modules["homeassistant.config_entries"].ConfigEntry = ConfigEntry
    modules["homeassistant.core"].HomeAssistant = HomeAssistant
    modules["homeassistant.helpers.entity_platform"].AddEntitiesCallback = object
    modules["homeassistant.helpers.update_coordinator"].CoordinatorEntity = CoordinatorEntity

    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


def _load_binary_sensor_module(monkeypatch):
    _install_homeassistant_stubs(monkeypatch)

    custom_components = types.ModuleType("custom_components")
    custom_components.__path__ = [str(REPO_ROOT / "custom_components")]
    bytewatt_package = types.ModuleType("custom_components.bytewatt")
    bytewatt_package.__path__ = [str(INTEGRATION_DIR)]
    coordinator_module = types.ModuleType("custom_components.bytewatt.coordinator")

    class ByteWattDataUpdateCoordinator:
        pass

    coordinator_module.ByteWattDataUpdateCoordinator = ByteWattDataUpdateCoordinator
    monkeypatch.setitem(sys.modules, "custom_components", custom_components)
    monkeypatch.setitem(sys.modules, "custom_components.bytewatt", bytewatt_package)
    monkeypatch.setitem(sys.modules, "custom_components.bytewatt.coordinator", coordinator_module)

    module_name = "custom_components.bytewatt.binary_sensor"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(
        module_name,
        INTEGRATION_DIR / "binary_sensor.py",
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _make_entry(entry_id: str = "entry-1"):
    return types.SimpleNamespace(entry_id=entry_id)


def test_off_grid_mode_binary_sensor_reads_ups_model(monkeypatch) -> None:
    module = _load_binary_sensor_module(monkeypatch)
    entry = _make_entry()

    on_values = [1, "1", True, "true", "off-grid", "off_grid"]
    for ups_model in on_values:
        coordinator = types.SimpleNamespace(data={"battery": {"upsModel": ups_model}})
        sensor = module.ByteWattOffGridModeBinarySensor(coordinator, entry)
        assert sensor.is_on is True

    off_values = [0, "0", False, "false", "grid", "on-grid"]
    for ups_model in off_values:
        coordinator = types.SimpleNamespace(data={"battery": {"upsModel": ups_model}})
        sensor = module.ByteWattOffGridModeBinarySensor(coordinator, entry)
        assert sensor.is_on is False

    sensor = module.ByteWattOffGridModeBinarySensor(
        types.SimpleNamespace(data={"battery": {}}), entry
    )
    assert sensor.is_on is None


def test_off_grid_mode_binary_sensor_registers_entity_and_context_attributes(monkeypatch) -> None:
    module = _load_binary_sensor_module(monkeypatch)
    entry = _make_entry()
    coordinator = types.SimpleNamespace(
        data={
            "battery": {
                "upsModel": 1,
                "pgrid": -12,
                "pload": 340,
                "pbat": -220,
                "ppv": 560,
                "soc": 87,
                "inverterMode": "backup",
                "forceChargeMode": 0,
            }
        }
    )
    hass = types.SimpleNamespace(data={"bytewatt": {entry.entry_id: {"coordinator": coordinator}}})
    added_entities = []

    asyncio.run(module.async_setup_entry(hass, entry, added_entities.extend))

    assert len(added_entities) == 1
    sensor = added_entities[0]
    assert sensor._attr_name == "ByteWatt Off Grid Mode"
    assert sensor._attr_unique_id == "entry-1_off_grid_mode"
    assert sensor.is_on is True
    assert sensor.extra_state_attributes == {
        "upsModel": 1,
        "grid_power_w": -12,
        "house_load_w": 340,
        "battery_power_w": -220,
        "solar_power_w": 560,
        "battery_soc": 87,
        "inverterMode": "backup",
        "forceChargeMode": 0,
    }



def _install_neovolt_client_stubs(monkeypatch) -> None:
    modules = {
        "homeassistant": types.ModuleType("homeassistant"),
        "homeassistant.core": types.ModuleType("homeassistant.core"),
        "homeassistant.helpers": types.ModuleType("homeassistant.helpers"),
        "homeassistant.helpers.aiohttp_client": types.ModuleType(
            "homeassistant.helpers.aiohttp_client"
        ),
        "homeassistant.util": types.ModuleType("homeassistant.util"),
        "homeassistant.util.dt": types.ModuleType("homeassistant.util.dt"),
    }

    class HomeAssistant:
        pass

    modules["homeassistant.core"].HomeAssistant = HomeAssistant
    modules["homeassistant.helpers.aiohttp_client"].async_get_clientsession = lambda hass: None
    modules["homeassistant.util"].dt = modules["homeassistant.util.dt"]
    modules["homeassistant.util.dt"].now = lambda: __import__("datetime").datetime(
        2026, 1, 2, 3, 4, 5
    )
    modules["homeassistant.util.dt"].utcnow = lambda: __import__("datetime").datetime(
        2026, 1, 2, 3, 4, 5
    )

    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


def _load_neovolt_client_module(monkeypatch):
    _install_neovolt_client_stubs(monkeypatch)

    custom_components = types.ModuleType("custom_components")
    custom_components.__path__ = [str(REPO_ROOT / "custom_components")]
    bytewatt_package = types.ModuleType("custom_components.bytewatt")
    bytewatt_package.__path__ = [str(INTEGRATION_DIR)]
    api_package = types.ModuleType("custom_components.bytewatt.api")
    api_package.__path__ = [str(INTEGRATION_DIR / "api")]

    monkeypatch.setitem(sys.modules, "custom_components", custom_components)
    monkeypatch.setitem(sys.modules, "custom_components.bytewatt", bytewatt_package)
    monkeypatch.setitem(sys.modules, "custom_components.bytewatt.api", api_package)

    module_name = "custom_components.bytewatt.api.neovolt_client"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(
        module_name,
        INTEGRATION_DIR / "api" / "neovolt_client.py",
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _StubResponse:
    def __init__(self, payload, status: int = 200):
        self._payload = payload
        self.status = status

    async def json(self):
        return self._payload

    async def text(self):
        return str(self._payload)


class _StubSession:
    def __init__(self, payloads_by_endpoint):
        self._payloads_by_endpoint = {
            endpoint: list(payloads)
            for endpoint, payloads in payloads_by_endpoint.items()
        }
        self.calls = []

    async def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        for endpoint, payloads in self._payloads_by_endpoint.items():
            if url.endswith(endpoint) and payloads:
                return _StubResponse(payloads.pop(0))
        raise AssertionError(f"Unexpected GET call to {url}")


def test_neovolt_client_uses_menu_sys_sn_for_power_data(monkeypatch) -> None:
    """Power data must use the real ESS serial so upsModel is not masked by All."""
    module = _load_neovolt_client_module(monkeypatch)
    client = module.NeovoltClient(types.SimpleNamespace(), "user", "pass", "https://example.test")
    client.token = "token"
    client.session = _StubSession(
        {
            "getCustomMenuEssList": [
                {"code": 200, "data": [{"sysSn": "ESS-123", "stationId": "station-9"}]}
            ],
            "getLastPowerData": [{"code": 200, "data": {"upsModel": 1, "soc": 88}}],
            "getEnergyStatistics": [{"code": 200, "data": {}}],
            "getSumDataForCustomer": [{"code": 200, "data": {}}],
            "staticsByDay": [{"code": 200, "data": {}}],
        }
    )

    data = asyncio.run(client.async_get_battery_data("configured-station"))

    assert data["upsModel"] == 1
    power_call = next(
        call for call in client.session.calls if call["url"].endswith("getLastPowerData")
    )
    assert power_call["params"]["sysSn"] == "ESS-123"
    assert power_call["params"]["stationId"] == "station-9"



def test_neovolt_client_falls_back_to_all_when_menu_unavailable(monkeypatch) -> None:
    """Configured users still update if the menu lookup cannot provide a serial."""
    module = _load_neovolt_client_module(monkeypatch)
    client = module.NeovoltClient(types.SimpleNamespace(), "user", "pass", "https://example.test")
    client.token = "token"
    client.session = _StubSession(
        {
            "getCustomMenuEssList": [{"code": 500, "msg": "temporary"}],
            "getLastPowerData": [{"code": 200, "data": {"soc": 55}}],
            "getEnergyStatistics": [{"code": 200, "data": {}}],
            "getSumDataForCustomer": [{"code": 200, "data": {}}],
            "staticsByDay": [{"code": 200, "data": {}}],
        }
    )

    data = asyncio.run(client.async_get_battery_data("configured-station"))

    assert data["soc"] == 55
    power_call = next(
        call for call in client.session.calls if call["url"].endswith("getLastPowerData")
    )
    assert power_call["params"] == {"sysSn": "All", "stationId": "configured-station"}



def test_neovolt_client_uses_menu_parent_station_id_for_nested_ess(monkeypatch) -> None:
    """Nested menu responses can carry stationId on the parent station node."""
    module = _load_neovolt_client_module(monkeypatch)
    client = module.NeovoltClient(types.SimpleNamespace(), "user", "pass", "https://example.test")
    client.token = "token"
    client.session = _StubSession(
        {
            "getCustomMenuEssList": [
                {"code": 200, "data": [{"stationId": "station-9", "children": [{"sysSn": "ESS-123"}]}]}
            ],
            "getLastPowerData": [{"code": 200, "data": {"upsModel": 1, "soc": 88}}],
            "getEnergyStatistics": [{"code": 200, "data": {}}],
            "getSumDataForCustomer": [{"code": 200, "data": {}}],
            "staticsByDay": [{"code": 200, "data": {}}],
        }
    )

    data = asyncio.run(client.async_get_battery_data("configured-station"))

    assert data["upsModel"] == 1
    power_call = next(
        call for call in client.session.calls if call["url"].endswith("getLastPowerData")
    )
    assert power_call["params"]["sysSn"] == "ESS-123"
    assert power_call["params"]["stationId"] == "station-9"



def test_neovolt_client_reuses_cached_menu_sys_sn(monkeypatch) -> None:
    """The ESS menu lookup is cached per configured station after the first success."""
    module = _load_neovolt_client_module(monkeypatch)
    client = module.NeovoltClient(types.SimpleNamespace(), "user", "pass", "https://example.test")
    client.token = "token"
    client.session = _StubSession(
        {
            "getCustomMenuEssList": [
                {"code": 200, "data": [{"sysSn": "ESS-123", "stationId": "station-9"}]}
            ],
            "getLastPowerData": [
                {"code": 200, "data": {"upsModel": 1, "soc": 88}},
                {"code": 200, "data": {"upsModel": 1, "soc": 89}},
            ],
            "getEnergyStatistics": [{"code": 200, "data": {}}, {"code": 200, "data": {}}],
            "getSumDataForCustomer": [{"code": 200, "data": {}}, {"code": 200, "data": {}}],
            "staticsByDay": [{"code": 200, "data": {}}, {"code": 200, "data": {}}],
        }
    )

    first = asyncio.run(client.async_get_battery_data("configured-station"))
    second = asyncio.run(client.async_get_battery_data("configured-station"))

    assert first["soc"] == 88
    assert second["soc"] == 89
    menu_calls = [
        call for call in client.session.calls if call["url"].endswith("getCustomMenuEssList")
    ]
    assert len(menu_calls) == 1
    power_calls = [
        call for call in client.session.calls if call["url"].endswith("getLastPowerData")
    ]
    assert [call["params"] for call in power_calls] == [
        {"sysSn": "ESS-123", "stationId": "station-9"},
        {"sysSn": "ESS-123", "stationId": "station-9"},
    ]
