import logging
import logging.handlers
from pathlib import Path

from app.core.config import Settings


LOG_DIR_NAME = "logs"
LOG_FILE_NAME = "backend.log"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3
_FILE_HANDLER_ATTR = "_tcm_log_file_handler"


def log_file_path(settings: Settings) -> Path:
    return settings.data_root / LOG_DIR_NAME / LOG_FILE_NAME


def set_log_level(level: str) -> None:
    """设置根日志级别。

    Telethon 在 DEBUG 级别会输出包含消息正文的 updates，因此把它的级别下限固定为
    INFO，避免私密内容落进日志文件。
    """
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.getLogger().setLevel(numeric)
    logging.getLogger("telethon").setLevel(max(numeric, logging.INFO))


def configure_logging(settings: Settings, level: str = "INFO") -> Path:
    """安装控制台与轮转文件两个 handler，返回日志文件路径；可重复调用。"""
    path = log_file_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    formatter = logging.Formatter(LOG_FORMAT)
    if not any(isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
               for handler in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)
    handler = getattr(root, _FILE_HANDLER_ATTR, None)
    if handler is not None and Path(handler.baseFilename) != path.resolve():
        root.removeHandler(handler)
        handler.close()
        handler = None
    if handler is None:
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=LOG_MAX_BYTES,
                                                       backupCount=LOG_BACKUP_COUNT, encoding="utf-8")
        handler.setFormatter(formatter)
        setattr(root, _FILE_HANDLER_ATTR, handler)
        root.addHandler(handler)
    set_log_level(level)
    return path
