import logging

from app.core import logging as app_logging
from app.core.config import Settings
from app.core.logging import configure_logging, log_file_path, set_log_level


def _settings(data_root) -> Settings:
    return Settings(_env_file=None, data_root=data_root, tg_api_id=1, tg_api_hash="test")


def _flush() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


def test_configure_logging_writes_rotating_file(tmp_path) -> None:
    root = logging.getLogger()
    before = list(root.handlers)
    original_level = root.level
    try:
        path = configure_logging(_settings(tmp_path), "INFO")
        logging.getLogger("app.test").info("hello from test")
        _flush()
        assert path == log_file_path(_settings(tmp_path))
        assert path.parent == tmp_path / "logs"
        assert "hello from test" in path.read_text(encoding="utf-8")
    finally:
        for handler in [item for item in root.handlers if item not in before]:
            root.removeHandler(handler)
            handler.close()
        setattr(root, app_logging._FILE_HANDLER_ATTR, None)
        root.setLevel(original_level)


def test_configure_logging_rebinds_when_data_root_changes(tmp_path) -> None:
    root = logging.getLogger()
    before = list(root.handlers)
    original_level = root.level
    try:
        first = configure_logging(_settings(tmp_path / "first"), "INFO")
        second = configure_logging(_settings(tmp_path / "second"), "INFO")
        logging.getLogger("app.test").info("after rebind")
        _flush()
        assert first.exists() and second.exists()
        assert "after rebind" in second.read_text(encoding="utf-8")
    finally:
        for handler in [item for item in root.handlers if item not in before]:
            root.removeHandler(handler)
            handler.close()
        setattr(root, app_logging._FILE_HANDLER_ATTR, None)
        root.setLevel(original_level)


def test_telethon_logger_minimum_is_info() -> None:
    root = logging.getLogger()
    original_level = root.level
    try:
        set_log_level("DEBUG")
        assert root.level == logging.DEBUG
        assert logging.getLogger("telethon").level == logging.INFO
        set_log_level("ERROR")
        assert logging.getLogger("telethon").level == logging.ERROR
    finally:
        root.setLevel(original_level)
