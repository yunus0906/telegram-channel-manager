from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect

from app.core.config import BACKEND_ROOT, Settings
from app.db.session import Database


def test_sqlite_is_default_and_keeps_database_url_override(tmp_path: Path) -> None:
    default = Settings(_env_file=None, data_root=tmp_path)
    assert default.db_type == "sqlite"
    assert default.async_database_url.render_as_string(hide_password=False) == (
        f"sqlite+aiosqlite:///{(tmp_path / 'manager.sqlite3').as_posix()}"
    )
    override = f"sqlite+aiosqlite:///{(tmp_path / 'other.sqlite3').as_posix()}"
    assert Settings(_env_file=None, database_url=override).async_database_url.render_as_string(hide_password=False) == override


def test_mysql_url_escapes_credentials_and_selects_mysql_engine() -> None:
    settings = Settings(
        _env_file=None, db_type="mysql", mysql_host="db.internal", mysql_port=3307,
        mysql_user="user@name", mysql_password="p@ss:/word", mysql_database="manager",
    )
    assert settings.async_database_url.render_as_string(hide_password=False) == (
        "mysql+aiomysql://user%40name:p%40ss%3A%2Fword@db.internal:3307/manager?charset=utf8mb4"
    )
    db = Database(settings)
    assert db.engine.dialect.name == "mysql"


@pytest.mark.parametrize("missing", ["mysql_user", "mysql_password", "mysql_database"])
def test_mysql_requires_connection_details(missing: str) -> None:
    values = {"db_type": "mysql", "mysql_user": "manager", "mysql_password": "secret", "mysql_database": "manager"}
    values[missing] = ""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_mysql_rejects_database_url_override() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(_env_file=None, db_type="mysql", mysql_user="manager", mysql_password="secret",
                 mysql_database="manager", database_url="sqlite+aiosqlite:///old.db")


def test_alembic_uses_selected_settings_instead_of_ini_url(tmp_path: Path) -> None:
    database = tmp_path / "manager.sqlite3"
    settings = Settings(_env_file=None, data_root=tmp_path)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", "invalid://")
    config.attributes["settings"] = settings
    command.upgrade(config, "head")
    with create_engine(f"sqlite:///{database.as_posix()}").connect() as connection:
        assert "messages" in inspect(connection).get_table_names()
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "0001_initial"
