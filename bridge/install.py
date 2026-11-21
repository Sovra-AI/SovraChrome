"""Register the local native host and print importable Harness settings."""
import argparse
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile

from local import HOST, ROOT, extension_id


def write_atomic(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, mode="w") as output:
        output.write(data)
    os.chmod(output.name, mode)
    os.replace(output.name, path)


def install(browser, config_root=None):
    if config_root:
        product = config_root
    elif sys.platform == "darwin":
        name = {"chrome": "Google/Chrome", "chromium": "Chromium"}[browser]
        product = Path.home() / "Library/Application Support" / name
    elif sys.platform.startswith("linux"):
        name = {"chrome": "google-chrome", "chromium": "chromium"}[browser]
        product = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / name
    else:
        raise SystemExit("The native host currently supports Linux and macOS.")

    directory = product / "NativeMessagingHosts"
    launcher = directory / (HOST + "-host")
    write_atomic(launcher, "#!/bin/sh\nexec " + shlex.join([sys.executable, str(ROOT / "bridge/native.py")]) + ' "$@"\n', 0o700)
    manifest = {"name": HOST, "description": "Sovra Chrome bridge", "path": str(launcher),
                "type": "stdio", "allowed_origins": [f"chrome-extension://{extension_id()}/"]}
    write_atomic(directory / (HOST + ".json"), json.dumps(manifest, indent=2) + "\n", 0o600)
    print(json.dumps({"mcpServers": {"Sovra Chrome": {
        "command": sys.executable, "args": [str(ROOT / "bridge/server.py")]
    }}}, indent=2))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--browser", choices=["chrome", "chromium"], default="chrome")
    cli.add_argument("--browser-config-dir", type=Path, help="Override the browser's product configuration directory")
    args = cli.parse_args()
    install(args.browser, args.browser_config_dir.resolve() if args.browser_config_dir else None)
