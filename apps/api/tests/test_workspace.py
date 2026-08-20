import pytest
from httpx import AsyncClient


async def signup_and_login(client: AsyncClient, email: str, name: str = "Engineer") -> str:
    response = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "securepass123", "full_name": name},
    )
    assert response.status_code == 201
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "securepass123"},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_signup_creates_personal_organization(client: AsyncClient):
    token = await signup_and_login(client, "org-owner@agentlens.dev", "Nitin")
    response = await client.get("/api/v1/organizations", headers=auth_header(token))
    assert response.status_code == 200
    orgs = response.json()
    assert len(orgs) == 1
    assert orgs[0]["role"] == "owner"
    assert "workspace" in orgs[0]["name"].lower() or "Nitin" in orgs[0]["name"]


@pytest.mark.asyncio
async def test_create_and_list_projects(client: AsyncClient):
    token = await signup_and_login(client, "projects@agentlens.dev")
    orgs = (await client.get("/api/v1/organizations", headers=auth_header(token))).json()
    org_id = orgs[0]["id"]

    created = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers=auth_header(token),
        json={"name": "Customer Support Agent", "description": "Production support agent"},
    )
    assert created.status_code == 201
    project = created.json()
    assert project["name"] == "Customer Support Agent"
    assert project["organization_id"] == org_id

    listed = await client.get(
        f"/api/v1/organizations/{org_id}/projects",
        headers=auth_header(token),
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1


@pytest.mark.asyncio
async def test_organization_isolation(client: AsyncClient):
    token_a = await signup_and_login(client, "alice@agentlens.dev", "Alice")
    token_b = await signup_and_login(client, "bob@agentlens.dev", "Bob")

    orgs_a = (await client.get("/api/v1/organizations", headers=auth_header(token_a))).json()
    orgs_b = (await client.get("/api/v1/organizations", headers=auth_header(token_b))).json()
    assert orgs_a[0]["id"] != orgs_b[0]["id"]

    forbidden = await client.get(
        f"/api/v1/organizations/{orgs_a[0]['id']}",
        headers=auth_header(token_b),
    )
    assert forbidden.status_code == 404

    project = await client.post(
        f"/api/v1/organizations/{orgs_a[0]['id']}/projects",
        headers=auth_header(token_a),
        json={"name": "Secret Agent"},
    )
    project_id = project.json()["id"]

    peek = await client.get(
        f"/api/v1/projects/{project_id}",
        headers=auth_header(token_b),
    )
    assert peek.status_code == 404

    steal_key = await client.post(
        f"/api/v1/projects/{project_id}/api-keys",
        headers=auth_header(token_b),
        json={"name": "stolen"},
    )
    assert steal_key.status_code == 404


@pytest.mark.asyncio
async def test_api_key_shown_once_hashed_and_revoked(client: AsyncClient):
    token = await signup_and_login(client, "keys@agentlens.dev")
    org_id = (await client.get("/api/v1/organizations", headers=auth_header(token))).json()[0]["id"]
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers=auth_header(token),
        json={"name": "Research Agent"},
    )
    project_id = project.json()["id"]

    created = await client.post(
        f"/api/v1/projects/{project_id}/api-keys",
        headers=auth_header(token),
        json={"name": "CI ingest"},
    )
    assert created.status_code == 201
    payload = created.json()
    secret = payload["secret"]
    assert secret.startswith("al_")
    assert "key_hash" not in payload

    listed = await client.get(
        f"/api/v1/projects/{project_id}/api-keys",
        headers=auth_header(token),
    )
    assert listed.status_code == 200
    listed_key = listed.json()[0]
    assert "secret" not in listed_key
    assert listed_key["key_prefix"] == payload["key_prefix"]
    assert listed_key["is_revoked"] is False

    verify = await client.get(
        "/api/v1/sdk/verify",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert verify.status_code == 200
    assert verify.json()["project_id"] == project_id
    assert verify.json()["project_name"] == "Research Agent"

    listed_after_use = await client.get(
        f"/api/v1/projects/{project_id}/api-keys",
        headers=auth_header(token),
    )
    assert listed_after_use.json()[0]["last_used_at"] is not None

    revoke = await client.post(
        f"/api/v1/projects/{project_id}/api-keys/{payload['id']}/revoke",
        headers=auth_header(token),
    )
    assert revoke.status_code == 200
    assert revoke.json()["is_revoked"] is True

    rejected = await client.get(
        "/api/v1/sdk/verify",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert rejected.status_code == 401


@pytest.mark.asyncio
async def test_member_invite(client: AsyncClient):
    owner_token = await signup_and_login(client, "owner@agentlens.dev", "Owner")
    await signup_and_login(client, "teammate@agentlens.dev", "Teammate")
    org_id = (await client.get("/api/v1/organizations", headers=auth_header(owner_token))).json()[0][
        "id"
    ]

    invite = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=auth_header(owner_token),
        json={"email": "teammate@agentlens.dev", "role": "member"},
    )
    assert invite.status_code == 201
    assert invite.json()["email"] == "teammate@agentlens.dev"
    assert invite.json()["role"] == "member"
