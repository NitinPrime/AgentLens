import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_signup_and_login(client: AsyncClient):
    signup_response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "engineer@agentlens.dev",
            "password": "securepass123",
            "full_name": "Test Engineer",
        },
    )
    assert signup_response.status_code == 201
    user = signup_response.json()
    assert user["email"] == "engineer@agentlens.dev"
    assert user["full_name"] == "Test Engineer"

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "engineer@agentlens.dev", "password": "securepass123"},
    )
    assert login_response.status_code == 200
    tokens = login_response.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens

    profile_response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert profile_response.status_code == 200
    assert profile_response.json()["email"] == "engineer@agentlens.dev"


@pytest.mark.asyncio
async def test_signup_duplicate_email(client: AsyncClient):
    payload = {"email": "duplicate@agentlens.dev", "password": "securepass123"}
    first = await client.post("/api/v1/auth/signup", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/auth/signup", json=payload)
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    await client.post(
        "/api/v1/auth/signup",
        json={"email": "valid@agentlens.dev", "password": "securepass123"},
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "valid@agentlens.dev", "password": "wrong-password"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_password_reset_flow(client: AsyncClient):
    await client.post(
        "/api/v1/auth/signup",
        json={"email": "reset@agentlens.dev", "password": "oldpassword1"},
    )

    forgot_response = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "reset@agentlens.dev"},
    )
    assert forgot_response.status_code == 200
    message = forgot_response.json()["message"]
    assert "dev token:" in message
    token = message.split("dev token: ")[1].rstrip("]")

    reset_response = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "newpassword1"},
    )
    assert reset_response.status_code == 200

    login_old = await client.post(
        "/api/v1/auth/login",
        json={"email": "reset@agentlens.dev", "password": "oldpassword1"},
    )
    assert login_old.status_code == 401

    login_new = await client.post(
        "/api/v1/auth/login",
        json={"email": "reset@agentlens.dev", "password": "newpassword1"},
    )
    assert login_new.status_code == 200


@pytest.mark.asyncio
async def test_update_profile(client: AsyncClient):
    signup = await client.post(
        "/api/v1/auth/signup",
        json={"email": "profile@agentlens.dev", "password": "securepass123"},
    )
    assert signup.status_code == 201

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "profile@agentlens.dev", "password": "securepass123"},
    )
    token = login.json()["access_token"]

    update = await client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"full_name": "Updated Name"},
    )
    assert update.status_code == 200
    assert update.json()["full_name"] == "Updated Name"


@pytest.mark.asyncio
async def test_unauthenticated_profile(client: AsyncClient):
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401
