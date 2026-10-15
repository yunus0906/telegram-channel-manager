from pathlib import Path, PurePosixPath, PureWindowsPath


def safe_relative(value: str) -> Path:
    if not value or "\x00" in value or PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute():
        raise ValueError("无效的相对路径")
    parts = value.replace("\\", "/").split("/")
    if any(part in ("", ".", "..") or ":" in part for part in parts):
        raise ValueError("无效的相对路径")
    return Path(*parts)


def within_root(root: Path, relative: str) -> Path:
    base = root.resolve()
    target = (base / safe_relative(relative)).resolve()
    if not target.is_relative_to(base):
        raise ValueError("路径不在允许目录内")
    return target

