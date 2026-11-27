"""Postgres connections for account code. One function so tests can swap it."""

from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row


def connect() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
