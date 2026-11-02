"""Local HTTP server and static web UI."""

from .app import create_app, run_server

__all__ = ["create_app", "run_server"]
