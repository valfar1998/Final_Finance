"""Esecuzione serverless su Modal.com (scan ogni 60s nelle finestre volatili)."""

from __future__ import annotations

try:
    import modal
except ImportError:  # pragma: no cover - opzionale in locale
    modal = None  # type: ignore

if modal is not None:
    app = modal.App("finance-alert-notify")

    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("tzdata")
        .pip_install("PyYAML>=6.0")
        .add_local_dir("finance_alert", remote_path="/root/finance_alert")
        .add_local_dir("config", remote_path="/root/config")
        .add_local_dir("scripts", remote_path="/root/scripts")
    )

    @app.function(
        image=image,
        schedule=modal.Cron("*/1 12-13 * * 1-5"),
        secrets=[modal.Secret.from_name("finance-alert")],
        timeout=300,
    )
    def scan_high_vol_morning():
        """~14:00-15:30 CET: scan ogni minuto."""
        _run_notify()

    @app.function(
        image=image,
        schedule=modal.Cron("*/1 20 * * 1-5"),
        secrets=[modal.Secret.from_name("finance-alert")],
        timeout=300,
    )
    def scan_high_vol_evening():
        """~22:00 CET: scan ogni minuto."""
        _run_notify()

    @app.function(
        image=image,
        schedule=modal.Cron("*/15 8-23 * * 1-5"),
        secrets=[modal.Secret.from_name("finance-alert")],
        timeout=300,
    )
    def scan_baseline():
        """Baseline ogni 15 min lun-ven."""
        _run_notify()


def _run_notify() -> None:
    import os
    import sys

    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ.setdefault("PYTHONPATH", root)

    from finance_alert.__main__ import main

    # Non usare SystemExit: Modal lo tratta come eccezione anche con code 0.
    code = main([])
    if code:
        raise RuntimeError(f"scan failed with exit code {code}")
