import base64
import json
import random
import uuid

_used_ids = set()

TYPE_MAP = {
    "string": "String",
    "str": "String",
    "int": "BigInt",
    "integer": "BigInt",
    "long": "BigInt",
    "bigint": "BigInt",
    "float": "Double",
    "double": "Double",
    "number": "Double",
    "decimal": "Double",
    "bool": "Boolean",
    "boolean": "Boolean",
    "datetime": "DateTime",
    "timestamp": "DateTime",
    "date": "DateTime",
    "time": "DateTime",
    "object": "Object",
    "json": "Object",
}


def to_b64(obj):
    return base64.b64encode(json.dumps(obj, separators=(",", ":")).encode("utf-8")).decode("utf-8")


def generate_id():
    while True:
        val = str(random.randint(10**12, 10**15))
        if val not in _used_ids:
            _used_ids.add(val)
            return val


def normalize_type(value):
    if value is None:
        return "String"
    key = str(value).strip().lower()
    return TYPE_MAP.get(key, str(value))


def cfg_entity_key(cfg, entity_name):
    for entity in cfg.get("entities", []):
        if entity["name"] == entity_name:
            return entity["key"]
    raise KeyError(entity_name)


def _resolve_source_workspace_id(source, default_workspace_id):
    return source.get("workspaceId") or default_workspace_id


def _resolve_source_lakehouse_id(source, workspace_id, default_lakehouse_id, lakehouse_resolver):
    direct_id = source.get("itemId") or source.get("lakehouseId")
    if direct_id:
        return direct_id

    lakehouse_name = source.get("lakehouseName") or source.get("itemName")
    if lakehouse_name:
        if not workspace_id:
            raise ValueError(
                f"Binding source for lakehouse '{lakehouse_name}' is missing workspaceId and --workspace-id was not provided."
            )
        if lakehouse_resolver is None:
            raise ValueError(
                "Lakehouse name resolution requires a Fabric token. Provide --token or set FABRIC_TOKEN."
            )
        return lakehouse_resolver.resolve_id(workspace_id, lakehouse_name)

    return default_lakehouse_id


def _build_source_table_properties(source, default_workspace_id, default_lakehouse_id, lakehouse_resolver,
                                    eventhouse_id=None, cluster_uri=None, database_name=None):
    source_type = source.get("sourceType", "LakehouseTable")

    if source_type == "KustoTable":
        return _build_eventhouse_source(source, default_workspace_id,
                                        eventhouse_id, cluster_uri, database_name)

    workspace_id = _resolve_source_workspace_id(source, default_workspace_id)
    lakehouse_id = _resolve_source_lakehouse_id(
        source=source,
        workspace_id=workspace_id,
        default_lakehouse_id=default_lakehouse_id,
        lakehouse_resolver=lakehouse_resolver,
    )

    source_table_name = source.get("table") or source.get("sourceTableName")
    if not source_table_name:
        raise ValueError("Binding source requires 'table' or 'sourceTableName'.")

    source_table = {
        "sourceType": "LakehouseTable",
        "workspaceId": workspace_id,
        "itemId": lakehouse_id,
        "sourceTableName": source_table_name,
    }
    if source.get("schema"):
        source_table["sourceSchema"] = source["schema"]
    return source_table


def _build_eventhouse_source(source, default_workspace_id, default_eventhouse_id=None,
                             default_cluster_uri=None, default_database_name=None):
    workspace_id = source.get("workspaceId") or default_workspace_id
    item_id = source.get("itemId") or source.get("eventhouseId") or default_eventhouse_id
    cluster_uri = source.get("clusterUri") or default_cluster_uri
    database_name = source.get("databaseName") or default_database_name
    source_table_name = source.get("table") or source.get("sourceTableName")

    if not item_id:
        raise ValueError("Eventhouse binding requires 'itemId' or 'eventhouseId' (or --eventhouse-id).")
    if not cluster_uri:
        raise ValueError("Eventhouse binding requires 'clusterUri' (or --cluster-uri).")
    if not database_name:
        raise ValueError("Eventhouse binding requires 'databaseName' (or --database-name).")
    if not source_table_name:
        raise ValueError("Eventhouse binding requires 'table' or 'sourceTableName'.")

    return {
        "sourceType": "KustoTable",
        "workspaceId": workspace_id,
        "itemId": item_id,
        "clusterUri": cluster_uri,
        "databaseName": database_name,
        "sourceTableName": source_table_name,
    }


