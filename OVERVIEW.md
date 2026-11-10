# OVERVIEW

## Purpose
Home Assistant custom integration (Marketplace-compatible) that connects De'Longhi Comfort air conditioners, heaters, and dehumidifiers to Home Assistant via the De'Longhi cloud API.

## Stack
- **Python 3.14 / asyncio** under the Home Assistant custom component framework (Core 2026.11.1 / Python >=3.14.2)
- **aiohttp** for all async HTTP — HA's `async_get_clientsession` used at runtime
- **Gigya OIDC + Ayla Networks** — two-vendor cloud auth chain; 8 sequential HTTP steps to obtain a usable `access_token`. Niche, undocumented externally.
- **Home Assistant Marketplace** distribution (`hacs.json` remains the repository manifest) — no PyPI package, no build system
- Local Python environment: `uv sync` creates `.venv` from `pyproject.toml` and `uv.lock`; `uv run pytest` runs the suite.
- Dev appliance environment: `uv run scripts/ha_dev.py up` starts Docker Compose (`docker-compose.yml`) running `ghcr.io/home-assistant/home-assistant:2026.11.1` with `custom_components/` bind-mounted read-only. VS Code's `Home Assistant: Docker debug` target starts and attaches automatically. State is isolated in ignored `ha-debug-config/`; `dev/configuration.yaml` enables debugpy with startup waiting and localhost-published ports 8123/5678.

## Architecture
Standard HA custom component layout under `custom_components/delonghi_comfort/`:

| File | Role |
|---|---|
| `__init__.py` | Entry setup — authenticates, discovers devices, sorts into three coordinator buckets by `oem_model`, sets up platforms |
| `api.py` | All HTTP — full Gigya/Ayla auth flow + Ayla `ads-eu` datapoint read/write |
| `coordinator.py` | `DataUpdateCoordinator` subclass; polls `get_device_properties` on configurable interval |
| `climate.py` | A/C (`DeLonghiClimate`) and heater (`DeLonghiHeater`) entities |
| `humidifier.py` | Dehumidifier entity (`DehumidifierEntity`); also defines `DEVICE_MODE_TO_DEHUMIDIFIER` map imported by `select.py` |
| `binary_sensor.py` | Dehumidifier alarm bitmask entities (tank full, filter warning) |
| `sensor.py`, `switch.py`, `select.py`, `number.py` | Supporting platforms for all three device types |
| `oem_model/DL-dehumidifier.md` | Reverse-engineered API reference for dehumidifier devices |

**Device routing**: `__init__.py` sorts coordinators into `airconditioner_coordinators`, `heater_coordinators`, `dehumidifier_coordinators` by `oem_model` string. Each platform file has separate entity blocks per device type.

## Scale & Complexity
~15 Python files, ~2,450 lines. Technically dense in two areas:
1. **Auth flow** (`api.py`) — 8-step Gigya/Ayla OIDC chain with hardcoded browser fingerprints; fragile against API changes
2. **HA platform contracts** — each platform has strict interface requirements; wrong property types or missing attributes cause silent failures, not exceptions
3. **Dehumidifier property naming** diverges significantly from A/C — different property names, `÷10` temperature scaling, bitmask alarm state. Documented in `oem_model/DL-dehumidifier.md`.

Regression tests run against Core 2026.11.1 on Python 3.14. `uv run pyright` checks integration code, scripts and tests in standard mode with shared Pylance configuration in `pyproject.toml`. CI also runs this type check, hassfest and Marketplace repository validation. Platform entities refresh HA backing attributes through `entity.py`; climate temperatures use Core's native temperature API.

## Key Files
1. `custom_components/delonghi_comfort/api.py` — auth flow and all device I/O
2. `custom_components/delonghi_comfort/__init__.py` — device discovery and coordinator routing
3. `custom_components/delonghi_comfort/humidifier.py` — dehumidifier primary entity and mode map
4. `oem_model/DL-dehumidifier.md` — dehumidifier API reference (property names, enums, bitmasks)
5. `custom_components/delonghi_comfort/coordinator.py` — data shape fed to all entities

## Routing Notes
- Requires solid knowledge of the **HA integration development pattern** (`ConfigEntry`, `DataUpdateCoordinator`, `CoordinatorEntity`, platform setup, translation file conventions). Models without HA-specific training produce plausible-looking but broken code.
- The Gigya + Ayla auth chain is niche — changes require reading existing code, not web lookup.
- The dehumidifier device type has a fully documented API in `oem_model/DL-dehumidifier.md`; read it before touching dehumidifier entities.
- Run `uv run pytest` after changes. API responses are mocked; live appliance behavior remains a separate check.
