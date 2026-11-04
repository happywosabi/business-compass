import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app

pytestmark = pytest.mark.anyio


async def test_health(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_docs_available_outside_production(client):
    assert (await client.get("/api/docs")).status_code == 200


async def test_docs_hidden_in_production(test_settings):
    app = create_app(settings=test_settings.model_copy(update={"app_env": "production"}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        assert (await c.get("/api/docs")).status_code == 404
        assert (await c.get("/api/openapi.json")).status_code == 404
    await app.state.engine.dispose()
