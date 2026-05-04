import os
from pathlib import Path

from .definition_builder import build_definition
from .fabric_api import FabricLakehouseResolver, create_or_update
from .io_utils import load_yaml, write_output
from .validation import config_uses_lakehouse_names, validate_config


def run(args):
    cfg = load_yaml(args.yaml_file)
    validate_config(cfg)

    token = args.token or os.environ.get("FABRIC_TOKEN")
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
    )
    write_output(args.output, payload)
    print(f"Wrote payload to {args.output}")

    if args.apply:
        if not args.workspace_id:
            raise ValueError("--workspace-id is required with --apply")
        result = create_or_update(args, payload)
        api_out = str(Path(args.output).with_suffix(".result.json"))
        write_output(api_out, result)
        print(f"Wrote API result to {api_out}")
