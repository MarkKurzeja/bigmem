import os
import pytest

from bigmem.db import get_connection, init_db, close_connection


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def conn(db_path):
    connection = get_connection(db_path)
    init_db(connection)
    yield connection
    close_connection(connection)
