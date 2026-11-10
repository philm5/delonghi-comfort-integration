# Marketplace and Core compatibility review

Reviewed 10 November 2026.

## Target runtime

- Latest stable Home Assistant Core: **2026.11.1**, released 9 November 2026.
- Core requires **Python >=3.14.2**. This upgrade was tested locally on Python
  **3.14.10**. CI selects the current Python 3.14 patch release.
- Home Assistant switched its packaged runtime to Python 3.14 in **2026.3**;
  this change predates the Marketplace release.
- The integration's supported baseline is now **Core 2026.11.0**, declared in
  `hacs.json`. Development dependencies in `pyproject.toml` and Docker Compose pin **2026.11.1**.
  `uv.lock` records the full resolved dependency graph; `uv sync` creates the
  local environment with test dependencies included by default.
- Home Assistant OS and the official Container include Python. Users update
  Home Assistant rather than installing Python inside those environments.

Sources: [Core on PyPI](https://pypi.org/project/homeassistant/2026.11.1/),
[Python 3.14 announcement](https://www.home-assistant.io/blog/2026/03/04/release-20263/).

## Marketplace distribution

The Marketplace is built into Core starting with 2026.11. It takes over existing
HACS installations and uses the same `custom_components/<domain>/` structure,
`hacs.json`, catalog, and repository validation action.

This remains an integration running inside Core. Home Assistant's separately
managed Apps are a different distribution type. No Supervisor container or app
configuration is needed for this integration.

The repository metadata now uses the maintained
`filmackay/delonghi-comfort-integration` fork, a valid `hacs.json`, a minimum Core
version, an issue tracker, and the Climate category. The domain and existing
entity identifiers remain unchanged. The version is **1.1.0**.

Marketplace installs the integration from the source tree of the selected
release. The downloadable integration ZIP keeps its `delonghi_comfort/` folder
for manual extraction into `custom_components/`; `zip_release` is intentionally
not enabled. Release builds exclude caches and refuse mismatched tags rather
than silently changing the manifest.

The changes prepare a custom Marketplace repository. They do not publish a
GitHub release, submit the repository to the public catalog, or update a running
Home Assistant installation.

Sources: [Marketplace architecture](https://contributors.home-assistant.io/marketplace/how-it-works/),
[repository metadata](https://contributors.home-assistant.io/marketplace/reference/hacs-json/),
[custom integration publishing](https://contributors.home-assistant.io/marketplace/guides/integrations/),
[catalog submission](https://contributors.home-assistant.io/marketplace/guides/catalog/).

## Dependency review

| Dependency | Before | Target | Ownership |
| --- | --- | --- | --- |
| Home Assistant | 2023.1 minimum / tests 2026.2.3 | 2026.11.1 | Pinned local development and test runtime |
| aiohttp | Unpinned local requirement | 3.14.5 | Supplied and pinned by Core |
| requests | Integration requirement >=2.31.0 | Removed from integration requirements | Unused by this integration; Core itself provides 2.34.2 |
| Schema validation | `voluptuous` import | Probatio 0.13.0 | Supplied by Core; integration imports it directly |
| PyYAML | Unpinned local requirement | 6.0.3 | Supplied by Core for development |
| pytest | >=8,<10 | 9.2.0 | Pinned test dependency |
| pytest-asyncio | >=1,<2 | 1.4.1.post1 | Pinned test dependency |
| actions/checkout | v4 | v7 | Validation and release workflows |
| astral-sh/setup-uv | Previously actions/setup-python | v10.3.2 / uv 0.13.7 | Locked validation and release environments |
| softprops/action-gh-release | v2 | v3 | Release workflow |

Only packages used by the integration and absent from Core belong in its
manifest requirements. Both aiohttp and Probatio are provided by Core, so that
list is now empty. This avoids installing competing versions in the user's
Home Assistant environment. The discovery script retains its PEP 723 header for
`uv run discover.py`, with Python and Core requirements matching the project.
Run it from the repository root so it can import the integration. uv gives the
script its own dependency environment; it does not use the project's `uv.lock`.

Core changed its validation engine to Probatio in 2026.9. The old voluptuous
import remains compatible through Core's alias, but this integration now uses
the current library directly. Its schemas retain the same behavior.

Sources: [Core dependency pins](https://github.com/home-assistant/core/blob/2026.11.1/pyproject.toml),
[Probatio migration](https://contributors.home-assistant.io/blog/2026/09/30/probatio-validation-engine/),
[pytest](https://pypi.org/project/pytest/9.2.0/),
[pytest-asyncio](https://pypi.org/project/pytest-asyncio/1.4.1.post1/).

## Verification

The test suite covers credential replacement, rejected credentials, token
renewal, API outages and malformed responses, initial unavailable states,
recovery without discarding the last good snapshot, Marketplace metadata, and
release archive layout. It runs with the actual Core 2026.11.1 coordinator,
config-entry, and Marketplace manifest validation code.

CI adds the official hassfest and HACS repository actions. Those hosted action
runs require pushing the changes; local tests do not establish a passing hosted
run or catalog acceptance. Cloud authentication and physical appliance behavior
also require a live check after deployment.

The release workflow now runs dependency, type, syntax, regression, hassfest and
Marketplace checks before publishing. Regression coverage includes a synthetic
eight-stage login, concurrent token renewal, startup retry exceptions, and HA's
real platform setup, state recovery, service errors and unload for all device types.
API calls have explicit 15-second request limits; login has a 60-second overall
deadline. Sanitized connection messages identify the failed login stage. Device
commands propagate failures to HA instead of silently returning unsuccessful results.
