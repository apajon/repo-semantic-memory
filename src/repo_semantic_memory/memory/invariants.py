"""Standalone YAML import/export for claims and invariants."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repo_semantic_memory.model import Claim, Invariant

try:
    import yaml  # type: ignore[import-untyped]
except ModuleNotFoundError:  # pragma: no cover - fallback path for minimal runtime installs.
    yaml = None


@dataclass(frozen=True)
class InvariantsDocument:
    """Portable, deterministic payload used by `rsm invariants` commands."""

    claims: tuple[Claim, ...] = ()
    invariants: tuple[Invariant, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Serialize document to deterministic dictionary payload."""
        ordered_claims = sorted(self.claims, key=lambda claim: claim.id)
        ordered_invariants = sorted(self.invariants, key=lambda invariant: invariant.id)
        return {
            "claims": [claim.to_dict() for claim in ordered_claims],
            "invariants": [invariant.to_dict() for invariant in ordered_invariants],
        }

    def to_yaml(self) -> str:
        """Render document as deterministic JSON-formatted YAML 1.2-compatible output."""
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> InvariantsDocument:
        """Build document from dictionary payload."""
        claims_payload = payload.get("claims", [])
        invariants_payload = payload.get("invariants", [])
        if not isinstance(claims_payload, list):
            raise ValueError("claims must be a list")
        if not isinstance(invariants_payload, list):
            raise ValueError("invariants must be a list")

        claims = []
        for item in claims_payload:
            if not isinstance(item, dict):
                raise ValueError("Claim items must be dictionaries")
            claims.append(Claim.from_dict(item))

        invariants = []
        for item in invariants_payload:
            if not isinstance(item, dict):
                raise ValueError("Invariant items must be dictionaries")
            invariants.append(Invariant.from_dict(item))

        return cls(claims=tuple(claims), invariants=tuple(invariants))


def export_invariants_yaml(
    *,
    out_path: Path | str,
    claims: tuple[Claim, ...] = (),
    invariants: tuple[Invariant, ...] = (),
) -> InvariantsDocument:
    """Write claims/invariants document to a YAML file path."""
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    document = InvariantsDocument(claims=claims, invariants=invariants)
    target.write_text(document.to_yaml(), encoding="utf-8")
    return document


def import_invariants_yaml(path: Path | str) -> InvariantsDocument:
    """Read and validate claims/invariants document from YAML file path."""
    source = Path(path)
    payload = _load_yaml_payload(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Invariant YAML payload must be a dictionary")
    return InvariantsDocument.from_dict(payload)


def _load_yaml_payload(content: str) -> Any:
    if yaml is not None:
        return yaml.safe_load(content)
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "PyYAML is not installed and the content is not valid JSON. "
            "Install PyYAML with 'uv add pyyaml' or provide JSON-formatted YAML."
        ) from exc
