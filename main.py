"""OrgCompare entry point — orchestrates retrieve, compare, report, serve, and deploy commands."""
import argparse
import sys
import yaml


def load_config() -> dict:
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def resolve_selection(args: argparse.Namespace, config: dict) -> tuple:
    """Return (metadata_types, data_objects) based on CLI flags.

    Priority: --metadata/--objects > --profile > full config (default).
    """
    if args.metadata or args.objects:
        metadata_types = (
            [m.strip() for m in args.metadata.split(",")]
            if args.metadata
            else config["metadata_types"]
        )
        obj_names = (
            {o.strip() for o in args.objects.split(",")}
            if args.objects
            else {o["name"] for o in config["data_objects"]}
        )
        from orgcompare.profiles import validate_profile
        validate_profile(
            {"metadata_types": metadata_types, "data_objects": list(obj_names)},
            config,
        )
        data_objects = [o for o in config["data_objects"] if o["name"] in obj_names]
        return metadata_types, data_objects

    if args.profile:
        from orgcompare.profiles import load_profiles, validate_profile

        profiles = load_profiles("profiles.yaml")
        if args.profile not in profiles:
            print(f"Profile '{args.profile}' not found in profiles.yaml")
            sys.exit(1)
        profile = profiles[args.profile]
        validate_profile(profile, config)
        obj_names = set(profile["data_objects"])
        data_objects = [o for o in config["data_objects"] if o["name"] in obj_names]
        return profile["metadata_types"], data_objects

    return config["metadata_types"], config["data_objects"]


def cmd_retrieve(config: dict, metadata_types: list, data_objects: list) -> None:
    from orgcompare.retrieve import retrieve_metadata, retrieve_data

    source = config["source_org"]
    target = config["target_org"]
    print(f"Retrieving metadata from {source}...")
    retrieve_metadata(source, metadata_types, f"output/retrieved/{source}")
    print(f"Retrieving metadata from {target}...")
    retrieve_metadata(target, metadata_types, f"output/retrieved/{target}")
    print(f"Retrieving data from {source}...")
    retrieve_data(source, data_objects, f"output/retrieved/{source}")
    print(f"Retrieving data from {target}...")
    retrieve_data(target, data_objects, f"output/retrieved/{target}")
    print("Done.")


def cmd_compare(config: dict, metadata_types: list, data_objects: list) -> None:
    from orgcompare.compare import compare_metadata, compare_data, save_results

    source = config["source_org"]
    target = config["target_org"]
    print("Comparing metadata...")
    meta_diffs = compare_metadata(
        f"output/retrieved/{source}",
        f"output/retrieved/{target}",
        metadata_types=metadata_types,
    )
    print("Comparing data...")
    data_diffs = compare_data(
        f"output/retrieved/{source}",
        f"output/retrieved/{target}",
        data_objects,
    )
    all_diffs = meta_diffs + data_diffs
    save_results(all_diffs, "output/reports/diff.json")
    total = len(all_diffs)
    different = sum(1 for r in all_diffs if r.status != "identical")
    print(f"Done. {different} differences out of {total} items. Results: output/reports/diff.json")


def cmd_report(config: dict, _metadata_types: list, _data_objects: list) -> None:
    from orgcompare.compare import load_results
    from orgcompare.report import generate_html, generate_csv

    results = load_results("output/reports/diff.json")
    generate_html(results, "output/reports/report.html", config["source_org"], config["target_org"])
    generate_csv(results, "output/reports")
    print("Report: output/reports/report.html")
    print("CSVs:   output/reports/<Type>_diff.csv")


def cmd_serve(_config: dict, _metadata_types: list, _data_objects: list) -> None:
    from orgcompare.server import run

    print("Starting web UI at http://localhost:5000")
    run()


def cmd_deploy(config: dict, _metadata_types: list, _data_objects: list) -> None:
    from orgcompare.compare import load_results
    from orgcompare.deploy import deploy_metadata, deploy_data

    results = load_results("output/reports/diff.json")
    target = config["target_org"]
    meta_items = [r for r in results if r.category == "metadata" and r.status != "identical"]
    data_items = [r for r in results if r.category == "data" and r.status != "identical"]
    if meta_items:
        result = deploy_metadata(meta_items, target)
        status = "OK" if result.get("success") else "FAILED"
        print(f"Metadata deploy: {status} — log: {result['log']}")
    if data_items:
        for r in deploy_data(data_items, config["data_objects"], target):
            status = "OK" if r.get("success") else "FAILED"
            print(f"Data deploy {r['object']}: {status} — log: {r.get('log', 'n/a')}")
    if not meta_items and not data_items:
        print("Nothing to deploy — no differences found.")


COMMANDS = {
    "retrieve": cmd_retrieve,
    "compare": cmd_compare,
    "report": cmd_report,
    "serve": cmd_serve,
    "deploy": cmd_deploy,
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="OrgCompare — compare Salesforce orgs",
        usage="python main.py [retrieve|compare|report|serve|deploy] ... [--profile NAME | --metadata TYPES --objects OBJS]",
    )
    parser.add_argument(
        "commands", nargs="+", choices=list(COMMANDS), help="Pipeline commands to run"
    )
    parser.add_argument("--profile", help="Named profile from profiles.yaml")
    parser.add_argument(
        "--metadata", help="Comma-separated metadata types, e.g. ApexClass,Flow"
    )
    parser.add_argument(
        "--objects", help="Comma-separated data object names, e.g. Product2,Pricebook2"
    )

    args = parser.parse_args()

    if args.profile and (args.metadata or args.objects):
        parser.error("--profile and --metadata/--objects are mutually exclusive")

    config = load_config()
    metadata_types, data_objects = resolve_selection(args, config)
    for cmd in args.commands:
        COMMANDS[cmd](config, metadata_types, data_objects)
