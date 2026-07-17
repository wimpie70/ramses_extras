"""Tests for the LogOnce helper."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.log_once import (
    _DOMAIN,
    _RESTART_SET_KEY,
    _STORE_KEY,
    LogOnce,
    LogWhen,
)


def _make_hass() -> MagicMock:
    """Create a MagicMock hass with the data dict LogOnce expects."""
    hass = MagicMock()
    hass.data = {_DOMAIN: {}}
    return hass


@contextmanager
def _patch_store(load_return=None, save_mock=None):
    """Patch HA's Store with controllable load/save (context manager).

    Usage::

        with _patch_store(load_return={...}) as mock_store_cls:
            ...
    """
    with patch("homeassistant.helpers.storage.Store") as mock_store_cls:
        mock_store_cls.return_value.async_load = AsyncMock(return_value=load_return)
        mock_store_cls.return_value.async_save = save_mock or AsyncMock()
        yield mock_store_cls


class TestLogWhen:
    """Tests for the LogWhen enum."""

    def test_str_values(self) -> None:
        assert LogWhen.RESTART == "restart"
        assert LogWhen.INSTALL == "install"
        assert LogWhen.VERSION_BUMP == "version_bump"
        assert LogWhen.INTERVAL == "interval"
        assert LogWhen.ALWAYS == "always"


class TestLogAlways:
    """LogWhen.ALWAYS — no dedup, always logs."""

    @pytest.mark.asyncio
    async def test_logs_every_time(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        hass = _make_hass()
        warner = LogOnce(hass)
        msg = "test always message"

        r1 = await warner.log(
            key="k1", msg=msg, level=logging.WARNING, when=LogWhen.ALWAYS
        )
        r2 = await warner.log(
            key="k1", msg=msg, level=logging.WARNING, when=LogWhen.ALWAYS
        )

        assert r1 is True
        assert r2 is True
        assert caplog.text.count(msg) == 2

    @pytest.mark.asyncio
    async def test_respects_level(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("DEBUG")
        hass = _make_hass()
        warner = LogOnce(hass)

        await warner.log(
            key="k1", msg="debug msg", level=logging.DEBUG, when=LogWhen.ALWAYS
        )
        assert "debug msg" in caplog.text


class TestLogRestart:
    """LogWhen.RESTART — once per HA process (in-memory)."""

    @pytest.mark.asyncio
    async def test_logs_first_time(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        hass = _make_hass()
        warner = LogOnce(hass)

        result = await warner.log(
            key="k1", msg="restart msg", level=logging.WARNING, when=LogWhen.RESTART
        )
        assert result is True
        assert "restart msg" in caplog.text

    @pytest.mark.asyncio
    async def test_suppresses_second_time(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        hass = _make_hass()
        warner = LogOnce(hass)

        await warner.log(key="k1", msg="first", when=LogWhen.RESTART)
        result = await warner.log(key="k1", msg="second", when=LogWhen.RESTART)

        assert result is False
        assert "second" not in caplog.text

    @pytest.mark.asyncio
    async def test_different_keys_log_independently(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        hass = _make_hass()
        warner = LogOnce(hass)

        r1 = await warner.log(key="k1", msg="msg1", when=LogWhen.RESTART)
        r2 = await warner.log(key="k2", msg="msg2", when=LogWhen.RESTART)

        assert r1 is True
        assert r2 is True
        assert "msg1" in caplog.text
        assert "msg2" in caplog.text

    @pytest.mark.asyncio
    async def test_uses_in_memory_set(self) -> None:
        hass = _make_hass()
        warner = LogOnce(hass)

        await warner.log(key="k1", msg="msg", when=LogWhen.RESTART)

        restart_set = hass.data[_DOMAIN][_RESTART_SET_KEY]
        assert isinstance(restart_set, set)
        assert "k1" in restart_set


class TestLogInstall:
    """LogWhen.INSTALL — once ever (persisted)."""

    @pytest.mark.asyncio
    async def test_logs_when_no_prior_state(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        hass = _make_hass()
        with _patch_store(load_return=None):
            warner = LogOnce(hass)
            result = await warner.log(key="k1", msg="install msg", when=LogWhen.INSTALL)
            assert result is True
            assert "install msg" in caplog.text

    @pytest.mark.asyncio
    async def test_suppresses_when_already_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        hass = _make_hass()
        with _patch_store(load_return={"k1": {"logged_at": time.time()}}):
            warner = LogOnce(hass)
            result = await warner.log(
                key="k1", msg="should not appear", when=LogWhen.INSTALL
            )
            assert result is False
            assert "should not appear" not in caplog.text

    @pytest.mark.asyncio
    async def test_persists_after_logging(self) -> None:
        hass = _make_hass()
        save_mock = AsyncMock()
        with _patch_store(load_return=None, save_mock=save_mock):
            warner = LogOnce(hass)
            await warner.log(key="k1", msg="msg", when=LogWhen.INSTALL)
            save_mock.assert_awaited_once()
            saved_data = save_mock.call_args.args[0]
            assert "k1" in saved_data
            assert "logged_at" in saved_data["k1"]


class TestLogVersionBump:
    """LogWhen.VERSION_BUMP — once per integration version."""

    @pytest.mark.asyncio
    async def test_logs_on_first_run(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        hass = _make_hass()
        hass.data[_DOMAIN]["_integration_version"] = "1.0.0"
        with _patch_store(load_return=None):
            warner = LogOnce(hass)
            result = await warner.log(
                key="k1", msg="version msg", when=LogWhen.VERSION_BUMP
            )
            assert result is True
            assert "version msg" in caplog.text

    @pytest.mark.asyncio
    async def test_suppresses_same_version(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        hass = _make_hass()
        hass.data[_DOMAIN]["_integration_version"] = "1.0.0"
        with _patch_store(
            load_return={"k1": {"logged_at": time.time(), "version": "1.0.0"}}
        ):
            warner = LogOnce(hass)
            result = await warner.log(
                key="k1", msg="should not appear", when=LogWhen.VERSION_BUMP
            )
            assert result is False
            assert "should not appear" not in caplog.text

    @pytest.mark.asyncio
    async def test_re_logs_on_version_change(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        hass = _make_hass()
        hass.data[_DOMAIN]["_integration_version"] = "2.0.0"
        with _patch_store(
            load_return={"k1": {"logged_at": time.time(), "version": "1.0.0"}}
        ):
            warner = LogOnce(hass)
            result = await warner.log(
                key="k1", msg="new version msg", when=LogWhen.VERSION_BUMP
            )
            assert result is True
            assert "new version msg" in caplog.text


class TestLogInterval:
    """LogWhen.INTERVAL — once per N days."""

    @pytest.mark.asyncio
    async def test_logs_when_no_prior_state(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        hass = _make_hass()
        with _patch_store(load_return=None):
            warner = LogOnce(hass)
            result = await warner.log(
                key="k1",
                msg="interval msg",
                when=LogWhen.INTERVAL,
                interval_days=7,
            )
            assert result is True
            assert "interval msg" in caplog.text

    @pytest.mark.asyncio
    async def test_suppresses_within_interval(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        hass = _make_hass()
        now = time.time()
        with _patch_store(
            load_return={"k1": {"logged_at": now, "expires_at": now + 86_400 * 7}}
        ):
            warner = LogOnce(hass)
            result = await warner.log(
                key="k1",
                msg="should not appear",
                when=LogWhen.INTERVAL,
                interval_days=7,
            )
            assert result is False
            assert "should not appear" not in caplog.text

    @pytest.mark.asyncio
    async def test_re_logs_after_expiry(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        hass = _make_hass()
        now = time.time()
        with _patch_store(
            load_return={
                "k1": {
                    "logged_at": now - 86_400 * 10,
                    "expires_at": now - 86_400 * 3,
                }
            }
        ):
            warner = LogOnce(hass)
            result = await warner.log(
                key="k1",
                msg="re-logged after expiry",
                when=LogWhen.INTERVAL,
                interval_days=7,
            )
            assert result is True
            assert "re-logged after expiry" in caplog.text

    @pytest.mark.asyncio
    async def test_defaults_to_one_day_when_not_specified(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        hass = _make_hass()
        save_mock = AsyncMock()
        with _patch_store(load_return=None, save_mock=save_mock):
            warner = LogOnce(hass)
            await warner.log(key="k1", msg="msg", when=LogWhen.INTERVAL)
            saved = save_mock.call_args.args[0]
            # expires_at should be ~now + 1 day
            assert "expires_at" in saved["k1"]
            assert saved["k1"]["expires_at"] > time.time()


class TestClear:
    """Tests for LogOnce.clear()."""

    @pytest.mark.asyncio
    async def test_clear_removes_from_persisted_store(self) -> None:
        hass = _make_hass()
        save_mock = AsyncMock()
        with _patch_store(
            load_return={"k1": {"logged_at": time.time()}}, save_mock=save_mock
        ):
            warner = LogOnce(hass)
            await warner.clear("k1")
            save_mock.assert_awaited_once()
            saved = save_mock.call_args.args[0]
            assert "k1" not in saved

    @pytest.mark.asyncio
    async def test_clear_removes_from_restart_set(self) -> None:
        hass = _make_hass()
        hass.data[_DOMAIN][_RESTART_SET_KEY] = {"k1", "k2"}
        with _patch_store(load_return={}):
            warner = LogOnce(hass)
            await warner.clear("k1")
            assert "k1" not in hass.data[_DOMAIN][_RESTART_SET_KEY]
            assert "k2" in hass.data[_DOMAIN][_RESTART_SET_KEY]

    @pytest.mark.asyncio
    async def test_clear_nonexistent_key_no_error(self) -> None:
        hass = _make_hass()
        with _patch_store(load_return=None):
            warner = LogOnce(hass)
            # Should not raise
            await warner.clear("nonexistent")

    @pytest.mark.asyncio
    async def test_clear_allows_re_log(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        hass = _make_hass()
        with _patch_store(load_return={"k1": {"logged_at": time.time()}}):
            warner = LogOnce(hass)
            # First call suppressed
            r1 = await warner.log(key="k1", msg="msg1", when=LogWhen.INSTALL)
            assert r1 is False
            # Clear
            await warner.clear("k1")
            # Now should log again
            r2 = await warner.log(key="k1", msg="msg2", when=LogWhen.INSTALL)
            assert r2 is True
            assert "msg2" in caplog.text


class TestIsLogged:
    """Tests for LogOnce.is_logged()."""

    @pytest.mark.asyncio
    async def test_true_for_restart_key(self) -> None:
        hass = _make_hass()
        hass.data[_DOMAIN][_RESTART_SET_KEY] = {"k1"}
        with _patch_store(load_return={}):
            warner = LogOnce(hass)
            assert await warner.is_logged("k1") is True

    @pytest.mark.asyncio
    async def test_true_for_persisted_key(self) -> None:
        hass = _make_hass()
        with _patch_store(load_return={"k1": {"logged_at": time.time()}}):
            warner = LogOnce(hass)
            assert await warner.is_logged("k1") is True

    @pytest.mark.asyncio
    async def test_false_for_unknown_key(self) -> None:
        hass = _make_hass()
        with _patch_store(load_return={}):
            warner = LogOnce(hass)
            assert await warner.is_logged("unknown") is False


class TestStoreErrorHandling:
    """LogOnce should never raise on store errors."""

    @pytest.mark.asyncio
    async def test_load_error_returns_empty(self) -> None:
        hass = _make_hass()
        with patch("homeassistant.helpers.storage.Store") as mock_store_cls:
            mock_store_cls.return_value.async_load = AsyncMock(
                side_effect=RuntimeError("disk")
            )
            mock_store_cls.return_value.async_save = AsyncMock()
            warner = LogOnce(hass)
            # Should not raise; should treat as empty state -> log
            result = await warner.log(key="k1", msg="msg", when=LogWhen.INSTALL)
            assert result is True

    @pytest.mark.asyncio
    async def test_save_error_does_not_raise(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        hass = _make_hass()
        with patch("homeassistant.helpers.storage.Store") as mock_store_cls:
            mock_store_cls.return_value.async_load = AsyncMock(return_value=None)
            mock_store_cls.return_value.async_save = AsyncMock(
                side_effect=RuntimeError("disk")
            )
            warner = LogOnce(hass)
            # Should log the message even if saving fails
            result = await warner.log(key="k1", msg="msg", when=LogWhen.INSTALL)
            assert result is True
            assert "msg" in caplog.text


class TestStoreKey:
    """Verify the shared store key."""

    @pytest.mark.asyncio
    async def test_uses_correct_store_key(self) -> None:
        hass = _make_hass()
        with _patch_store(load_return=None) as ctx:
            warner = LogOnce(hass)
            await warner.log(key="k1", msg="msg", when=LogWhen.INSTALL)
            assert ctx.call_args is not None
            # Store(hass, version, key) — verify the key argument
            assert ctx.call_args.args[2] == _STORE_KEY


class TestLoggerOverride:
    """Tests for logger parameter handling."""

    @pytest.mark.asyncio
    async def test_custom_logger_at_construction(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        custom_logger = logging.getLogger("custom.test.log_once")
        hass = _make_hass()
        warner = LogOnce(hass, logger=custom_logger)

        await warner.log(key="k1", msg="custom logger msg", when=LogWhen.ALWAYS)
        assert "custom logger msg" in caplog.text

    @pytest.mark.asyncio
    async def test_logger_override_per_call(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        call_logger = logging.getLogger("custom.per_call.log_once")
        hass = _make_hass()
        warner = LogOnce(hass)

        await warner.log(
            key="k1", msg="per-call msg", when=LogWhen.ALWAYS, logger=call_logger
        )
        assert "per-call msg" in caplog.text


class TestLazyFormatArgs:
    """Tests for lazy % formatting via args parameter."""

    @pytest.mark.asyncio
    async def test_args_passed_to_logger(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        hass = _make_hass()
        warner = LogOnce(hass)

        await warner.log(
            key="k1",
            msg="value is %s and %s",
            args=("hello", 42),
            when=LogWhen.ALWAYS,
        )
        assert "value is hello and 42" in caplog.text
