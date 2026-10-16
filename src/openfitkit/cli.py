"""A single local launcher; application behavior lives in the service modules."""

import argparse
from dataclasses import replace
import threading
import webbrowser

import uvicorn

from . import __version__
from .app import create_app
from .settings import Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the local OpenFitKit fitness app starter.")
    parser.add_argument("--version", action="version", version=f"OpenFitKit {__version__}")
    parser.add_argument("--no-browser", action="store_true", help="open the printed address yourself")
    parser.add_argument("--port", type=int, help="local port (default: 8766 or OPENFITKIT_PORT)")
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env()
        if args.port is not None:
            settings = replace(settings, port=args.port)
        app = create_app(settings)
    except ValueError as error:
        parser.error(str(error))
    address = f"http://127.0.0.1:{settings.port}"
    print(f"OpenFitKit: {address}")
    print(f"Provider: {settings.provider}. Keep this terminal open; Ctrl+C stops the app.")
    if not args.no_browser:
        opener = threading.Timer(0.8, lambda: webbrowser.open(address))
        opener.daemon = True
        opener.start()
    uvicorn.run(app, host="127.0.0.1", port=settings.port, access_log=False, log_level="warning")
    return 0
