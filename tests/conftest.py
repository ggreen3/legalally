import os
import tempfile
from pathlib import Path

DB_PATH = Path(tempfile.gettempdir()) / f"legalally-test-{os.getpid()}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-that-is-long-enough"
os.environ["ENVIRONMENT"] = "test"
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app
from app.security import rate_limiter


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    rate_limiter.reset()
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)


def register(test_client: TestClient, email: str, tenant_name: str) -> dict:
    full_name = email.split("@")[0].replace(".", " ").title()
    if len(full_name) < 2:
        full_name = "Demo User"
    response = test_client.post(
        "/api/auth/register",
        json={
            "tenant_name": tenant_name,
            "email": email,
            "full_name": full_name,
            "password": "StrongPass123!",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
