"""Run the local Home Assistant Docker debugger: uv run scripts/ha_dev.py up."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
HA_URL = "http://127.0.0.1:8123"
COMPOSE = [
    "docker", "compose", "--project-name", "delonghi-debug",
    "--file", str(ROOT / "docker-compose.yml"),
]


def compose(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    """Run only this repository's development Compose project."""
    return subprocess.run(
        [*COMPOSE, *args], cwd=ROOT, check=True, text=True,
        capture_output=capture,
    )


def wait_for_debugger(timeout: float) -> None:
    """Wait for HA's debugger log, without connecting to its debug socket."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        logs = compose("logs", "--no-color", "--tail", "100", "homeassistant", capture=True)
        if "Waiting for remote debug connection" in logs.stdout:
            print("Debugger ready at 127.0.0.1:5678. Attach VS Code to continue startup.")
            return
        if not compose("ps", "--status", "running", "--quiet", "homeassistant", capture=True).stdout.strip():
            raise RuntimeError("Home Assistant exited. Run: uv run scripts/ha_dev.py logs")
        time.sleep(1)
    raise RuntimeError(
        "Timed out waiting for debugpy (the first boot may download dependencies). "
        "Run: uv run scripts/ha_dev.py logs; retry 'up' once ready."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("up", "restart", "down", "logs", "status", "open"))
    parser.add_argument("--timeout", type=float, default=300, help="Debugger startup timeout in seconds")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the HA page on startup")
    args = parser.parse_args()
    if args.action == "open":
        # A separate process lets the VS Code pre-launch task finish, allowing
        # the debugger to attach and HA's HTTP server to start.
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            try:
                with urlopen(HA_URL, timeout=2):
                    if not webbrowser.open(HA_URL):
                        print(f"Open Home Assistant manually: {HA_URL}", file=sys.stderr)
                    return 0
            except (URLError, TimeoutError, OSError):
                time.sleep(1)
        print(f"HA did not become ready in time. Open {HA_URL} after continuing startup.", file=sys.stderr)
        return 1
    if not shutil.which("docker"):
        parser.exit(1, "Docker is missing. Install and start Docker Desktop first.\n")
    try:
        subprocess.run(["docker", "info"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        parser.exit(1, "Docker is not available. Start Docker Desktop and retry.\n")
    try:
        if args.action in ("up", "restart"):
            (ROOT / "ha-debug-config").mkdir(exist_ok=True)
            # Recreate so F5 always starts a fresh process waiting for attach,
            # with fresh logs rather than a previous boot's readiness message.
            compose("up", "--detach", "--force-recreate", "homeassistant")
            wait_for_debugger(args.timeout)
            if not args.no_browser:
                with (ROOT / "ha-debug-config" / "browser.log").open("w") as log:
                    subprocess.Popen(
                        [sys.executable, str(Path(__file__).resolve()), "open",
                         "--timeout", str(args.timeout)],
                        cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                        start_new_session=True,
                    )
                print(f"Will open {HA_URL} when HA responds after debugger attachment.")
        elif args.action == "down":
            compose("down")
        elif args.action == "logs":
            compose("logs", "--follow", "--tail", "100", "homeassistant")
        else:
            compose("ps")
    except (subprocess.CalledProcessError, RuntimeError) as err:
        print(f"HA development command failed: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
