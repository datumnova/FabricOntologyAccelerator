import os
from pathlib import Path

from .definition_builder import build_definition
from .fabric_api import FabricLakehouseResolver, create_or_update
from .io_utils import load_yaml, write_output, write_yaml
from .validation import config_uses_lakehouse_names, validate_config


def _resolve_token(args):
    token = args.token or os.environ.get("FABRIC_TOKEN")
    return token


def _load_config(args, token):
    """Return the ontology config dict from the selected input source."""

    if getattr(args, "yaml_file", None):
        return load_yaml(args.yaml_file)

    if getattr(args, "excel_file", None):
        from .excel_importer import load_excel

        return load_excel(args.excel_file)

    if getattr(args, "semantic_model_id", None):
        if not token:
            raise ValueError(
                "--from-semantic-model requires a Fabric token. Provide --token or set FABRIC_TOKEN."
            )
        if not args.workspace_id:
            raise ValueError("--workspace-id is required with --from-semantic-model")
        from .semantic_model_importer import fetch_semantic_model

        return fetch_semantic_model(token, args.workspace_id, args.semantic_model_id)

    raise ValueError("No input source specified. Use --yaml, --excel, --from-semantic-model, or --suggest.")


# ---------------------------------------------------------------------------
# Suggest flow
# ---------------------------------------------------------------------------


def _build_suggest_config(args, token):
    """Assemble the config dict expected by ``suggestion_agent.suggest``."""
    config: dict = {"token": token}

    # Azure OpenAI (preferred)
    endpoint = (
        getattr(args, "azure_openai_endpoint", None)
        or os.environ.get("AZURE_OPENAI_ENDPOINT")
    )
    if endpoint:
        config["azure_endpoint"] = endpoint
        config["model"] = (
            getattr(args, "azure_openai_deployment", None)
            or os.environ.get("AZURE_OPENAI_DEPLOYMENT")
            or "gpt-4o"
        )
        config["azure_api_key"] = (
            getattr(args, "azure_openai_key", None)
            or os.environ.get("AZURE_OPENAI_KEY")
        )
        config["azure_api_version"] = (
            getattr(args, "azure_openai_api_version", None)
            or os.environ.get("AZURE_OPENAI_API_VERSION")
            or "2024-12-01-preview"
        )
        # Fall back to Fabric token as Azure AD token when no API key
        if not config["azure_api_key"]:
            config["azure_ad_token"] = token
    else:
        # OpenAI
        api_key = (
            getattr(args, "openai_api_key", None)
            or os.environ.get("OPENAI_API_KEY")
        )
        if not api_key:
            raise ValueError(
                "AI agent requires an LLM.  Set --azure-openai-endpoint (+ deployment) "
                "or --openai-api-key / OPENAI_API_KEY."
            )
        config["openai_api_key"] = api_key
        config["model"] = (
            getattr(args, "openai_model", None)
            or os.environ.get("OPENAI_MODEL")
            or "gpt-4o"
        )

    # Optional scope / hints
    if getattr(args, "workspace_id", None):
        config["workspace_ids"] = [args.workspace_id]
    if getattr(args, "suggest_hint", None):
        config["user_hint"] = args.suggest_hint

    return config


def run_suggest(args):
    """Run the AI suggestion agent and save results."""
    token = _resolve_token(args)
    if not token:
        raise ValueError(
            "--suggest requires a Fabric token for MCP access.  "
            "Provide --token or set FABRIC_TOKEN."
        )

    config = _build_suggest_config(args, token)

    from .suggestion_agent import suggest

    result = suggest(config)

    # Print rationale
    if result["rationale"]:
        print("\n" + result["rationale"])

    output_yaml = getattr(args, "output_yaml", None) or "suggested.ontology.yaml"

    if result["config"]:
        write_yaml(output_yaml, result["config"])
        print(f"\nWrote suggested ontology to {output_yaml}")
        print("Review and edit, then build payload with:")
        print(f"  fabric-ontology --yaml {output_yaml} --workspace-id <id> --lakehouse-id <id>")
    else:
        raw_path = str(Path(output_yaml).with_suffix(".raw.md"))
        Path(raw_path).write_text(result["raw"], encoding="utf-8")
        print(f"\nAgent did not produce valid YAML.  Raw output saved to {raw_path}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run(args):
    # Suggest mode — separate flow
    if getattr(args, "suggest", False):
        return run_suggest(args)

    # Standard payload-building modes require an input source
    if not any(
        getattr(args, attr, None)
        for attr in ("yaml_file", "excel_file", "semantic_model_id")
    ):
        raise ValueError(
            "No input source specified. Use --yaml, --excel, --from-semantic-model, or --suggest."
        )

    token = _resolve_token(args)
    cfg = _load_config(args, token)

    # Optional enrichment from a semantic model
    if getattr(args, "enrich_model_id", None):
        if not token:
            raise ValueError(
                "--enrich-from-model requires a Fabric token. Provide --token or set FABRIC_TOKEN."
            )
        if not args.workspace_id:
            raise ValueError("--workspace-id is required with --enrich-from-model")
        from .semantic_model_importer import enrich_from_semantic_model

        cfg = enrich_from_semantic_model(cfg, token, args.workspace_id, args.enrich_model_id)

    validate_config(cfg)

    lakehouse_resolver = None
    if config_uses_lakehouse_names(cfg):
        if not token:
            raise ValueError(
                "Config uses source.lakehouseName/itemName. Provide --token or set FABRIC_TOKEN to resolve IDs."
            )
        lakehouse_resolver = FabricLakehouseResolver(token)

    payload = build_definition(
        cfg,
        workspace_id=args.workspace_id,
        lakehouse_id=args.lakehouse_id,
        seed=args.seed,
        lakehouse_resolver=lakehouse_resolver,
        eventhouse_id=getattr(args, "eventhouse_id", None),
        cluster_uri=getattr(args, "cluster_uri", None),
        database_name=getattr(args, "database_name", None),
    )
    write_output(args.output, payload)
    print(f"Wrote payload to {args.output}")

    # Optionally write resolved config as YAML
    if getattr(args, "output_yaml", None):
        write_yaml(args.output_yaml, cfg)
        print(f"Wrote ontology YAML to {args.output_yaml}")

    if args.apply:
        if not args.workspace_id:
            raise ValueError("--workspace-id is required with --apply")
        result = create_or_update(args, payload)
        api_out = str(Path(args.output).with_suffix(".result.json"))
        write_output(api_out, result)
        print(f"Wrote API result to {api_out}")
