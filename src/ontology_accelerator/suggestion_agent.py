"""AI agent that suggests business ontologies by discovering Fabric data sources.

Connects to the official Fabric Core MCP Server for workspace / item discovery
and uses Azure OpenAI (or OpenAI) for reasoning.  Outputs a suggested ontology
YAML config and human-readable rationale.

Requires optional dependencies::

    uv pip install 'ontology-accelerator[suggest]'
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FABRIC_MCP_URL = "https://api.fabric.microsoft.com/v1/mcp/core"
MAX_ITERATIONS = 30
MAX_TOOL_RESULT_CHARS = 50_000

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert ontology architect for Microsoft Fabric.  Your task is to \
analyse data sources across one or more Fabric workspaces and design a valuable \
business ontology that models the real-world domain represented by the data.

## Workflow

1. **DISCOVER** — Call `list_workspaces` to find workspaces you can access.  \
Then call `list_items` on each workspace (filter by type when useful) to find \
lakehouses, eventhouses, semantic models, and KQL databases.

2. **INSPECT SCHEMAS**
   • Semantic models → call `get_item_definition` to extract tables, columns, \
types, and relationships.
   • Lakehouses → call `list_lakehouse_tables` to get table names.  \
Cross-reference with semantic models for column info.
   • Eventhouses / KQL databases → call `execute_kql_query`:
       `.show tables`                — list tables
       `.show table <T> schema`      — columns and types
       `<T> | take 5`               — sample rows

3. **SAMPLE DATA** — For key tables, retrieve a few sample rows so you can \
understand data content, identify keys, infer foreign-key relationships, and \
detect timeseries columns.

4. **ANALYSE** — Identify business entities, key properties, display names, \
foreign-key relationships, and timeseries data suitable for Eventhouse bindings.

5. **PROPOSE** — Output a complete ontology YAML and an explanation of your \
design decisions.

## Design principles

• Entities represent distinct business objects (Customer, Order, Sensor, …).
• Key property uniquely identifies an entity instance.
• Display property is the human-readable label (often a name or title).
• Relationships reflect real business connections with clear direction.
• Include data bindings **only** for data sources whose tables you have confirmed.
• Use `KustoTable` sourceType **only** for `TimeSeries` bindings from Eventhouses.
• Avoid duplicating the same real-world concept across multiple entities.
• Prefer meaningful relationship names that describe the business meaning \
(e.g. OrderPlacedByCustomer, SensorInstalledOnEquipment).

## Valid property types
string, int, double, boolean, datetime, object

## Supported binding source types
• `LakehouseTable` — lakehouse bindings (NonTimeSeries or TimeSeries)
• `KustoTable` — Eventhouse/KQL bindings (**TimeSeries only**)

## Output format

Your **final** response MUST contain:

1. A **Rationale** section explaining your analysis and every design choice.
2. A single fenced YAML code block (```yaml … ```) with the complete ontology \
config in this exact schema:

```yaml
ontology:
  displayName: <name>
  description: <description>
  namespace: usertypes

entities:
  - name: <EntityName>           # ^[a-zA-Z][a-zA-Z0-9_-]{0,127}$
    key: <key_property_name>
    display: <display_property_name>
    properties:
      - { name: <prop>, type: <type> }
    bindings:
      - source:
          sourceType: LakehouseTable   # or KustoTable
          table: <source_table_name>
          schema: dbo                  # optional
        propertyBindings:
          <source_column>: <property_name>
        # For KustoTable / timeseries add:
        # dataBindingType: TimeSeries
        # timestampColumnName: <col>

relationships:
  - name: <RelName>
    source_entity: <SourceEntity>
    target_entity: <TargetEntity>
    bindings:
      - source:
          sourceType: LakehouseTable
          table: <table_with_fk>
        sourceColumn: <fk_column>
        targetColumn: <pk_column>
```

Only include bindings for tables you have **confirmed** exist.  \
If you cannot determine exact column names, omit bindings and explain \
what additional information is needed.
"""

# ---------------------------------------------------------------------------
# Custom tools (supplementary — not provided by MCP server)
# ---------------------------------------------------------------------------

