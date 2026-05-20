from __future__ import annotations

import json
import logging
import os
import time

import requests

log = logging.getLogger(__name__)


def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


class FabricLakehouseResolver:
    def __init__(self, token):
        self.token = token
        self.base_url = "https://api.fabric.microsoft.com/v1"
        self.cache = {}

    def _list_workspace_lakehouses(self, workspace_id):
        if workspace_id in self.cache:
            return self.cache[workspace_id]

        url = f"{self.base_url}/workspaces/{workspace_id}/items"
        params = {"type": "Lakehouse"}
        items = []

        while True:
            resp = requests.get(url, headers=auth_headers(self.token), params=params, timeout=60)
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Failed to list lakehouses for workspace '{workspace_id}': {resp.status_code} {resp.text}"
                )

            try:
                body = resp.json() if resp.text.strip() else {}
            except ValueError:
                raise RuntimeError(
                    f"Invalid JSON response while listing lakehouses: {resp.text[:200]}"
                )
            page_items = body.get("value") or []
            if not isinstance(page_items, list):
                raise RuntimeError("Unexpected response while listing lakehouses; expected a list in 'value'")
            items.extend(page_items)

            continuation_token = body.get("continuationToken")
            if not continuation_token:
                break
            params["continuationToken"] = continuation_token

        self.cache[workspace_id] = items
        return items

    def resolve_id(self, workspace_id, lakehouse_name):
        normalized = lakehouse_name.strip().lower()
        matches = []
        for item in self._list_workspace_lakehouses(workspace_id):
            candidate_names = [
                str(item.get("displayName") or "").strip(),
                str(item.get("name") or "").strip(),
            ]
            if any(name and name.lower() == normalized for name in candidate_names):
                matches.append(item)

        if not matches:
            raise ValueError(
                f"No lakehouse named '{lakehouse_name}' was found in workspace '{workspace_id}'."
            )
        if len(matches) > 1:
            ids = ", ".join(str(item.get("id")) for item in matches)
            raise ValueError(
                f"Multiple lakehouses named '{lakehouse_name}' were found in workspace '{workspace_id}' (IDs: {ids})."
            )

        lakehouse_id = matches[0].get("id")
        if not lakehouse_id:
            raise RuntimeError(
                f"Lakehouse '{lakehouse_name}' in workspace '{workspace_id}' did not contain an 'id' field."
            )
        return lakehouse_id


def poll_operation(url, token, timeout=600):
    start = time.time()
    while True:
        resp = requests.get(url, headers=auth_headers(token), timeout=60)
        if resp.status_code >= 400:
            raise RuntimeError(f"Operation polling failed: {resp.status_code} {resp.text}")

        try:
            data = resp.json() if resp.text.strip() else {}
        except ValueError:
            raise RuntimeError(
                f"Invalid JSON in operation poll response: {resp.text[:200]}"
            )
        status = (data.get("status") or data.get("state") or "").lower()
        if status in {"succeeded", "success", "completed"}:
            return data
        if status in {"failed", "error", "cancelled"}:
            raise RuntimeError(f"Operation failed: {json.dumps(data, indent=2)}")

        if time.time() - start > timeout:
            raise TimeoutError("Timed out while waiting for Fabric long-running operation")

        try:
            retry_after = int(resp.headers.get("Retry-After", 5))
        except ValueError:
            retry_after = 5
        time.sleep(retry_after)


def create_or_update(args, payload):
    token = args.token or os.environ.get("FABRIC_TOKEN")
    if not token:
        raise ValueError("Provide --token or set FABRIC_TOKEN")

    base = "https://api.fabric.microsoft.com/v1"
    workspace_id = args.workspace_id
    if args.ontology_id:
        url = f"{base}/workspaces/{workspace_id}/ontologies/{args.ontology_id}/updateDefinition"
        body = {"definition": payload["definition"]}
        if args.update_metadata:
            url += "?updateMetadata=true"
        resp = requests.post(url, headers=auth_headers(token), json=body, timeout=120)
    else:
        url = f"{base}/workspaces/{workspace_id}/ontologies"
        resp = requests.post(url, headers=auth_headers(token), json=payload, timeout=120)

    if resp.status_code not in (200, 201, 202):
        raise RuntimeError(f"Fabric API error {resp.status_code}: {resp.text}")

    try:
        response_body = resp.json() if resp.text.strip() else {}
    except ValueError:
        response_body = {}
    result = {
        "status_code": resp.status_code,
        "headers": dict(resp.headers),
        "body": response_body,
    }
    location = resp.headers.get("Location")
    if args.wait and location:
        result["operation"] = poll_operation(location, token)
    return result