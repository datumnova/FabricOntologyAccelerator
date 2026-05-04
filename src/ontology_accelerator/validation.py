def validate_config(cfg):
    entities = cfg.get("entities") or []
    if not entities:
        raise ValueError("Config must include a non-empty 'entities' list")

    names = set()
    for entity in entities:
        name = entity.get("name")
        if not name:
            raise ValueError("Every entity must have a name")
        if name in names:
            raise ValueError(f"Duplicate entity name: {name}")
        names.add(name)

        props = entity.get("properties") or []
        if not props:
            raise ValueError(f"Entity '{name}' must include properties")
        prop_names = {p.get("name") for p in props}

        key = entity.get("key")
        if not key:
            raise ValueError(f"Entity '{name}' must include a key property name")
        if key not in prop_names:
            raise ValueError(f"Entity '{name}' key '{key}' was not found in properties")

        display = entity.get("display") or key
        if display not in prop_names:
            raise ValueError(f"Entity '{name}' display '{display}' was not found in properties")

    for rel in cfg.get("relationships") or []:
        if rel.get("source_entity") not in names:
            raise ValueError(f"Relationship '{rel.get('name')}' has unknown source_entity")
        if rel.get("target_entity") not in names:
            raise ValueError(f"Relationship '{rel.get('name')}' has unknown target_entity")


def config_uses_lakehouse_names(cfg):
    for entity in cfg.get("entities", []):
        for binding in entity.get("bindings", []):
            source = binding.get("source", {})
            if source.get("lakehouseName") or source.get("itemName"):
                return True

    for rel in cfg.get("relationships", []):
        for binding in rel.get("bindings", []):
            source = binding.get("source", {})
            if source.get("lakehouseName") or source.get("itemName"):
                return True

    return False