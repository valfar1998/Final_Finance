from __future__ import annotations

import argparse
import json
import sys

from finance_alert.aggregator import source_status
from finance_alert.config import load_config
from finance_alert.engine import mark_sent, run_scan
from finance_alert.env import load_env
from finance_alert.format import format_alerts, format_test_ping
from finance_alert.telegram import load_credentials, send_message


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def cmd_status() -> int:
    cfg = load_config()
    creds = load_credentials()
    status = source_status()
    _print(
        {
            "watchlist": cfg.symbols,
            "telegram": bool(creds),
            "sources": status,
            "rules": {
                "mode": "early_upside" if cfg.rules.only_upside else "all",
                "enabled_tipos": cfg.rules.enabled_tipos,
                "extended_hours_pct": cfg.rules.extended_hours_pct,
                "peer_lag_leader_pct": cfg.rules.peer_lag_leader_pct,
                "surprise_eps_pct": cfg.rules.surprise_eps_pct,
            },
        }
    )
    return 0


def cmd_test() -> int:
    cfg = load_config()
    text = format_test_ping(source_status(), len(cfg.symbols))
    print(text)
    if not send_message(text):
        print("invio test fallito (mancano credenziali o bot non raggiungibile)", file=sys.stderr)
        return 1
    print("test inviato")
    return 0


def cmd_scan(*, dry_run: bool) -> int:
    result = run_scan()
    print(json.dumps(result.summary(), ensure_ascii=False))
    if not result.fresh:
        print("nessun alert nuovo" if result.alerts else "nessun alert")
        return 0
    text = format_alerts(result.fresh, result.now, macro_stress=result.macro_stress)
    print(text)
    if dry_run:
        return 0
    if not send_message(text):
        print("invio Telegram fallito", file=sys.stderr)
        return 1
    mark_sent(result.fresh)
    print(f"alert inviato ({len(result.fresh)} nuovi)")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    load_env()
    parser = argparse.ArgumentParser(description="Alert Telegram borsa")
    parser.add_argument("--dry-run", action="store_true", help="calcola senza inviare")
    parser.add_argument("--test", action="store_true", help="ping di prova sul bot")
    parser.add_argument("--status", action="store_true", help="mostra fonti e watchlist")
    args = parser.parse_args(argv)
    if args.status:
        return cmd_status()
    if args.test:
        return cmd_test()
    return cmd_scan(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
