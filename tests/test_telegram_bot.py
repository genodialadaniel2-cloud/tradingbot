from unittest.mock import MagicMock, patch

import pytest

import notify.telegram_bot as telegram_bot


def test_send_message_raises_clear_error_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        telegram_bot.send_message("hello")


def test_send_message_posts_to_telegram_api_with_configured_credentials(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    with patch("notify.telegram_bot.requests.post", return_value=mock_response) as mock_post:
        telegram_bot.send_message("hello world")

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert "fake-token" in args[0]
    assert kwargs["data"]["chat_id"] == "12345"
    assert kwargs["data"]["text"] == "hello world"
    mock_response.raise_for_status.assert_called_once()


def test_send_message_propagates_http_errors(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = Exception("429 rate limited")
    with patch("notify.telegram_bot.requests.post", return_value=mock_response):
        with pytest.raises(Exception, match="429"):
            telegram_bot.send_message("hello world")
