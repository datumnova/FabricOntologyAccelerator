from __future__ import annotations

import logging
import os
from pathlib import Path

from .definition_builder import build_definition
from .fabric_api import FabricLakehouseResolver, create_or_update
from .io_utils import load_yaml, write_output, write_yaml
from .validation import config_uses_lakehouse_names, validate_config

log = logging.getLogger(__name__)


def _resolve_token(args) -> str | None:
    return args.token or os.environ.get("FABRIC_TOKEN")


def _load_config(args, token: str | None) -> dict:
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

    raise ValueError("No input source specified. Use --yaml, --excel, or --from-semantic-model.")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run(args):
    # Standard payload-building modes require an input source
    if not any(
        getattr(args, attr, None)
        for attr in ("yaml_file", "excel_file", "semantic_model_id")
    ):
        raise ValueError(
            "No input source specified. Use --yaml, --excel, or --from-semantic-model."
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
    log.info("Wrote payload to %s", args.output)

    # Optionally write resolved config as YAML
    if getattr(args, "output_yaml", None):
        write_yaml(args.output_yaml, cfg)
        log.info("Wrote ontology YAML to %s", args.output_yaml)

    if args.apply:
        if not args.workspace_id:
            raise ValueError("--workspace-id is required with --apply")
        if not token:
            raise ValueError("--apply requires a Fabric token. Provide --token or set FABRIC_TOKEN.")
        result = create_or_update(args, payload)
        api_out = str(Path(args.output).with_suffix(".result.json"))
        write_output(api_out, result)
        log.info("Wrote API result to %s", api_out)
