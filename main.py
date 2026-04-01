"""OrgCompare entry point — orchestrates retrieve, compare, report, serve, and deploy commands."""
import sys
import yaml


def load_config() -> dict:
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def cmd_retrieve(config: dict) -> None:
    from orgcompare.retrieve import retrieve_metadata, retrieve_data
    source = config["source_org"]
    target = config["target_org"]
    print(f"Retrieving metadata from {source}...")
    retrieve_metadata(source, config["metadata_types"], f"output/retrieved/{source}")
    print(f"Retrieving metadata from {target}...")
    retrieve_metadata(target, config["metadata_types"], f"output/retrieved/{target}")
    print(f"Retrieving data from {source}...")
    retrieve_data(source, config["data_objects"], f"output/retrieved/{source}")
    print(f"Retrieving data from {target}...")
    retrieve_data(target, config["data_objects"], f"output/retrieved/{target}")
    print("Done.")


def cmd_compare(config: dict) -> None:
    from orgcompare.compare import compare_metadata, compare_data, save_results
    source = config["source_org"]
    target = config["target_org"]
    print("Comparing metadata...")
    meta_diffs = compare_metadata(
        f"output/retrieved/{source}", f"output/retrieved/{target}"
    )
    print("Comparing data...")
    data_diffs = compare_data(
        f"output/retrieved/{source}", f"output/retrieved/{target}",
        config["data_objects"],
    )
    all_diffs = meta_diffs + data_diffs
    save_results(all_diffs, "output/reports/diff.json")
    total = len(all_diffs)
    different = sum(1 for r in all_diffs if r.status != "identical")
    print(f"Done. {different} differences out of {total} items. Results: output/reports/diff.json")


def cmd_report(config: dict) -> None:
    from orgcompare.compare import load_results
    from orgcompare.report import generate_html, generate_csv
    results = load_results("output/reports/diff.json")
    generate_html(results, "output/reports/report.html", config["source_org"], config["target_org"])
    generate_csv(results, "output/reports")
    print("Report: output/reports/report.html")
    print("CSVs:   output/reports/<Type>_diff.csv")


def cmd_serve(_config: dict) -> None:
    from orgcompare.server import run
    print("Starting web UI at http://localhost:5000")
    run()


def cmd_deploy(config: dict) -> None:
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
    args = sys.argv[1:]
    if not args:
        print(f"Usage: python main.py [{'|'.join(COMMANDS)}] ...")
        print("Commands can be chained: python main.py retrieve compare report")
        sys.exit(1)

    for cmd in args:
        if cmd not in COMMANDS:
            print(f"Unknown command: '{cmd}'. Valid: {list(COMMANDS)}")
            sys.exit(1)

    config = load_config()
    for cmd in args:
        COMMANDS[cmd](config)
