import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.errors import AppError, app_error_handler
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


def test_message_change_compares_edit_instants_in_utc() -> None:
    old = {"text": "edited", "edit_date": datetime(2026, 1, 1, 0, 0), "media_type": None,
           "reply_to_message_id": None}
    new = {**old, "edit_date": datetime(2026, 1, 1, 8, 0, tzinfo=timezone(timedelta(hours=8)))}
    assert message_changed(old, new) is False


@pytest.mark.asyncio
async def test_app_error_handler_exposes_detail() -> None:
    response = await app_error_handler(None, AppError(502, "telegram_login_failed", "请求验证码失败",
                                                     "PhoneNumberInvalidError"))
    assert response.status_code == 502
    assert json.loads(response.body)["error"] == {"code": "telegram_login_failed", "message": "请求验证码失败",
                                                  "detail": "PhoneNumberInvalidError"}


@pytest.mark.asyncio
async def test_app_error_handler_omits_absent_detail() -> None:
    response = await app_error_handler(None, AppError(422, "validation_error", "请求参数无效"))
    assert json.loads(response.body)["error"] == {"code": "validation_error", "message": "请求参数无效"}
