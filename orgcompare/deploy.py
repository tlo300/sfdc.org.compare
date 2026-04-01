# Stub — full implementation in Task 9
from typing import List
from orgcompare.models import DiffResult


def deploy_metadata(diff_results: List[DiffResult], target_org: str, dry_run: bool = False) -> dict:
    raise NotImplementedError("deploy_metadata not yet implemented")


def deploy_data(diff_results: List[DiffResult], data_objects_config: List[dict], target_org: str, dry_run: bool = False) -> List[dict]:
    raise NotImplementedError("deploy_data not yet implemented")
