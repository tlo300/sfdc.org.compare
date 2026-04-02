"""Org registry — load, save, and manage named Salesforce CLI orgs."""
import yaml
from pathlib import Path


def load_orgs(path: str) -> dict:
    """Return {orgs, selection} from orgs.yaml. Returns empty defaults if file missing."""
    p = Path(path)
    if not p.exists():
        return {"orgs": [], "selection": {"source": "", "target": ""}}
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {
        "orgs": data.get("orgs") or [],
        "selection": data.get("selection") or {"source": "", "target": ""},
    }


def save_orgs(path: str, data: dict) -> None:
    """Write data to orgs.yaml."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def bootstrap_orgs(orgs_path: str, config_path: str) -> None:
    """Create orgs.yaml from config.yaml source_org/target_org if orgs.yaml is absent."""
    if Path(orgs_path).exists():
        return
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    source = config.get("source_org", "")
    target = config.get("target_org", "")
    seen: set = set()
    orgs = []
    for alias in [source, target]:
        if alias and alias not in seen:
            orgs.append({"alias": alias, "name": alias})
            seen.add(alias)
    save_orgs(orgs_path, {
        "orgs": orgs,
        "selection": {"source": source, "target": target},
    })


def add_org(path: str, alias: str, name: str) -> None:
    """Append org to registry. Raises ValueError if alias already exists."""
    data = load_orgs(path)
    if any(o["alias"] == alias for o in data["orgs"]):
        raise ValueError(f"Org '{alias}' already exists")
    data["orgs"].append({"alias": alias, "name": name})
    save_orgs(path, data)


def remove_org(path: str, alias: str) -> None:
    """Remove org by alias. Clears selection slots that referenced this alias."""
    data = load_orgs(path)
    data["orgs"] = [o for o in data["orgs"] if o["alias"] != alias]
    sel = data.setdefault("selection", {"source": "", "target": ""})
    if sel.get("source") == alias:
        sel["source"] = ""
    if sel.get("target") == alias:
        sel["target"] = ""
    save_orgs(path, data)


def set_selection(path: str, source: str, target: str) -> None:
    """Update active source/target. Empty strings are allowed (clears the slot).
    Raises ValueError if a non-empty alias is not in the registry.
    """
    data = load_orgs(path)
    aliases = {o["alias"] for o in data["orgs"]}
    if source and source not in aliases:
        raise ValueError(f"Org '{source}' not in registry")
    if target and target not in aliases:
        raise ValueError(f"Org '{target}' not in registry")
    data["selection"] = {"source": source, "target": target}
    save_orgs(path, data)
