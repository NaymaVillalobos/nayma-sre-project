import os
import tempfile

import pytest


@pytest.fixture
def client():
    file_descriptor, database_path = tempfile.mkstemp(
        suffix=".db",
    )
    os.close(file_descriptor)

    os.environ["DATABASE_PATH"] = database_path

    from app.app import create_app

    application = create_app()
    application.config["TESTING"] = True

    with application.test_client() as test_client:
        yield test_client

    os.unlink(database_path)