"""Read-only checks against sibling schema declarations, not service integration.

Only the named model classes are compiled: importing sibling applications would
start unrelated infrastructure. Standalone distributions can skip these checks.
"""

import ast
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from decision_engine.hashing import CONTENT_HASH_VERSION, content_sha256
from decision_engine.models import EmergencyContact, EmergencyInstructions


def read_models(relative_path, names):
    path = Path(__file__).resolve().parents[2] / relative_path
    if not path.exists():
        pytest.skip("Sibling source not present in standalone module checkout")
    source = ast.parse(path.read_text(encoding="utf-8-sig"))
    classes = [n for n in source.body if isinstance(n, ast.ClassDef) and n.name in names]
    assert {n.name for n in classes} == set(names)
    namespace = dict(
        BaseModel=BaseModel, ConfigDict=ConfigDict, Field=Field, Any=Any, datetime=datetime
    )
    exec(compile(ast.Module(body=classes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def test_02_strict_emergency_contract_with_contact(now):
    models = read_models(
        "02_api_backend/app/schemas/v1/travel.py",
        [
            "_Strict",
            "EmergencyContact",
            "SupportPlace",
            "EmergencyInstructions",
        ],
    )
    instructions = EmergencyInstructions(
        what_to_do_now="SYNTHETIC test instruction",
        contacts=[EmergencyContact(name="SYNTHETIC contact", phone="TEST-NOT-A-PHONE")],
    )
    parsed = models["EmergencyInstructions"].model_validate(instructions.model_dump(mode="json"))
    assert parsed.contacts[0].phone == "TEST-NOT-A-PHONE"


def test_08_contact_fragment_shape(now):
    models = read_models("08_recommendation_feedback/app/schema.py", ["EmergencyContact"])
    payload = {
        "name": "SYNTHETIC contact",
        "phone": "+1 202-555-0100",
        "contact_type": "test-support",
        "region": "TEST-REGION",
        "effective_date": now.isoformat(),
    }
    assert models["EmergencyContact"].model_validate(payload).region == "TEST-REGION"


def test_module_06_hashes_content_the_same_way_as_module_07():
    """The two copies of the hash helper must agree, or reviews silently stop matching."""
    path = (
        Path(__file__).resolve().parents[2]
        / "06_risk_knowledge_services/risk_knowledge/hashing.py"
    )
    if not path.exists():
        pytest.skip("Sibling source not present in standalone module checkout")
    namespace: dict[str, Any] = {}
    exec(compile(path.read_text(encoding="utf-8-sig"), str(path), "exec"), namespace)

    samples = [
        "plain text",
        "  spaced \n text  ",
        "ข้อความภาษาไทย พร้อมช่องว่าง",
        "line\r\nbreaks\tand\ttabs",
    ]
    for sample in samples:
        assert namespace["content_sha256"](sample) == content_sha256(sample)
    assert namespace["CONTENT_HASH_VERSION"] == CONTENT_HASH_VERSION
