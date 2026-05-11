import argparse

from .app import run


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Translate ontology YAML/Excel into Microsoft Fabric ontology REST payloads"
    )

    # --- Input sources (mutually exclusive) ---
    input_group = parser.add_mutually_exclusive_group(required=False)
    input_group.add_argument("--yaml", dest="yaml_file", help="Path to ontology YAML file")
    input_group.add_argument("--excel", dest="excel_file", help="Path to ontology Excel workbook")
    input_group.add_argument(
        "--from-semantic-model", dest="semantic_model_id",
        help="Fabric semantic model ID to generate ontology from",
    )
    input_group.add_argument(
        "--suggest", action="store_true",
        help="Use an AI agent to discover Fabric data and suggest an ontology",
    )

    # --- Enrichment (can be combined with --yaml or --excel) ---
    parser.add_argument(
        "--enrich-from-model", dest="enrich_model_id",
        help="Semantic model ID to enrich the input ontology with missing entities/properties",
    )

    # --- Fabric IDs ---
    parser.add_argument("--workspace-id", help="Fabric workspace ID")
    parser.add_argument("--lakehouse-id", help="Default Fabric lakehouse item ID used by bindings")
    parser.add_argument("--ontology-id", help="Existing ontology ID to update instead of create")

    # --- Eventhouse / KQL DB ---
    parser.add_argument("--eventhouse-id", help="Fabric Eventhouse item ID for KustoTable bindings")
    parser.add_argument("--cluster-uri", help="Kusto cluster URI for Eventhouse bindings")
    parser.add_argument("--database-name", help="Kusto database name for Eventhouse bindings")

    # --- Auth & misc ---
    parser.add_argument("--token", help="Fabric bearer token. You can also set FABRIC_TOKEN")
    parser.add_argument("--seed", type=int, default=42, help="Seed for deterministic numeric IDs")
    parser.add_argument(
        "--output",
        default="fabric_ontology_payload.json",
        help="Where to write the generated create payload",
    )
    parser.add_argument(
        "--output-yaml",
        help="Write the resolved ontology config to a YAML file (useful with --excel, --from-semantic-model, or --suggest)",
    )
    parser.add_argument("--apply", action="store_true", help="Call the Fabric REST API")
    parser.add_argument(
        "--wait", action="store_true", help="Wait for long-running Fabric operation completion"
    )
    parser.add_argument(
        "--update-metadata",
        action="store_true",
        help="Pass updateMetadata=true when updating definition",
    )

    # --- AI agent options (for --suggest) ---
    agent_group = parser.add_argument_group("AI agent options (used with --suggest)")
    agent_group.add_argument(
        "--azure-openai-endpoint",
        help="Azure OpenAI endpoint URL (or set AZURE_OPENAI_ENDPOINT)",
    )
    agent_group.add_argument(
        "--azure-openai-deployment",
        help="Azure OpenAI deployment/model name (or set AZURE_OPENAI_DEPLOYMENT)",
    )
    agent_group.add_argument(
        "--azure-openai-key",
        help="Azure OpenAI API key (or set AZURE_OPENAI_KEY). If omitted, uses Fabric token as AD token.",
    )
    agent_group.add_argument(
        "--azure-openai-api-version",
        default=None,
        help="Azure OpenAI API version (default: 2024-12-01-preview)",
    )
    agent_group.add_argument(
        "--openai-api-key",
        help="OpenAI API key (or set OPENAI_API_KEY). Used when Azure endpoint is not set.",
    )
    agent_group.add_argument(
        "--openai-model",
        default=None,
        help="OpenAI model name (default: gpt-4o)",
    )
    agent_group.add_argument(
        "--suggest-hint",
        help="Additional context or focus areas for the AI agent",
    )

    return parser.parse_args(argv)


def main(argv=None):
    run(parse_args(argv))


if __name__ == "__main__":
    main()
