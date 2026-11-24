import os
import tempfile

import pytest


@pytest.fixture
def client():
    database = tempfile.NamedTemporaryFile(
        suffix=".db",
        delete=False,
    )

    database.close()

    os.environ["DATABASE_PATH"] = database.name

    from app.app import create_app

    application = create_app()
    application.config["TESTING"] = True

    with application.test_client() as test_client:
        yield test_client

    os.unlink(database.name)
