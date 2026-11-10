# Changelog

## 1.1.0

Requires Home Assistant 2026.11.0 or newer. Tested against Core 2026.11.1 on
Python 3.14.10.

- Prepare distribution through the built-in Home Assistant Marketplace, with
  current repository metadata, Climate categorization, and installation docs.
- Keep the existing integration domain, devices, and entity IDs for in-place
  upgrades from HACS installations.
- Use Core's aiohttp and Probatio libraries; remove the unused requests
  installation requirement and update the Python development/test dependencies.
- Recover from transient connection failures, refresh expired tokens, and offer
  password recovery for the existing account when credentials are rejected.
- Keep entities unavailable during failed polling and retain the last good
  snapshot until connectivity returns.
- Let HA manage startup retries, report failed commands to callers, and share
  concurrent account token renewals. Bound authentication time and identify
  failed login stages without logging credentials or response bodies.
- Test all eight login stages and actual HA platform setup, recovery and unload;
  require type checking, hassfest and Marketplace checks before publishing.
- Add a uv project and lockfile so `uv sync` creates the Python 3.14 development
  environment, including test dependencies.
- Add regression and packaging checks, official repository validation jobs,
  and release archives that exclude caches and enforce tag/version consistency.

See [UPGRADE.md](UPGRADE.md) for the dependency and Python compatibility review.
