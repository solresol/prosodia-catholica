"""
Connection helper for the Stephanos PostgreSQL database (read-only access).

By default this is meant to be used on raksasa as OS user `herodian`, connecting
over the local UNIX socket (peer auth). If you need TCP auth, set host/password.
"""

from __future__ import annotations

import os

import psycopg2
from psycopg2.extras import RealDictCursor


def _load_setting(config_value, env_names, default=None):
    if config_value not in (None, ""):
        return config_value
    for env_name in env_names:
        env_value = os.environ.get(env_name)
        if env_value not in (None, ""):
            return env_value
    return default


try:
    from config import STEPHANOS_DB_HOST as CONFIG_HOST
    from config import STEPHANOS_DB_PORT as CONFIG_PORT
    from config import STEPHANOS_DB_NAME as CONFIG_NAME
    from config import STEPHANOS_DB_USER as CONFIG_USER
    from config import STEPHANOS_DB_PASSWORD as CONFIG_PASSWORD
except ImportError:
    CONFIG_HOST = None
    CONFIG_PORT = None
    CONFIG_NAME = None
    CONFIG_USER = None
    CONFIG_PASSWORD = None


DB_HOST = _load_setting(CONFIG_HOST, ("STEPHANOS_DB_HOST",), default=None)
DB_PORT = int(_load_setting(CONFIG_PORT, ("STEPHANOS_DB_PORT",), default=5432))
DB_NAME = _load_setting(CONFIG_NAME, ("STEPHANOS_DB_NAME",), default="stephanos")
DB_USER = _load_setting(CONFIG_USER, ("STEPHANOS_DB_USER",), default="herodian")
DB_PASSWORD = _load_setting(CONFIG_PASSWORD, ("STEPHANOS_DB_PASSWORD",), default=None)


def get_connection(*, dict_cursor: bool = False):
    cursor_factory = RealDictCursor if dict_cursor else None
    kwargs = {
        "port": DB_PORT,
        "database": DB_NAME,
        "user": DB_USER,
        "cursor_factory": cursor_factory,
    }
    # Empty string / None => use UNIX socket defaults
    if DB_HOST:
        kwargs["host"] = DB_HOST
    if DB_PASSWORD:
        kwargs["password"] = DB_PASSWORD
    return psycopg2.connect(**kwargs)