CUSTOM_TOOL_DEFS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_lakehouse_tables",
            "description": (
                "List all tables in a Fabric lakehouse.  Returns table names "
                "and formats.  Use after discovering a lakehouse via list_items."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "Fabric workspace GUID",
                    },
                    "lakehouse_id": {
                        "type": "string",
                        "description": "Fabric lakehouse item GUID",
                    },
                },
                "required": ["workspace_id", "lakehouse_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_kql_query",
            "description": (
                "Execute a KQL query against a Fabric Eventhouse / KQL database.  "
                "Useful queries: `.show tables` (list tables), "
                "`.show table <name> schema` (column info), "
                "`<table> | take 5` (sample rows)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cluster_uri": {
                        "type": "string",
                        "description": "Kusto cluster URI (e.g. https://xyz.kusto.fabric.microsoft.com)",
                    },
                    "database_name": {
                        "type": "string",
                        "description": "KQL database name",
                    },
                    "query": {
                        "type": "string",
                        "description": "KQL query to execute",
                    },
                },
                "required": ["cluster_uri", "database_name", "query"],
            },
        },
    },
]

_CUSTOM_TOOL_NAMES = {t["function"]["name"] for t in CUSTOM_TOOL_DEFS}

# ---------------------------------------------------------------------------
# MCP → OpenAI tool conversion
# ---------------------------------------------------------------------------


def _mcp_tool_to_openai(tool: Any) -> dict:
    """Convert an MCP ``Tool`` object to OpenAI function-calling format."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": (
                tool.inputSchema
                if tool.inputSchema
                else {"type": "object", "properties": {}}
            ),
        },
    }


# ---------------------------------------------------------------------------
# Tool execution helpers
# ---------------------------------------------------------------------------


async def _call_mcp_tool(session: Any, name: str, arguments: dict) -> str:
    """Forward a tool call to the Fabric MCP server and return text."""
    result = await session.call_tool(name, arguments=arguments)
    texts = []
    for item in result.content or []:
        if hasattr(item, "text"):
            texts.append(item.text)
    content = "\n".join(texts) if texts else "(empty response)"
    if result.isError:
        content = f"Error: {content}"
    return content


def _call_custom_tool(name: str, arguments: dict, token: str) -> str:
    """Execute a local (non-MCP) discovery tool."""
    from .fabric_discovery import execute_kql_query, list_lakehouse_tables

    try:
        if name == "list_lakehouse_tables":
            result = list_lakehouse_tables(
                token, arguments["workspace_id"], arguments["lakehouse_id"]
            )
        elif name == "execute_kql_query":
            result = execute_kql_query(
                token,
                arguments["cluster_uri"],
                arguments["database_name"],
                arguments["query"],
            )
        else:
            result = {"error": f"Unknown custom tool: {name}"}
        return json.dumps(result, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# User prompt builder
# ---------------------------------------------------------------------------


def _build_user_prompt(
    workspace_ids: list[str] | None = None, user_hint: str | None = None
) -> str:
    parts: list[str] = []

    if workspace_ids:
        ws_list = "\n".join(f"- {wid}" for wid in workspace_ids)
        parts.append(
            "Please analyse these Fabric workspaces and suggest a business "
            f"ontology:\n{ws_list}"
        )
    else:
        parts.append(
            "Please discover ALL accessible Fabric workspaces and suggest a "
            "business ontology."
        )

    parts.append(
        "\nSteps:\n"
        "1. List workspaces and discover data sources "
        "(lakehouses, eventhouses, semantic models)\n"
        "2. Inspect schemas — get table names, column types, relationships\n"
        "3. Sample data where possible to understand content\n"
        "4. Propose a comprehensive ontology with entities, properties, "
        "relationships, and data bindings"
    )

    if user_hint:
        parts.append(f"\nAdditional context from the user:\n{user_hint}")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------


def _parse_agent_output(content: str) -> dict:
    """Extract YAML config + rationale from the agent's final text."""
    yaml_match = re.search(r"```ya?ml\s*\n(.*?)```", content, re.DOTALL)
    config = None
    rationale = content

    if yaml_match:
        yaml_str = yaml_match.group(1).strip()
        try:
            config = yaml.safe_load(yaml_str)
        except yaml.YAMLError:
            pass
        rationale = (
            content[: yaml_match.start()] + content[yaml_match.end() :]
        ).strip()

    return {"config": config, "rationale": rationale, "raw": content}


# ---------------------------------------------------------------------------
# LLM client factory
# ---------------------------------------------------------------------------


