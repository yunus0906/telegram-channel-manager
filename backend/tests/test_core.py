from pathlib import Path

import pytest

from app.core.paths import safe_relative, within_root
from app.services.message_store import message_changed


def test_safe_relative_rejects_traversal() -> None:
    with pytest.raises(ValueError):
        safe_relative("../secret")
    with pytest.raises(ValueError):
        safe_relative("C:\\Windows")


def test_within_root_rejects_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        within_root(tmp_path, "../outside.txt")


def test_message_change_ignores_identical_business_content() -> None:
    old = {"text": "hello", "edit_date": None, "media_type": "photo", "reply_to_message_id": None, "views": 1}
    new = {**old, "views": 2}
    assert message_changed(old, new) is False
    assert message_changed(old, {**new, "text": "edited"}) is True
