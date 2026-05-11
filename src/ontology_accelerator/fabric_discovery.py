"""Direct Fabric REST API calls for data discovery beyond the Core MCP server.

Provides table-level operations that the MCP server does not expose:
listing lakehouse tables and executing KQL queries for schema/sampling.
"""

from __future__ import annotations

import requests

from .fabric_api import auth_headers

_BASE = "https://api.fabric.microsoft.com/v1"


def list_lakehouse_tables(token: str, workspace_id: str, lakehouse_id: str) -> list[dict]:
    """List all tables in a Fabric lakehouse."""
    url = f"{_BASE}/workspaces/{workspace_id}/lakehouses/{lakehouse_id}/tables"
    items: list[dict] = []
    params: dict = {}

    while True:
        resp = requests.get(url, headers=auth_headers(token), params=params, timeout=60)
        if resp.status_code >= 400:
            return [{"error": f"HTTP {resp.status_code}", "detail": resp.text[:500]}]
        body = resp.json() if resp.text.strip() else {}
        items.extend(body.get("data", []))
        ct = body.get("continuationToken")
        if not ct:
            break
        params["continuationToken"] = ct

    return items


def execute_kql_query(token: str, cluster_uri: str, database_name: str, query: str) -> dict:
    """Execute a KQL query against a Fabric Eventhouse / KQL database.

    Uses the Kusto REST v2 query endpoint.  The *token* must be scoped for the
    Kusto service — this may be the same Fabric token depending on tenant
    configuration.
    """
    url = f"{cluster_uri.rstrip('/')}/v2/rest/query"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = {"db": database_name, "csl": query}
    resp = requests.post(url, headers=headers, json=body, timeout=120)
    if resp.status_code >= 400:
        return {"error": f"HTTP {resp.status_code}", "detail": resp.text[:500]}
    return resp.json()
