"""Validate canonical schemas and detect drift in generated consumers.

This check deliberately has no dependency on service implementations. It parses every
canonical OpenAPI/JSON-Schema document, validates representative contract instances, and
compares the generated Python/TypeScript vocabularies to the canonical enum definitions.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
EXPECTED_PATHS = {
    "chat.openapi.yaml": {
        "/api/v1/conversations",
        "/api/v1/conversations/{conversation_id}",
        "/api/v1/manager/session",
        "/api/v1/seed",
        "/api/v1/conversations/{conversation_id}/messages",
        "/api/v1/conversations/{conversation_id}/events",
        "/api/v1/conversations/{conversation_id}/complaints/{draft_id}",
        "/api/v1/conversations/{conversation_id}/complaints/{draft_id}/confirm",
        "/api/v1/messages/{message_id}/feedback",
        "/api/v1/manager/complaints",
        "/api/v1/manager/complaints/{complaint_id}",
        "/health/live",
        "/health/ready",
        "/version",
    },
    "retrieval.openapi.yaml": {"/v1/retrieve", "/health/live", "/health/ready", "/version"},
    "model.openapi.yaml": {"/v1/chat/completions", "/health/live", "/health/ready", "/version"},
}
OWNER_FIXTURES = {
    ROOT / "components/01-model-preparation/fixtures/evaluation/decision-cases-v1.jsonl": 70,
    ROOT / "components/03-rag-platform/fixtures/evaluation/retrieval-golden-v1.jsonl": 60,
    ROOT / "components/04-support-runtime/fixtures/evaluation/runtime-cases.jsonl": 75,
    ROOT / "tests/system/fixtures/grounded-answers.jsonl": 80,
    ROOT / "tests/system/fixtures/dependency-failures.jsonl": 15,
}
EXPECTED_SCHEMAS = {
    "decision.schema.json",
    "complaint.schema.json",
    "model-manifest.schema.json",
    "rag-index-manifest.schema.json",
    "runtime-events.schema.json",
}
OPENAPI_METHODS = {"get", "post", "patch", "delete", "put", "head", "options"}


def _local_refs(value: Any) -> list[str]:
    """Return local JSON pointers nested in an OpenAPI/JSON-Schema value."""
    refs: list[str] = []
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/"):
            refs.append(ref)
        for child in value.values():
            refs.extend(_local_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.extend(_local_refs(child))
    return refs


def _resolve_pointer(document: dict[str, Any], pointer: str) -> Any:
    current: Any = document
    for part in pointer.removeprefix("#/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def fail(message: str) -> None:
    raise SystemExit(f"contract verification failed: {message}")


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError as exc:
        fail("PyYAML is required to parse OpenAPI contracts")
        raise AssertionError from exc
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"{path.relative_to(ROOT)} is not valid YAML: {exc}")
    if not isinstance(value, dict):
        fail(f"{path.relative_to(ROOT)} must contain an object")
    return value


def validate_openapi(path: Path) -> None:
    document = load_yaml(path)
    if document.get("openapi") != "3.1.0":
        fail(f"{path.name} must target OpenAPI 3.1.0")
    info = document.get("info")
    if not isinstance(info, dict) or not isinstance(info.get("version"), str):
        fail(f"{path.name} has no contract version")
    paths = document.get("paths")
    if not isinstance(paths, dict) or set(paths) != EXPECTED_PATHS[path.name]:
        fail(f"{path.name} paths do not match the declared service surface")
    components = document.get("components")
    if not isinstance(components, dict) or not isinstance(components.get("schemas"), dict):
        fail(f"{path.name} has no reusable schemas")
    operation_ids: set[str] = set()
    for route, item in paths.items():
        if not isinstance(item, dict):
            fail(f"{path.name} {route} is not an object")
        template_names = set(re.findall(r"\{([^}]+)\}", route))
        path_parameters = item.get("parameters", [])
        if not isinstance(path_parameters, list):
            fail(f"{path.name} {route} path parameters are invalid")
        path_parameters = [
            _resolve_pointer(document, parameter["$ref"])
            if isinstance(parameter, dict) and isinstance(parameter.get("$ref"), str)
            else parameter
            for parameter in path_parameters
        ]
        operations = [value for key, value in item.items() if key.lower() in OPENAPI_METHODS]
        if not operations:
            fail(f"{path.name} {route} has no HTTP operation")
        for operation in operations:
            if not isinstance(operation, dict) or not isinstance(operation.get("operationId"), str):
                fail(f"{path.name} {route} operationId is missing")
            operation_id = operation["operationId"]
            if operation_id in operation_ids:
                fail(f"{path.name} contains duplicate operationId {operation_id}")
            operation_ids.add(operation_id)
            operation_parameters = operation.get("parameters", [])
            if not isinstance(operation_parameters, list):
                fail(f"{path.name} {route} operation parameters are invalid")
            parameters = path_parameters + [
                _resolve_pointer(document, parameter["$ref"])
                if isinstance(parameter, dict) and isinstance(parameter.get("$ref"), str)
                else parameter
                for parameter in operation_parameters
            ]
            parameter_names = {
                parameter.get("name")
                for parameter in parameters
                if isinstance(parameter, dict) and parameter.get("in") == "path"
            }
            if template_names - parameter_names:
                fail(f"{path.name} {route} has undocumented path parameters")
            for parameter in parameters:
                if (
                    isinstance(parameter, dict)
                    and parameter.get("in") == "path"
                    and parameter.get("required") is not True
                ):
                    fail(f"{path.name} {route} path parameters must be required")
            request_body = operation.get("requestBody")
            if (
                request_body is not None
                and isinstance(request_body, dict)
                and "content" in request_body
            ):
                _validate_content(path, route, request_body["content"], "request body")
            responses = operation.get("responses") if isinstance(operation, dict) else None
            if not isinstance(responses, dict) or not responses:
                fail(f"{path.name} {route} has no responses")
            for status, response in responses.items():
                if not isinstance(response, dict):
                    fail(f"{path.name} {route} response {status} is invalid")
                if "$ref" not in response and not response.get("description"):
                    fail(f"{path.name} {route} response {status} has no description")
                if "$ref" not in response and "content" in response:
                    _validate_content(path, route, response["content"], f"response {status}")
                if (
                    str(status).startswith("2")
                    and status != "204"
                    and "$ref" not in response
                    and "content" not in response
                ):
                    fail(f"{path.name} {route} success response {status} has no schema/content")
    for reference in _local_refs(document):
        if _resolve_pointer(document, reference) is None:
            fail(f"{path.name} contains an unresolved reference {reference}")


def _validate_content(path: Path, route: str, content: Any, label: str) -> None:
    if not isinstance(content, dict) or not content:
        fail(f"{path.name} {route} {label} content is empty")
    for media_type, media in content.items():
        if not isinstance(media, dict) or not isinstance(media.get("schema"), dict):
            fail(f"{path.name} {route} {label} {media_type} has no schema")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"{path.relative_to(ROOT)} is not valid JSON: line {exc.lineno}, column {exc.colno}")
    if not isinstance(value, dict):
        fail(f"{path.relative_to(ROOT)} must contain an object")
    return value


def json_schema_checks() -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    for path in sorted(CONTRACTS.rglob("*.schema.json")):
        schema = load_json(path)
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            fail(f"{path.relative_to(ROOT)} must use draft 2020-12")
        if not isinstance(schema.get("$id"), str) or schema.get("type") != "object":
            fail(f"{path.relative_to(ROOT)} must have a stable id and object root")
        required = schema.get("required")
        if not isinstance(required, list) or len(required) != len(set(required)):
            fail(f"{path.relative_to(ROOT)} has invalid required fields")
        if schema.get("additionalProperties") is not False:
            fail(f"{path.relative_to(ROOT)} must reject unknown fields")
        try:
            from jsonschema import Draft202012Validator
        except ImportError as exc:
            fail("jsonschema is required to validate canonical JSON Schemas")
            raise AssertionError from exc
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            fail(f"{path.relative_to(ROOT)} is not a valid draft 2020-12 schema: {exc}")
        for reference in _local_refs(schema):
            if _resolve_pointer(schema, reference) is None:
                fail(f"{path.relative_to(ROOT)} contains an unresolved reference {reference}")
        schemas[path.name] = schema
    if set(schemas) != EXPECTED_SCHEMAS:
        fail("canonical JSON Schema set is incomplete or contains an unexpected duplicate")
    return schemas


def validate_examples(schemas: dict[str, dict[str, Any]]) -> None:
    """Run jsonschema when available; still perform strict structural checks in minimal images."""
    from jsonschema import Draft202012Validator

    decision = {
        "class": "complaint",
        "intent": "delivery_delay",
        "expected_action": "complaint_tool",
        "rag_required": False,
        "safety_class": "normal",
        "clarification_question": None,
        "complaint": {
            "complaint_text": "The delivery is five days late and I need assistance.",
            "category": "complaint",
            "complaint_type": "delivery_delay",
            "customer_context": "Order details were not provided.",
            "submission_mode": "confirmation_required",
            "consent_evidence": None,
        },
    }
    for name, value in {
        "decision.schema.json": decision,
        "complaint.schema.json": {
            "complaint_text": "The delivery is five days late and I need assistance.",
            "category": "complaint",
            "complaint_type": "delivery_delay",
            "customer_context": "",
        },
        "runtime-events.schema.json": {
            "event": "completed",
            "request_id": "req_12345678",
            "sequence": 1,
            "data": {"outcome": "rag_answer"},
        },
        "model-manifest.schema.json": {
            "schema_version": "1.0",
            "model_id": "demo",
            "model_version": "demo-1",
            "base_model": "Qwen/Qwen3-4B",
            "base_revision": "revision-123",
            "adapter_uri": "artifact://adapter",
            "adapter_sha256": "a" * 64,
            "dataset_manifest_sha256": "b" * 64,
            "training_config_sha256": "c" * 64,
            "chat_template_sha256": "d" * 64,
            "evaluation_report_sha256": "e" * 64,
            "license_review": "approved",
            "quality_gate": "passed",
            "created_at": "2026-09-12T00:00:00Z",
            "git_commit": "deadbeef",
        },
        "rag-index-manifest.schema.json": {
            "schema_version": "1.0",
            "index_version": "idx_demo",
            "workspace_id": "anonymous-furniture-company",
            "embedding_model": "BAAI/bge-base-en-v1.5",
            "embedding_revision": "revision-123",
            "embedding_dimensions": 768,
            "reranker_model": "BAAI/bge-reranker-base",
            "reranker_revision": "revision-456",
            "chunking_config_sha256": "a" * 64,
            "source_manifest_sha256": "b" * 64,
            "document_count": 1,
            "chunk_count": 1,
            "retrieval_report_sha256": "c" * 64,
            "quality_gate": "passed",
            "status": "active",
            "created_at": "2026-09-12T00:00:00Z",
            "git_commit": "deadbeef",
        },
    }.items():
        errors = sorted(
            Draft202012Validator(schemas[name]).iter_errors(value),
            key=lambda error: list(error.path),
        )
        if errors:
            fail(f"representative {name} does not validate: {errors[0].message}")


def parse_python_consumer() -> tuple[set[str], set[str], set[str]]:
    path = ROOT / "packages/python-contracts/support_contracts/contracts.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values: dict[str, set[str]] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id
            in {"BUSINESS_CLASSES", "ALLOWED_ACTIONS", "ALLOWED_COMPLAINT_TYPES", "RUNTIME_EVENTS"}
        ):
            try:
                value_node = node.value
                if (
                    isinstance(value_node, ast.Call)
                    and isinstance(value_node.func, ast.Name)
                    and value_node.func.id == "frozenset"
                ):
                    value_node = value_node.args[0]
                literal = ast.literal_eval(value_node)
            except (ValueError, TypeError, IndexError):
                continue
            values[node.targets[0].id] = set(literal)
    return (
        values.get("BUSINESS_CLASSES", set()),
        values.get("ALLOWED_ACTIONS", set()),
        values.get("ALLOWED_COMPLAINT_TYPES", set()) | values.get("RUNTIME_EVENTS", set()),
    )


def parse_typescript_consumer() -> tuple[set[str], set[str], set[str], set[str]]:
    text = (ROOT / "packages/typescript-contracts/src/index.ts").read_text(encoding="utf-8")

    def array(name: str) -> set[str]:
        match = re.search(rf"(?:const|let)\s+{name}\s*=\s*\[(.*?)\]\s+as\s+const", text, re.S)
        if not match:
            return set()
        return set(re.findall(r'"([^"\n]+)"', match.group(1)))

    events = set(
        re.findall(
            r'\|\s*"([a-z._]+)"',
            text.split("RuntimeEventName", 1)[-1].split("export interface", 1)[0],
        )
    )
    action_section = text.split("export type ExpectedAction", 1)[-1].split(";", 1)[0]
    actions = set(re.findall(r'"([^"\n]+)"', action_section))
    return array("businessClasses"), actions, array("complaintTypes"), events


def consumer_drift() -> None:
    classes, actions, complaint_and_events = parse_python_consumer()
    ts_classes, ts_actions, ts_complaints, ts_events = parse_typescript_consumer()
    decision = load_json(CONTRACTS / "decision.schema.json")
    defs = decision["$defs"]
    expected_classes = set(defs["businessClass"]["enum"])
    expected_actions = set(defs["action"]["enum"])
    expected_complaints = set(defs["complaintType"]["enum"])
    event_schema = load_json(CONTRACTS / "events/runtime-events.schema.json")
    expected_events = set(event_schema["properties"]["event"]["enum"])
    if classes != expected_classes or ts_classes != expected_classes:
        fail(f"business class consumer drift: python={classes}, typescript={ts_classes}")
    if actions != expected_actions or ts_actions != expected_actions:
        fail(f"action consumer drift: python={actions}, typescript={ts_actions}")
    if (
        (complaint_and_events - set()) != expected_complaints | expected_events
        or ts_complaints != expected_complaints
        or ts_events != expected_events
    ):
        fail("complaint/event consumer drift detected")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            fail(f"{path.relative_to(ROOT)} line {number} is invalid JSONL: {exc.msg}")
        if not isinstance(value, dict):
            fail(f"{path.relative_to(ROOT)} line {number} is not an object")
        rows.append(value)
    return rows


def _require_fields(row: dict[str, Any], fields: set[str], path: Path) -> None:
    missing = fields - set(row)
    if missing:
        fail(
            f"{path.relative_to(ROOT)} case "
            f"{row.get('case_id', '<unknown>')} is missing {sorted(missing)}"
        )


def validate_fixture_content(path: Path, rows: list[dict[str, Any]]) -> None:
    """Reject counted-but-empty fixtures and verify each owner's wire shape."""
    if path.name == "decision-cases-v1.jsonl":
        required = {
            "case_id",
            "class",
            "intent",
            "expected_action",
            "rag_required",
            "safety_class",
            "complaint_type",
            "synthetic_data",
        }
        for row in rows:
            _require_fields(row, required, path)
            if row["synthetic_data"] is not True or row["expected_action"] not in {
                "answer",
                "rag_answer",
                "clarify",
                "complaint_tool",
                "abstain",
            }:
                fail(f"{path.relative_to(ROOT)} contains an invalid decision case {row['case_id']}")
            if not isinstance(row["intent"], str) or not row["intent"]:
                fail(f"{path.relative_to(ROOT)} case {row['case_id']} has no intent")
            if row["expected_action"] == "rag_answer" and row["rag_required"] is not True:
                fail(
                    f"{path.relative_to(ROOT)} case {row['case_id']} routes to "
                    "RAG without rag_required=true"
                )
    elif path.name == "retrieval-golden-v1.jsonl":
        required = {
            "case_id",
            "query",
            "workspace_id",
            "audience",
            "language",
            "as_of",
            "expected_document_ids",
        }
        for row in rows:
            _require_fields(row, required, path)
            if not isinstance(row["query"], str) or len(row["query"].strip()) < 8:
                fail(f"{path.relative_to(ROOT)} case {row['case_id']} has no substantive query")
            if (
                row["workspace_id"] != "anonymous-furniture-company"
                or row["audience"] != "customer"
                or row["language"] != "en"
            ):
                fail(
                    f"{path.relative_to(ROOT)} case {row['case_id']} has an "
                    "invalid retrieval context"
                )
            if (
                not isinstance(row["expected_document_ids"], list)
                or not row["expected_document_ids"]
            ):
                fail(f"{path.relative_to(ROOT)} case {row['case_id']} has no expected document")
    elif path.name == "runtime-cases.jsonl":
        required = {"case_id", "family", "message", "expected"}
        for row in rows:
            _require_fields(row, required, path)
            expected = row["expected"]
            if (
                not isinstance(expected, dict)
                or not isinstance(row["message"], str)
                or len(row["message"].strip()) < 8
            ):
                fail(f"{path.relative_to(ROOT)} case {row['case_id']} is not substantive")
            _require_fields(expected, {"action", "submit_allowed"}, path)
            if not isinstance(expected["submit_allowed"], bool):
                fail(
                    f"{path.relative_to(ROOT)} case {row['case_id']} has an "
                    "invalid submit_allowed gate"
                )
            if expected["action"] in {"abstain", "clarify"} and not isinstance(
                expected.get("outcome"), str
            ):
                fail(f"{path.relative_to(ROOT)} case {row['case_id']} has no expected outcome")
            if expected["action"] == "complaint_tool" and not isinstance(
                expected.get("complaint_type"), str
            ):
                fail(f"{path.relative_to(ROOT)} case {row['case_id']} has no complaint type")
    elif path.name == "grounded-answers.jsonl":
        required = {
            "case_id",
            "family",
            "message",
            "query",
            "expected_action",
            "expected_outcome",
            "expected_document_ids",
            "allowed_citation_ids",
            "required_citation_ids",
            "required_facts",
            "forbidden_claims",
            "owner_components",
            "synthetic_data",
        }
        for row in rows:
            _require_fields(row, required, path)
            if row["synthetic_data"] is not True or row["expected_action"] != "rag_answer":
                fail(
                    f"{path.relative_to(ROOT)} case {row['case_id']} is not a grounded-answer case"
                )
            for field in (
                "expected_document_ids",
                "allowed_citation_ids",
                "required_citation_ids",
                "required_facts",
                "forbidden_claims",
            ):
                if not isinstance(row[field], list) or not row[field]:
                    fail(f"{path.relative_to(ROOT)} case {row['case_id']} has empty {field}")
            if set(row["owner_components"]) != {"03-rag-platform", "04-support-runtime"}:
                fail(f"{path.relative_to(ROOT)} case {row['case_id']} has invalid owners")
    elif path.name == "dependency-failures.jsonl":
        required = {
            "case_id",
            "family",
            "message",
            "dependency",
            "expected_action",
            "expected_outcome",
            "expected_error_code",
            "must_preserve_conversation",
            "must_not_submit_complaint",
            "owner_components",
            "synthetic_data",
        }
        for row in rows:
            _require_fields(row, required, path)
            if row["synthetic_data"] is not True or row["family"] != "dependency_failure":
                fail(
                    f"{path.relative_to(ROOT)} case {row['case_id']} is not a "
                    "dependency-failure case"
                )
            if row["dependency"] not in {"rag", "model_decision", "model_answer"}:
                fail(f"{path.relative_to(ROOT)} case {row['case_id']} has an unknown dependency")
            if (
                row["must_preserve_conversation"] is not True
                or row["must_not_submit_complaint"] is not True
            ):
                fail(
                    f"{path.relative_to(ROOT)} case {row['case_id']} weakens "
                    "dependency safety assertions"
                )


