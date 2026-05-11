import argparse
import logging
import sys

from .app import run

log = logging.getLogger(__name__)


def _get_version() -> str:
    try:
        from importlib.metadata import version

        return version("ontology-accelerator")
    except Exception:
        return "0.0.0-dev"


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
        help="Write the resolved ontology config to a YAML file (useful with --excel or --from-semantic-model)",
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
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose (DEBUG) logging",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {_get_version()}",
    )

    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    try:
        run(args)
    except (ValueError, FileNotFoundError) as exc:
        log.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
