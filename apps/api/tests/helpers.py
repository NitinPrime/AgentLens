"""Shared fixtures-as-functions for API tests."""

from __future__ import annotations

from dataclasses import dataclass

from httpx import AsyncClient

PASSWORD = "securepass123"


@dataclass
class Workspace:
    token: str
    org_id: str
    project_id: str
    secret: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    @property
    def key(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.secret}"}


async def signup_and_login(client: AsyncClient, email: str, name: str = "Engineer") -> str:
    signup = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": PASSWORD, "full_name": name},
    )
    assert signup.status_code == 201, signup.text
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_workspace(
    client: AsyncClient,
    email: str,
    *,
    name: str = "Engineer",
    project_name: str = "Support Agent",
) -> Workspace:
    """Sign up a user and return their org, a project, and a live API key."""

    token = await signup_and_login(client, email, name)
    headers = auth_header(token)
    orgs = await client.get("/api/v1/organizations", headers=headers)
    assert orgs.status_code == 200, orgs.text
    org_id = orgs.json()[0]["id"]

    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        headers=headers,
        json={"name": project_name},
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]

    key = await client.post(
        f"/api/v1/projects/{project_id}/api-keys",
        headers=headers,
        json={"name": "ingest"},
    )
    assert key.status_code == 201, key.text

    return Workspace(
        token=token,
        org_id=org_id,
        project_id=project_id,
        secret=key.json()["secret"],
    )
