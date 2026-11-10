# De'Longhi Comfort Home Assistant Integration

[![Marketplace](https://img.shields.io/badge/Home_Assistant-Marketplace-blue)](https://www.home-assistant.io/integrations/marketplace/)
[![GitHub release](https://img.shields.io/github/release/filmackay/delonghi-comfort-integration.svg)](https://github.com/filmackay/delonghi-comfort-integration/releases/)

This repository contains a comprehensive Home Assistant integration for De'Longhi Comfort air conditioners, heaters, and dehumidifiers. The integration provides full control and monitoring capabilities through Home Assistant's user interface.

## ⚠️ Disclaimer

**IMPORTANT**: This integration is provided "as-is" without any warranty or guarantee. The author takes no responsibility for any damage, data loss, or issues that may arise from using this integration. Use at your own risk.

**AI-Assisted Development**: Much of the work converting this to a Home Assistant integration was done using **GitHub Copilot** and other AI assistance tools. This README was also created with the help of an LLM model. While every effort has been made to ensure accuracy and functionality, please thoroughly test before deploying in production environments.

This integration is based on the excellent work of:
- **[rtfpessoa/delonghi-comfort-client](https://github.com/rtfpessoa/delonghi-comfort-client)** - Thank you for the initial client implementation
- **[duckwc/ECAMpy](https://github.com/duckwc/ECAMpy)** - Thanks for the authentication and token conversion code

## 🚀 Features

### Climate Control
- **HVAC Modes**: Cool, Heat, Dry (dehumidify), Fan Only, Off
- **Temperature Control**: Set target temperature with precise control
- **Fan Speed Control**: Multiple fan speed settings
- **Real-time Status**: Live updates of device status and settings

### Sensors
- **Room Temperature**: Current ambient temperature
- **Target Temperature**: Current temperature setpoint
- **Room Humidity**: Current humidity levels
- **Device Status**: Operating status (on/off/standby)
- **Device Mode**: Current operating mode
- **Fan Speed**: Current fan speed setting

### Controls
- **Power Switch**: Turn device on/off
- **Temperature Controls**: Precise temperature adjustment
- **Mode Selection**: Easy switching between operating modes
- **Fan Speed Selection**: Control fan speed levels

### Advanced Features
- **Configuration Flow**: Easy setup through Home Assistant UI
- **Device Discovery**: Automatic detection of De'Longhi devices
- **Coordinator Pattern**: Efficient data updates with minimal API calls
- **Cloud Polling**: Regular status updates from De'Longhi cloud services

## 📋 Requirements

- Home Assistant 2026.11.0 or newer (tested with Core 2026.11.1)
- Python 3.14.2 or newer for local development; Home Assistant OS and Container supply their own Python
- De'Longhi Comfort account with registered devices
- Internet connection for cloud API access

## 🔧 Installation

### Method 1: Home Assistant Marketplace (Recommended)

1. Open **Settings → Marketplace**.
2. Select **Add from link** and enter `https://github.com/filmackay/delonghi-comfort-integration`.
3. Select the **Integration** content type if prompted, then add the repository.
4. Open **De'Longhi Comfort**, install the release, and restart when prompted.
5. Add the integration under **Settings → Devices & services** as described below.

Existing HACS installations carry over to the Marketplace when Home Assistant is
upgraded. Update the existing installation in place to retain devices, entity IDs,
and automations. The `delonghi_comfort` domain is unchanged.

This repository is distributed as a custom repository. A public catalog listing
requires a separate submission and review. The Marketplace still reads `hacs.json`.

### Method 2: Manual Installation
1. **Download the integration**:
   ```bash
   git clone https://github.com/filmackay/delonghi-comfort-integration.git
   ```

2. **Copy to custom_components**:
   Copy the `custom_components/delonghi_comfort` folder to your Home Assistant `custom_components` directory:
   ```
   config/
   └── custom_components/
       └── delonghi_comfort/
           ├── __init__.py
           ├── api.py
           ├── climate.py
           ├── config_flow.py
           ├── const.py
           ├── coordinator.py
           ├── manifest.json
           ├── number.py
           ├── select.py
           ├── sensor.py
           ├── switch.py
           └── translations/
               └── en.json
   ```

3. **Restart Home Assistant**

## ⚙️ Configuration

### Initial Setup
1. Navigate to **Settings** → **Devices & Services** in Home Assistant
2. Click **Add Integration**
3. Search for **De'Longhi Comfort**
4. Enter your De'Longhi Comfort account credentials:
   - **Username**: Your De'Longhi account email
   - **Password**: Your De'Longhi account password
   - **Language**: Select your preferred language/region

### Configuration Options
- **Scan Interval**: How often to poll the API for updates (5–300 seconds, default 15).
  Change this in the integration options. Devices are discovered from the account.

## 🏠 Usage

### Dashboard Cards
Once configured, you'll have access to various entities:

#### Climate Entity
- `climate.delonghi_comfort_[device_id]`
- Full climate control with temperature, mode, and fan speed

#### Sensors
- `sensor.delonghi_comfort_[device_id]_room_temperature`
- `sensor.delonghi_comfort_[device_id]_room_humidity`
- `sensor.delonghi_comfort_[device_id]_target_temperature`
- `sensor.delonghi_comfort_[device_id]_device_status`

#### Controls
- `switch.delonghi_comfort_[device_id]_power`
- `number.delonghi_comfort_[device_id]_temperature`
- `select.delonghi_comfort_[device_id]_mode`
- `select.delonghi_comfort_[device_id]_fan_speed`

## 🐛 Troubleshooting

### Common Issues
1. **Authentication Errors**: Verify your De'Longhi account credentials
2. **No Devices Found**: Ensure devices are registered in the De'Longhi app
3. **Connection Timeouts**: Check internet connection and API status
4. **Slow Updates**: Adjust scan interval in configuration

### Debug Logging
Connection failures report the authentication stage in HA's logs. Requests have
a 15-second timeout and the complete login has a 60-second deadline. During
startup, HA manages temporary-failure retries. Failed device commands surface in
the UI and automation traces; rejected credentials start reauthentication.

Add to your `configuration.yaml`:
```yaml
logger:
  default: warning
  logs:
    custom_components.delonghi_comfort: debug
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

### Development Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run
these commands from the repository root:

```bash
uv sync
uv run pyright
uv run pytest
```

`uv sync` selects Python 3.14 from `.python-version`, creates `.venv`, and
installs Home Assistant and the default development/test dependencies from
`uv.lock`. uv downloads a compatible Python if it is not already available.
Select `.venv/bin/python` as your editor's interpreter. Shell activation is
optional; `uv run` selects this environment automatically.

Dependencies are declared in `pyproject.toml`, and the lockfile records their
resolved versions. After editing dependencies, run `uv lock` and `uv sync`, and
include both files in the change. CI uses `uv sync --locked` to check that they
agree. The project is configured as a development environment; Home Assistant
continues to load the integration from `custom_components/`.

`uv run pyright` checks all integration code, scripts and tests using the same
standard type-checking rules as Pylance. The shared configuration is in
`pyproject.toml`; select the project's `.venv` interpreter in VS Code. You can
also run **Python: type check project** using Tasks: Run Task. CI runs this check
alongside the regression suite. Availability overrides have narrowly scoped
exceptions for HA's dynamic CoordinatorEntity property versus its cached Entity
descriptor; all other type diagnostics remain enabled.

### Debug Home Assistant in Docker

Install and start Docker Desktop (with Compose), and install VS Code's **Python
Debugger** extension (`ms-python.debugpy`). The container runs Core 2026.11.1,
matching the local test environment. This is a Home Assistant custom integration;
it runs inside HA rather than as a separate app process.

In VS Code, set a breakpoint in the integration, select **Home Assistant: Docker
debug** in Run and Debug, and press **F5**. The pre-launch task starts the container
and waits for the debugger listener before attaching. The default browser opens
<http://127.0.0.1:8123> once HA responds. HA pauses its startup until
the debugger attaches, allowing breakpoints in integration setup code.

The equivalent terminal entry point is:

```bash
uv run scripts/ha_dev.py up
```

Then select **Home Assistant: Attach to running Docker** and press F5. The browser
opens after attaching and continuing startup. Use `up --no-browser` to suppress
this, or `uv run scripts/ha_dev.py open` to wait for and open the page manually.
The browser watcher waits up to `--timeout` seconds and records failures in
`ha-debug-config/browser.log`. On the first run,
complete HA onboarding, then add **De'Longhi Comfort** under Settings > Devices &
services using your account. This connects to the real cloud account and devices;
commands issued in this instance can operate them.

```bash
uv run scripts/ha_dev.py logs     # Follow container output; Ctrl+C stops following
uv run scripts/ha_dev.py status
uv run scripts/ha_dev.py restart  # Apply Python edits, then attach again
uv run scripts/ha_dev.py down     # Stop/remove the container; retain local state
```

The first start downloads the HA image and may install debugpy. The helper waits
up to five minutes after the container starts; increase this with `up --timeout
600` if needed. If a port is occupied, stop the other local service before retrying.
F5 recreates this debug container, so finish any active debug session first.
Disconnecting VS Code leaves the container running; use `down` when finished.

`custom_components/` is mounted read-only and mapped to local source for
breakpoints. Python edits require a restart; there is no automatic reload.
`dev/configuration.yaml` supplies the debug configuration. Persistent state,
credentials and logs stay in ignored `ha-debug-config/`. The older `ha-config/`
directory is preserved and unused by this workflow. HTTP and debugger ports are
published only on localhost. No local debugpy dependency is needed: HA installs
its own pinned debugger inside the container. See the [HA remote debugger
documentation](https://www.home-assistant.io/integrations/debugpy/).

### Regression Tests

```bash
uv run pytest
```

The tests mock API responses and never use a real account or appliance.
See [UPGRADE.md](UPGRADE.md) for the runtime and dependency review.

### Automated Workflows

This repository includes GitHub Actions for quality assurance and release management:

#### Validation workflow

Pull requests and pushes to `main` run the Python 3.14 regression suite,
Marketplace manifest and archive checks, dependency checks, hassfest, and the
HACS repository action (also used by the Marketplace).

#### Release workflow

A `v*` tag runs the tests and builds two archives: `delonghi_comfort.zip` for
manual installation and a complete package with documentation. The tag must
match the version committed in `manifest.json`; the workflow never rewrites it.
The Marketplace installs the integration directly from the release's source tree.

Build and inspect the packages locally before publishing:

```bash
uv run python scripts/build_release.py --tag v1.1.0
```

Publishing a matching Git tag triggers the GitHub release workflow. Manual
workflow dispatch can republish an existing matching tag.

## 📄 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

### License Attribution

This project incorporates code from the following Apache 2.0 licensed projects:
- **[rtfpessoa/delonghi-comfort-client](https://github.com/rtfpessoa/delonghi-comfort-client)** - Licensed under Apache 2.0
- **[duckwc/ECAMpy](https://github.com/duckwc/ECAMpy)** - Authentication and token conversion code

All modifications and additions to the original code are also licensed under Apache 2.0. See the NOTICE file for detailed attribution information.

## 🙏 Acknowledgments

- **[rtfpessoa](https://github.com/rtfpessoa)** for the original [delonghi-comfort-client](https://github.com/rtfpessoa/delonghi-comfort-client)
- **[duckwc](https://github.com/duckwc)** for the authentication code from [ECAMpy](https://github.com/duckwc/ECAMpy)
- The Home Assistant community for guidance and best practices

## 📞 Support

- Create an issue on GitHub for bug reports
- Check existing issues before creating new ones
- Provide logs and device information when reporting issues
