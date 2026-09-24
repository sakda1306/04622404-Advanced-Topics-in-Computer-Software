"""Exercise an already running 07 service using fresh synthetic data only."""

import argparse
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from decision_engine.models import DecisionResponse
from decision_engine.policy import Policy
from decision_engine.sample_data import scenarios


def run(base_url: str):
    def get(path):
        with urlopen(base_url + path, timeout=5) as response:
            return json.load(response)

    assert get("/health")["status"] == "ok"
    assert get("/ready")["policy"] == "prototype-v3"
    schema = get("/openapi.json")
    assert schema["info"]["version"] == "0.3.0"
    assert (
        schema["components"]["schemas"]["DecisionResponse"]["properties"]["confidence"]["type"]
        == "number"
    )
    expected = {
        "low_risk": "NORMAL",
        "numeric_confidence": "NORMAL",
        "safer_route": "CHANGE_ROUTE",
        "safer_time": "DELAY",
    }
    samples = scenarios()
    for name, payload in samples.items():
        request = Request(
            base_url + "/v1/decisions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            result = DecisionResponse.model_validate_json(response.read())
        assert result.action_code == expected.get(name, "AVOID"), name
        assert 0 <= result.confidence <= 1, name
        assert result.versions.policy_sha256 == Policy.load("prototype-v3").digest
        if name in {"partial", "freshness_unknown", "partial_alternative", "summary_only_risk"}:
            assert result.confidence <= 0.25 and result.escalation_required, name
        if result.action_code == "AVOID":
            assert result.emergency_assessment.status == "fallback", name
            assert result.emergency_instructions.contacts == [], name
        print(f"PASS {name}: {result.action_code}, confidence={result.confidence}")
    bad = samples["low_risk"]
    bad["risk"]["confidence"] = True
    request = Request(
        base_url + "/v1/decisions",
        data=json.dumps(bad).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        urlopen(request, timeout=5)
    except HTTPError as error:
        assert error.code == 422
        assert json.load(error)["code"] == "INVALID_INPUT"
    else:
        raise AssertionError("Invalid input was accepted")
    print(f"PASS health/ready/schema, {len(samples)} scenarios, invalid input rejected")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8050")
    run(parser.parse_args().base_url.rstrip("/"))
