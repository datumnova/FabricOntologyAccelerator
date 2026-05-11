"""Fetch a Power BI / Fabric semantic model definition and convert it into an
ontology config dict that can be merged with or used as-is.

The module talks to the Fabric REST API:
  * ``GET /v1/workspaces/{workspaceId}/semanticModels/{modelId}/definition``

It extracts tables → entities, columns → properties, and relationships →
relationship types, then returns a config dict compatible with
``validate_config`` / ``build_definition``.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

import requests

from .fabric_api import auth_headers

# ---------------------------------------------------------------------------
# Fabric API helpers
# ---------------------------------------------------------------------------

_BASE = "https://api.fabric.microsoft.com/v1"


def _fetch_semantic_model_definition(token: str, workspace_id: str, model_id: str) -> dict:
    """GET the semantic model definition from Fabric."""
    url = f"{_BASE}/workspaces/{workspace_id}/semanticModels/{model_id}/getDefinition"
    resp = requests.post(url, headers=auth_headers(token), timeout=120)
    if resp.status_code == 202:
        # Long-running operation — follow the Location header
        location = resp.headers.get("Location")
        if not location:
            raise RuntimeError("Semantic model definition returned 202 but no Location header")
        from .fabric_api import poll_operation

        result = poll_operation(location, token)
        return result.get("definition", result)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Failed to get semantic model definition: {resp.status_code} {resp.text}"
        )
    body = resp.json() if resp.text.strip() else {}
    return body.get("definition", body)


def _decode_part(part: dict) -> dict | None:
    """Decode a base64-encoded definition part payload."""
    payload = part.get("payload")
    if not payload:
        return None
    try:
        raw = base64.b64decode(payload).decode("utf-8")
        return json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# TMDL / BIM model parsing
# ---------------------------------------------------------------------------

_SM_TYPE_MAP = {
    "string": "string",
    "int64": "int",
    "int32": "int",
    "double": "double",
    "decimal": "double",
    "currency": "double",
    "boolean": "boolean",
    "dateTime": "datetime",
    "datetime": "datetime",
    "binary": "string",
    "unknown": "string",
}


def _normalise_sm_type(datatype: str | None) -> str:
    if not datatype:
        return "string"
    return _SM_TYPE_MAP.get(datatype.strip().lower(), "string")


def _parse_bim_model(model: dict) -> dict:
    """Parse a BIM (model.bim / database.json) style semantic model."""
    db_model = model.get("model", model)
    tables = db_model.get("tables", [])
    relationships_raw = db_model.get("relationships", [])

    entities: list[dict] = []
    table_columns: dict[str, list[str]] = {}

    for tbl in tables:
        tbl_name: str = tbl.get("name", "")
        if not tbl_name or tbl_name.startswith("DateTableTemplate") or tbl_name.startswith("LocalDateTable"):
            continue  # skip auto date tables

        columns = tbl.get("columns", [])
        props: list[dict] = []
        key_prop: str | None = None
        display_prop: str | None = None
        col_names: list[str] = []

        for col in columns:
            col_name = col.get("name", "")
            if not col_name:
                continue
            # Skip internal columns
            if col.get("isHidden") or col.get("type") == "rowNumber":
                continue
            col_names.append(col_name)
            prop_type = _normalise_sm_type(col.get("dataType"))
            props.append({"name": col_name, "type": prop_type})
            if col.get("isKey"):
                key_prop = col_name
            if col.get("isDefaultLabel"):
                display_prop = col_name

        if not props:
            continue

        if not key_prop:
            key_prop = props[0]["name"]
        if not display_prop:
            display_prop = key_prop

        table_columns[tbl_name] = col_names
        entities.append({
            "name": _sanitise_name(tbl_name),
            "key": key_prop,
            "display": display_prop,
            "properties": props,
            "_original_table_name": tbl_name,
        })

    relationships: list[dict] = []
    for rel in relationships_raw:
        from_table = rel.get("fromTable", "")
        to_table = rel.get("toTable", "")
        from_col = rel.get("fromColumn", "")
        to_col = rel.get("toColumn", "")
        if not from_table or not to_table:
            continue
        rel_name = rel.get("name") or f"{_sanitise_name(from_table)}To{_sanitise_name(to_table)}"
        relationships.append({
            "name": _sanitise_name(rel_name),
            "source_entity": _sanitise_name(from_table),
            "target_entity": _sanitise_name(to_table),
            "_sourceColumn": from_col,
            "_targetColumn": to_col,
        })

    return {"entities": entities, "relationships": relationships}


def _sanitise_name(name: str) -> str:
    """Make a name safe for ontology entity/relationship naming (alphanumeric + _ -)."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if cleaned and not cleaned[0].isalpha():
        cleaned = "E_" + cleaned
    return cleaned or "Unnamed"


