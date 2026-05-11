# Fabric Ontology Accelerator

Python CLI that creates Microsoft Fabric Ontology payloads from **YAML**, **Excel workbooks**, or **Fabric semantic models**, and can optionally push them to the Fabric REST API.  An **AI agent** mode can discover data across workspaces and suggest ontologies automatically.

## What it supports

- Entities with properties, key property, and display property
- Entity data bindings to **Lakehouse tables** and **Eventhouse (KQL) tables**
- Relationship types
- Relationship contextualizations (bindings)
- **Excel import** – define entities and relationships in a spreadsheet
- **Semantic model enrichment** – pull tables/columns/relationships from a Power BI semantic model and enrich an existing ontology
- **AI-powered suggestion** – an agent connects to the Fabric Core MCP Server, discovers data sources across workspaces, and proposes a business ontology
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
uv sync                   # core features
uv sync --extra suggest   # + AI agent (openai, mcp)
```

## Generate payload from YAML

```bash
uv run fabric-ontology --yaml example.ontology.yaml \
  --workspace-id <workspace-id> \
  --lakehouse-id <lakehouse-id> \
  --output fabric_ontology_payload.json
```

## Generate payload from Excel

The Excel workbook should contain an **Entities** sheet (one row per property) and an optional **Relationships** sheet. See `sample_data/example.ontology.xlsx` for the expected format.

```bash
uv run fabric-ontology --excel sample_data/example.ontology.xlsx \
  --workspace-id <workspace-id> \
  --lakehouse-id <lakehouse-id> \
  --output fabric_ontology_payload.json \
  --output-yaml resolved.ontology.yaml      # optionally export the resolved YAML
```

### Excel sheet layout

**Entities** sheet:

| entity   | property    | type   | key | display | table     | schema |
|----------|-------------|--------|-----|---------|-----------|--------|
| Customer | customer_id | string | yes |         | customers | dbo    |
| Customer | name        | string |     | yes     | customers | dbo    |

**Relationships** sheet:

| name                   | source_entity | target_entity | table  | source_column | target_column |
|------------------------|---------------|---------------|--------|---------------|---------------|
| OrderBelongsToCustomer | Order         | Customer      | orders | order_id      | customer_id   |

## Generate from a Fabric semantic model

Pull entities, properties, and relationships directly from a Power BI semantic model:

```bash
export FABRIC_TOKEN='<entra-access-token>'
uv run fabric-ontology --from-semantic-model <semantic-model-id> \
  --workspace-id <workspace-id> \
  --output fabric_ontology_payload.json
```

## Enrich an existing ontology from a semantic model

Start from a YAML or Excel definition and fill in missing entities/properties from a semantic model:

```bash
export FABRIC_TOKEN='<entra-access-token>'
uv run fabric-ontology --yaml example.ontology.yaml \
  --enrich-from-model <semantic-model-id> \
  --workspace-id <workspace-id> \
  --lakehouse-id <lakehouse-id> \
  --output fabric_ontology_payload.json
```

## Create a new ontology in Fabric

```bash
export FABRIC_TOKEN='<entra-access-token>'
uv run fabric-ontology --yaml example.ontology.yaml \
  --workspace-id <workspace-id> \
  --lakehouse-id <lakehouse-id> \
  --apply --wait
```

## Update an existing ontology definition

```bash
export FABRIC_TOKEN='<entra-access-token>'
uv run fabric-ontology --yaml example.ontology.yaml \
  --workspace-id <workspace-id> \
  --ontology-id <ontology-id> \
  --lakehouse-id <lakehouse-id> \
  --apply --wait --update-metadata
```

## Eventhouse (KQL) data bindings

Bind timeseries properties to an Eventhouse (Kusto) table. The Fabric API source type is `KustoTable` and is only valid for `TimeSeries` bindings.

```yaml
bindings:
  - dataBindingType: TimeSeries
    timestampColumnName: timestamp
    source:
      sourceType: KustoTable
      table: equipment_telemetry
      # Provide these inline or via CLI flags
      # eventhouseId: <guid>
      # clusterUri: https://mycluster.kusto.fabric.microsoft.com
      # databaseName: TelemetryDB
    propertyBindings:
      timestamp: timestamp
      temperature: temperature
```

CLI flags for Eventhouse defaults:

```bash
uv run fabric-ontology --yaml example.eventhouse.ontology.yaml \
  --workspace-id <workspace-id> \
  --lakehouse-id <lakehouse-id> \
  --eventhouse-id <eventhouse-guid> \
  --cluster-uri https://mycluster.kusto.fabric.microsoft.com \
  --database-name TelemetryDB
```

Windows PowerShell token example:

```powershell
$env:FABRIC_TOKEN = '<entra-access-token>'
```

## AI-powered ontology suggestion

The `--suggest` mode uses an AI agent that:

1. Connects to the [Fabric Core MCP Server](https://learn.microsoft.com/en-us/rest/api/fabric/articles/mcp-servers/core-remote/overview-core-mcp-server) to discover workspaces and items
2. Inspects schemas — semantic model definitions, lakehouse tables, KQL databases
3. Samples data to understand content and infer relationships
4. Proposes a complete ontology YAML with rationale

### With Azure OpenAI (recommended)

```bash
export FABRIC_TOKEN='<entra-access-token>'
export AZURE_OPENAI_ENDPOINT='https://<resource>.openai.azure.com'
export AZURE_OPENAI_DEPLOYMENT='gpt-4o'
export AZURE_OPENAI_KEY='<api-key>'          # or omit to use FABRIC_TOKEN as AD token

uv run fabric-ontology --suggest
```

### With OpenAI

```bash
export FABRIC_TOKEN='<entra-access-token>'
export OPENAI_API_KEY='sk-...'

uv run fabric-ontology --suggest
```

### Scoped to a workspace

```bash
uv run fabric-ontology --suggest \
  --workspace-id <workspace-id> \
  --output-yaml suggested.ontology.yaml
```

### With a user hint

```bash
uv run fabric-ontology --suggest \
  --suggest-hint "Focus on IoT telemetry data and equipment maintenance"
```

The agent writes the suggested ontology to `suggested.ontology.yaml` (or `--output-yaml`).  Review and edit it, then build the payload:

```bash
uv run fabric-ontology --yaml suggested.ontology.yaml \
  --workspace-id <workspace-id> \
  --lakehouse-id <lakehouse-id> \
  --output payload.json --apply --wait
```

## Notes

- The tool writes the create payload to JSON even when `--apply` is used.
- For updates, Fabric expects only the `definition` object in the request body.
- If bindings omit `workspaceId` or `itemId`, the CLI fills them from `--workspace-id` and `--lakehouse-id`.
- You can bind by lakehouse name using `source.lakehouseName` (or `source.itemName`); the CLI resolves it to `itemId` via Fabric Items API.
- Lakehouse name resolution requires a token (`--token` or `FABRIC_TOKEN`) and an effective workspace ID.
- Relationship bindings are emitted as `RelationshipTypes/<id>/Contextualizations/<guid>.json` parts.
- Eventhouse (KustoTable) bindings are only allowed with `dataBindingType: TimeSeries`.
- Use `--output-yaml` with `--excel` or `--from-semantic-model` to export the resolved config as YAML for inspection.
- The `--enrich-from-model` flag can be combined with any input source (`--yaml` or `--excel`) to add missing entities/properties from a semantic model.

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
