"""Unit tests for Telegram client resilience helpers."""

from __future__ import annotations

from finance_alert.telegram import _is_transient, diagnose_telegram


def test_is_transient_timeout():
    assert _is_transient("The read operation timed out")
    assert _is_transient("<urlopen error timed out>")
    assert _is_transient("HTTP Error 429: Too Many Requests") is False


def test_diagnose_reuses_getme_detail_without_network(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    out = diagnose_telegram(getme_detail="False (The read operation timed out)")
    assert "token_len=7" in out
    assert "getMe=False (The read operation timed out)" in out