def build_definition(cfg, workspace_id=None, lakehouse_id=None, seed=42, lakehouse_resolver=None,
                     eventhouse_id=None, cluster_uri=None, database_name=None):
    random.seed(seed)
    _used_ids.clear()

    ontology_name = cfg.get("ontology", {}).get("displayName") or cfg.get("displayName") or "OntologyFromYaml"
    ontology_description = cfg.get("ontology", {}).get("description") or cfg.get("description") or "Created from YAML"
    namespace = cfg.get("ontology", {}).get("namespace") or "usertypes"
    platform = cfg.get("platform")

    parts = [{"path": "definition.json", "payload": to_b64({}), "payloadType": "InlineBase64"}]

    entity_type_ids = {}
    property_ids = {}

    for entity in cfg.get("entities", []):
        entity_name = entity["name"]
        entity_id = generate_id()
        entity_type_ids[entity_name] = entity_id

        props = []
        for prop in entity.get("properties", []):
            prop_id = generate_id()
            property_ids[(entity_name, prop["name"])] = prop_id
            props.append(
                {
                    "id": prop_id,
                    "name": prop["name"],
                    "redefines": prop.get("redefines"),
                    "baseTypeNamespaceType": prop.get("baseTypeNamespaceType"),
                    "valueType": normalize_type(prop.get("type")),
                }
            )

        entity_def = {
            "id": entity_id,
            "namespace": entity.get("namespace", namespace),
            "baseEntityTypeId": entity.get("baseEntityTypeId"),
            "name": entity_name,
            "entityIdParts": [property_ids[(entity_name, entity["key"])]],
            "displayNamePropertyId": property_ids[(entity_name, entity.get("display", entity["key"]))],
            "namespaceType": entity.get("namespaceType", "Custom"),
            "visibility": entity.get("visibility", "Visible"),
            "properties": props,
            "timeseriesProperties": entity.get("timeseriesProperties", []),
        }
        parts.append(
            {
                "path": f"EntityTypes/{entity_id}/definition.json",
                "payload": to_b64(entity_def),
                "payloadType": "InlineBase64",
            }
        )

        for binding in entity.get("bindings", []):
            binding_id = binding.get("id") or str(uuid.uuid4())
            property_bindings = []
            for col, prop_name in (binding.get("propertyBindings") or {}).items():
                property_bindings.append(
                    {
                        "sourceColumnName": col,
                        "targetPropertyId": property_ids[(entity_name, prop_name)],
                    }
                )

            source = binding.get("source", {})
            binding_cfg = {
                "dataBindingType": binding.get("dataBindingType", "NonTimeSeries"),
                "propertyBindings": property_bindings,
                "sourceTableProperties": _build_source_table_properties(
                    source=source,
                    default_workspace_id=workspace_id,
                    default_lakehouse_id=lakehouse_id,
                    lakehouse_resolver=lakehouse_resolver,
                    eventhouse_id=eventhouse_id,
                    cluster_uri=cluster_uri,
                    database_name=database_name,
                ),
            }
            if binding.get("timestampColumnName"):
                binding_cfg["timestampColumnName"] = binding["timestampColumnName"]
            data_binding = {
                "id": binding_id,
                "dataBindingConfiguration": binding_cfg,
            }
            parts.append(
                {
                    "path": f"EntityTypes/{entity_id}/DataBindings/{binding_id}.json",
                    "payload": to_b64(data_binding),
                    "payloadType": "InlineBase64",
                }
            )

    for rel in cfg.get("relationships", []):
        rel_id = rel.get("id") or generate_id()
        src_entity = rel["source_entity"]
        tgt_entity = rel["target_entity"]

        rel_def = {
            "namespace": rel.get("namespace", namespace),
            "id": rel_id,
            "name": rel["name"],
            "namespaceType": rel.get("namespaceType", "Custom"),
            "source": {"entityTypeId": entity_type_ids[src_entity]},
            "target": {"entityTypeId": entity_type_ids[tgt_entity]},
        }
        parts.append(
            {
                "path": f"RelationshipTypes/{rel_id}/definition.json",
                "payload": to_b64(rel_def),
                "payloadType": "InlineBase64",
            }
        )

        for ctx in rel.get("bindings", []):
            ctx_id = ctx.get("id") or str(uuid.uuid4())
            source_key_property = ctx.get("sourceKeyProperty") or cfg_entity_key(cfg, src_entity)
            target_key_property = ctx.get("targetKeyProperty") or cfg_entity_key(cfg, tgt_entity)
            source_column = ctx.get("sourceColumn")
            target_column = ctx.get("targetColumn")
            if not source_column or not target_column:
                raise ValueError(
                    f"Relationship binding for '{rel['name']}' requires sourceColumn and targetColumn"
                )

            source = ctx.get("source", {})
            contextualization = {
                "id": ctx_id,
                "dataBindingTable": _build_source_table_properties(
                    source=source,
                    default_workspace_id=workspace_id,
                    default_lakehouse_id=lakehouse_id,
                    lakehouse_resolver=lakehouse_resolver,
                    eventhouse_id=eventhouse_id,
                    cluster_uri=cluster_uri,
                    database_name=database_name,
                ),
                "sourceKeyRefBindings": [
                    {
                        "sourceColumnName": source_column,
                        "targetPropertyId": property_ids[(src_entity, source_key_property)],
                    }
                ],
                "targetKeyRefBindings": [
                    {
                        "sourceColumnName": target_column,
                        "targetPropertyId": property_ids[(tgt_entity, target_key_property)],
                    }
                ],
            }
            parts.append(
                {
                    "path": f"RelationshipTypes/{rel_id}/Contextualizations/{ctx_id}.json",
                    "payload": to_b64(contextualization),
                    "payloadType": "InlineBase64",
                }
            )

    if platform is not None:
        parts.append({"path": ".platform", "payload": to_b64(platform), "payloadType": "InlineBase64"})

    return {
        "displayName": ontology_name,
        "description": ontology_description,
        "definition": {"parts": parts},
    }