def _parse_tmdl_parts(parts: list[dict]) -> dict:
    """Attempt to parse TMDL format parts from the semantic model definition."""
    # TMDL stores definitions across multiple files.  We look for the model.bim
    # or database.json equivalent first, then fall back to individual table files.
    for part in parts:
        path = (part.get("path") or "").lower()
        if path.endswith("model.bim") or path.endswith("database.json") or path == "definition.json":
            decoded = _decode_part(part)
            if decoded and ("model" in decoded or "tables" in decoded):
                return _parse_bim_model(decoded)

    # Fall back: try to collect individual table definitions
    entities: list[dict] = []
    for part in parts:
        decoded = _decode_part(part)
        if decoded and "columns" in decoded and "name" in decoded:
            parsed = _parse_bim_model({"model": {"tables": [decoded]}})
            entities.extend(parsed.get("entities", []))
    return {"entities": entities, "relationships": []}


# ---------------------------------------------------------------------------
# Merge / enrich logic
# ---------------------------------------------------------------------------

def _merge_configs(existing: dict, incoming: dict) -> dict:
    """Merge *incoming* config into *existing*, filling missing parts.

    Rules:
    * New entities from *incoming* that are absent in *existing* are appended.
    * For entities present in both, properties that are only in *incoming* are
      added.
    * Relationships from *incoming* that are absent are appended.
    * Existing definitions are **not** overwritten — they are enriched only.
    """
    existing_entity_names = {e["name"] for e in existing.get("entities", [])}
    existing_entities_by_name = {e["name"]: e for e in existing.get("entities", [])}

    merged_entities = list(existing.get("entities", []))

    for entity in incoming.get("entities", []):
        name = entity["name"]
        if name not in existing_entity_names:
            # Brand new entity
            merged_entities.append(entity)
            existing_entity_names.add(name)
        else:
            # Enrich existing entity with missing properties
            existing_entity = existing_entities_by_name[name]
            existing_prop_names = {p["name"] for p in existing_entity.get("properties", [])}
            for prop in entity.get("properties", []):
                if prop["name"] not in existing_prop_names:
                    existing_entity.setdefault("properties", []).append(prop)
                    existing_prop_names.add(prop["name"])

    # Merge relationships
    existing_rel_names = {r["name"] for r in existing.get("relationships", [])}
    merged_rels = list(existing.get("relationships", []))
    for rel in incoming.get("relationships", []):
        if rel["name"] not in existing_rel_names:
            merged_rels.append(rel)
            existing_rel_names.add(rel["name"])

    result = dict(existing)
    result["entities"] = merged_entities
    if merged_rels:
        result["relationships"] = merged_rels
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_semantic_model(token: str, workspace_id: str, model_id: str) -> dict:
    """Fetch a semantic model definition and return an ontology config dict."""
    definition = _fetch_semantic_model_definition(token, workspace_id, model_id)

    parts = definition.get("parts", [])
    if parts:
        cfg = _parse_tmdl_parts(parts)
    else:
        cfg = _parse_bim_model(definition)

    # Strip internal keys
    for entity in cfg.get("entities", []):
        entity.pop("_original_table_name", None)
    for rel in cfg.get("relationships", []):
        rel.pop("_sourceColumn", None)
        rel.pop("_targetColumn", None)

    return cfg


def enrich_from_semantic_model(
    existing_cfg: dict,
    token: str,
    workspace_id: str,
    model_id: str,
) -> dict:
    """Fetch a semantic model and merge its definition into *existing_cfg*.

    Returns a new merged config dict with entities and relationships that were
    missing in *existing_cfg* added from the semantic model.
    """
    sm_cfg = fetch_semantic_model(token, workspace_id, model_id)
    return _merge_configs(existing_cfg, sm_cfg)
