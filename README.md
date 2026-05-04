# Fabric ontology YAML tool

Small Python CLI that converts a YAML ontology description into the multipart JSON definition expected by the Microsoft Fabric Ontology REST API, and can optionally create or update the ontology.

## What it supports

- Entities with properties, key property, and display property
- Entity data bindings to lakehouse tables
- Relationship types
- Relationship contextualizations (bindings)
- Optional direct call to the Fabric REST API

## YAML shape

```yaml
ontology:
  displayName: SalesOntology
  description: Simple sales ontology
  namespace: usertypes

entities:
  - name: Customer
    key: customer_id
    display: name
    properties:
      - { name: customer_id, type: string }
      - { name: name, type: string }
    bindings:
      - source:
          sourceType: LakehouseTable
          table: customers
        propertyBindings:
          customer_id: customer_id
          name: name

relationships:
  - name: OrderBelongsToCustomer
    source_entity: Order
    target_entity: Customer
    bindings:
      - source:
          sourceType: LakehouseTable
          table: orders
        sourceColumn: order_id
        targetColumn: customer_id
```

## Install

```bash
uv sync
```

## Generate payload only

```bash
uv run fabric-ontology-from-yaml example.ontology.yaml \
  --workspace-id <workspace-id> \
  --lakehouse-id <lakehouse-id> \
  --output fabric_ontology_payload.json
```

## Create a new ontology in Fabric

```bash
export FABRIC_TOKEN='<entra-access-token>'
uv run fabric-ontology-from-yaml example.ontology.yaml \
  --workspace-id <workspace-id> \
  --lakehouse-id <lakehouse-id> \
  --apply --wait
```

## Update an existing ontology definition

```bash
export FABRIC_TOKEN='<entra-access-token>'
uv run fabric-ontology-from-yaml example.ontology.yaml \
  --workspace-id <workspace-id> \
  --ontology-id <ontology-id> \
  --lakehouse-id <lakehouse-id> \
  --apply --wait --update-metadata
```

Windows PowerShell token example:

```powershell
$env:FABRIC_TOKEN = '<entra-access-token>'
```

## Notes

- The tool writes the create payload to JSON even when `--apply` is used.
- For updates, Fabric expects only the `definition` object in the request body.
- If bindings omit `workspaceId` or `itemId`, the CLI fills them from `--workspace-id` and `--lakehouse-id`.
- You can bind by lakehouse name using `source.lakehouseName` (or `source.itemName`); the CLI resolves it to `itemId` via Fabric Items API.
- Lakehouse name resolution requires a token (`--token` or `FABRIC_TOKEN`) and an effective workspace ID.
- Relationship bindings are emitted as `RelationshipTypes/<id>/Contextualizations/<guid>.json` parts.

## Bind to a lakehouse by name

```yaml
bindings:
  - source:
      sourceType: LakehouseTable
      workspaceId: <workspace-id>   # optional if --workspace-id is provided
      lakehouseName: SalesLakehouse # resolved to itemId automatically
      table: orders
      schema: dbo
```
