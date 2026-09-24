from __future__ import annotations

from app.infrastructure.agent.contracts import (
    EmergencyContact as ContractEmergencyContact,
)
from app.infrastructure.agent.contracts import (
    EmergencyInstructions as ContractEmergencyInstructions,
)
from app.schemas.v1.travel import (
    EmergencyContact as SchemaEmergencyContact,
)
from app.schemas.v1.travel import (
    EmergencyInstructions as SchemaEmergencyInstructions,
)


def test_schema_emergency_contact_accepts_metadata() -> None:
    contact = SchemaEmergencyContact(
        name="Tourist Police",
        phone="1155",
        url="https://touristpolice.go.th",
        available_hours="24/7",
        metadata={"priority": "high", "coverage_radius_km": 50},
    )
    assert contact.name == "Tourist Police"
    assert contact.phone == "1155"
    assert contact.metadata == {"priority": "high", "coverage_radius_km": 50}

    # Test default metadata is None
    contact_no_meta = SchemaEmergencyContact(
        name="Highway Police",
        phone="1193",
    )
    assert contact_no_meta.metadata is None

    instructions = SchemaEmergencyInstructions(
        what_to_do_now="Pull over safely",
        safety_steps=["Turn on hazard lights"],
        contacts=[contact],
    )
    assert len(instructions.contacts) == 1
    instruction_metadata = instructions.contacts[0].metadata
    assert instruction_metadata is not None
    assert instruction_metadata["coverage_radius_km"] == 50


def test_contract_emergency_contact_accepts_metadata() -> None:
    contact = ContractEmergencyContact(
        name="Medical Emergency",
        phone="1669",
        metadata={"dispatch": "direct", "responder_type": "ambulance"},
    )
    contact_metadata = contact.metadata
    assert contact_metadata is not None
    assert contact_metadata["dispatch"] == "direct"

    instructions = ContractEmergencyInstructions(
        what_to_do_now="Call EMS immediately",
        safety_steps=["Check breathing"],
        contacts=[contact],
    )
    assert len(instructions.contacts) == 1
    instruction_metadata = instructions.contacts[0].metadata
    assert instruction_metadata is not None
    assert instruction_metadata["responder_type"] == "ambulance"
