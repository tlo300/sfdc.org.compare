"""
DiffResult model for representing differences between Salesforce org components.
"""
from dataclasses import dataclass, asdict


@dataclass
class DiffResult:
    """
    Represents a single difference detected between source and target orgs.

    Attributes:
        category: Type of comparison - "metadata" or "data"
        type: Salesforce object type (e.g. "ApexClass", "Product2")
        name: Name of the component (e.g. "OrderService", "Enterprise License")
        status: Change status - "added", "modified", "removed", or "identical"
        source_value: Component data from source org
        target_value: Component data from target org
        diff: DeepDiff output showing specific changes
        xml_diff: Unified diff string for metadata items; None for data rows
    """
    category: str   # "metadata" | "data"
    type: str       # e.g. "ApexClass", "Product2"
    name: str       # e.g. "OrderService", "Enterprise License"
    status: str     # "added" | "modified" | "removed" | "identical"
    source_value: dict
    target_value: dict
    diff: dict
    xml_diff: str | None = None

    def to_dict(self) -> dict:
        """Convert DiffResult to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DiffResult":
        """Reconstruct DiffResult from dictionary."""
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