def _create_llm_client(config: dict) -> Any:
    """Create an async OpenAI or Azure OpenAI client from *config*."""
    if config.get("azure_endpoint"):
        from openai import AsyncAzureOpenAI

        kwargs: dict[str, Any] = {
            "azure_endpoint": config["azure_endpoint"],
            "api_version": config.get(
                "azure_api_version", "2024-12-01-preview"
            ),
        }
        if config.get("azure_api_key"):
            kwargs["api_key"] = config["azure_api_key"]
        if config.get("azure_ad_token"):
            kwargs["azure_ad_token"] = config["azure_ad_token"]
        return AsyncAzureOpenAI(**kwargs)

    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=config.get("openai_api_key"))


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


async def _run_agent(config: dict) -> dict:
    """Async core of the suggestion agent."""
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError:
        raise ImportError(
            "The 'mcp' and 'openai' packages are required for --suggest.  "
            "Install with:  uv pip install 'ontology-accelerator[suggest]'"
        ) from None

    try:
        from openai import AsyncAzureOpenAI, AsyncOpenAI  # noqa: F401
    except ImportError:
        raise ImportError(
            "The 'openai' package is required for --suggest.  "
            "Install with:  uv pip install 'ontology-accelerator[suggest]'"
        ) from None

    token = config["token"]
    headers = {"Authorization": f"Bearer {token}"}

    print("[Agent] Connecting to Fabric Core MCP Server…")

    async with streamablehttp_client(
        url=FABRIC_MCP_URL, headers=headers
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as mcp:
            await mcp.initialize()
            print("[Agent] Connected.  Discovering available tools…")

            # Merge MCP tools + custom tools
            mcp_result = await mcp.list_tools()
            mcp_tool_names = {t.name for t in mcp_result.tools}
            openai_tools: list[dict] = [
                _mcp_tool_to_openai(t) for t in mcp_result.tools
            ]
            openai_tools.extend(CUSTOM_TOOL_DEFS)
            print(
                f"[Agent] {len(mcp_tool_names)} MCP tools + "
                f"{len(CUSTOM_TOOL_DEFS)} custom tools ready."
            )

            # LLM client
            llm = _create_llm_client(config)
            model = config["model"]

            # Seed messages
            messages: list[dict] = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _build_user_prompt(
                        config.get("workspace_ids"), config.get("user_hint")
                    ),
                },
            ]

            for iteration in range(1, MAX_ITERATIONS + 1):
                response = await llm.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=openai_tools,
                    temperature=0.2,
                )

                choice = response.choices[0]
                msg = choice.message

                # No tool calls → agent is done
                if not msg.tool_calls:
                    print(f"[Agent] Done — {iteration} iteration(s).")
                    return _parse_agent_output(msg.content or "")

                # Execute every tool call in the response
                messages.append(msg)
                for tc in msg.tool_calls:
                    fn_name = tc.function.name
                    fn_args = (
                        json.loads(tc.function.arguments)
                        if tc.function.arguments
                        else {}
                    )

                    # Progress indicator
                    short_args = ", ".join(
                        f"{k}={v!r}"
                        for k, v in list(fn_args.items())[:3]
                    )
                    print(f"[Agent] → {fn_name}({short_args})")

                    # Dispatch
                    if fn_name in mcp_tool_names:
                        content = await _call_mcp_tool(mcp, fn_name, fn_args)
                    elif fn_name in _CUSTOM_TOOL_NAMES:
                        content = _call_custom_tool(fn_name, fn_args, token)
                    else:
                        content = json.dumps(
                            {"error": f"Unknown tool: {fn_name}"}
                        )

                    # Truncate huge payloads to stay within context limits
                    if len(content) > MAX_TOOL_RESULT_CHARS:
                        content = (
                            content[:MAX_TOOL_RESULT_CHARS] + "\n… (truncated)"
                        )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": content,
                        }
                    )

            raise RuntimeError(
                "Agent reached the maximum number of iterations without "
                "producing a final response."
            )


# ---------------------------------------------------------------------------
# Public synchronous entry point
# ---------------------------------------------------------------------------


def suggest(config: dict) -> dict:
    """Run the suggestion agent.

    Parameters
    ----------
    config : dict
        Must contain ``token`` (Fabric bearer token) and LLM settings — either
        ``azure_endpoint`` + ``model`` (Azure OpenAI) or ``openai_api_key`` +
        ``model`` (OpenAI).

    Returns
    -------
    dict
        ``{"config": <parsed_yaml_dict | None>, "rationale": str, "raw": str}``
    """
    return asyncio.run(_run_agent(config))
