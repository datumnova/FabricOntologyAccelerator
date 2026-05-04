import argparse

from .app import run


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Translate ontology YAML to Microsoft Fabric ontology REST payloads"
    )
    parser.add_argument("yaml_file", help="Path to ontology YAML")
    parser.add_argument("--workspace-id", help="Fabric workspace ID")
    parser.add_argument("--lakehouse-id", help="Default Fabric lakehouse item ID used by bindings")
    parser.add_argument("--ontology-id", help="Existing ontology ID to update instead of create")
    parser.add_argument("--token", help="Fabric bearer token. You can also set FABRIC_TOKEN")
    parser.add_argument("--seed", type=int, default=42, help="Seed for deterministic numeric IDs")
    parser.add_argument(
        "--output",
        default="fabric_ontology_payload.json",
        help="Where to write the generated create payload",
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
    return parser.parse_args(argv)


def main(argv=None):
    run(parse_args(argv))


if __name__ == "__main__":
    main()