def fixture_ownership() -> None:
    seen: set[str] = set()
    total = 0
    for path, expected_count in OWNER_FIXTURES.items():
        if not path.exists():
            fail(f"missing evaluation fixture {path.relative_to(ROOT)}")
        rows = read_jsonl(path)
        if len(rows) != expected_count:
            fail(f"{path.relative_to(ROOT)} has {len(rows)} rows, expected {expected_count}")
        ids = [row.get("case_id") for row in rows]
        if any(not isinstance(case_id, str) or not case_id for case_id in ids):
            fail(f"{path.relative_to(ROOT)} contains a missing case_id")
        if len(set(ids)) != len(ids) or seen.intersection(ids):
            fail(f"duplicate case_id across evaluation owners at {path.relative_to(ROOT)}")
        validate_fixture_content(path, rows)
        seen.update(ids)
        total += len(rows)
    if total != 300:
        fail(f"evaluation ownership totals {total}, expected 300")


def main() -> int:
    for filename in EXPECTED_PATHS:
        validate_openapi(CONTRACTS / filename)
    schemas = json_schema_checks()
    validate_examples(schemas)
    consumer_drift()
    fixture_ownership()
    print(
        "verified 3 OpenAPI contracts, 5 JSON Schemas, generated consumers, "
        "and 300 unique JSONL cases"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
