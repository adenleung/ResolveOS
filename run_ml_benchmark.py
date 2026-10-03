"""Run separately from regression; accepts only a reviewed synthetic manifest."""
import argparse
import json
from pathlib import Path
from app.ml.benchmark import compare, write_report
from app.ml.dataset import DATASET_VERSION, TASKS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    required = {"dataset_version", "synthetic_only", "task", "seed", "scenario_holdout", "rows"}
    if set(manifest) != required or manifest["synthetic_only"] is not True or manifest["dataset_version"] != DATASET_VERSION or manifest["task"] not in TASKS:
        raise ValueError("Invalid synthetic dataset manifest")
    if type(manifest["seed"]) is not int or type(manifest["scenario_holdout"]) is not bool:
        raise ValueError("Invalid split configuration")
    write_report(compare(manifest["rows"], manifest["task"], manifest["dataset_version"], manifest["seed"], manifest["scenario_holdout"]), args.output)


if __name__ == "__main__":
    main()
