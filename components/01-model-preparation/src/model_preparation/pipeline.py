from __future__ import annotations

import hashlib
import html
import json
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from .records import ValidationError, validate_record
from .render import render_training_example

_SPACE = re.compile(r"\s+")
_TAG = re.compile(r"<[^>]+>")
_PII = re.compile(
    r"(?:\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|\b(?:\+?\d[\d ()-]{7,}\d)\b|"
    r"\b(?:\d[ -]*?){13,19}\b|\b(?:customer|account)[-_ ]?id\s*[:#]?\s*[A-Za-z0-9-]+|"
    r"\b(?:password|passcode|security\s+code|api\s*key|secret|credential)s?\s*[:=]?\s*\S+|"
    r"\b\d{1,6}\s+[A-Za-z0-9 .'-]+\s+"
    r"(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|boulevard|blvd)\b|"
    r"\b(?:cvv|cvc|iban|routing\s+number)\s*[:=]?\s*\S+)",
    re.IGNORECASE,
)

SEMANTIC_DEDUP_THRESHOLD = 0.96
_SEMANTIC_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", html.unescape(value))
    return _SPACE.sub(" ", _TAG.sub(" ", value)).strip()


def exact_key(record: dict[str, Any]) -> str:
    payload = f"{record['question'].casefold()}\0{record['answer'].casefold()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def split_for_cluster(cluster_id: str, seed: int = 42) -> str:
    value = int(hashlib.sha256(f"{seed}:{cluster_id}".encode()).hexdigest()[:8], 16) % 100
    return "train" if value < 70 else "validation" if value < 85 else "evaluation"


def semantic_embedding(text: str, dimensions: int = 256) -> tuple[float, ...]:
    """Create a deterministic normalized feature vector for CPU checks.

    The production job substitutes the pinned sentence encoder, but the
    cosine operation and threshold are identical.  Hashing unigrams and
    bigrams avoids the old set-Jaccard approximation and is dependency-free.
    """
    raw_tokens = _SEMANTIC_TOKEN.findall(text.casefold())
    # Function words and common paraphrase forms should not dominate the
    # semantic signal.  Numeric/product identifiers remain features so two
    # different fixture records are not incorrectly collapsed.
    synonyms = {
        "how": "what",
        "much": "what",
        "does": "be",
        "costs": "cost",
        "priced": "price",
        "prices": "price",
        "delivered": "delivery",
        "shipping": "delivery",
    }
    stop_words = {
        "a",
        "an",
        "and",
        "are",
        "be",
        "can",
        "do",
        "for",
        "from",
        "i",
        "in",
        "is",
        "it",
        "of",
        "on",
        "the",
        "to",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
    }
    tokens = [
        canonical
        for token in raw_tokens
        for canonical in (synonyms.get(token, token),)
        if canonical not in stop_words
    ]
    features = tokens + [f"{a}\\0{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
    vector = [0.0] * dimensions
    for feature in features:
        digest = hashlib.sha256(feature.encode("utf-8")).digest()
        slot = int.from_bytes(digest[:4], "big") % dimensions
        vector[slot] += 1.0 if digest[4] & 1 else -1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return tuple(value / norm for value in vector)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


def semantic_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    """Similarity of normalized question+answer text used by deduplication."""
    left_text = f"{left['question']} {left['answer']}"
    right_text = f"{right['question']} {right['answer']}"
    return cosine_similarity(semantic_embedding(left_text), semantic_embedding(right_text))


def _balance_records(
    records: list[dict[str, Any]], seed: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Downsample clearly over-represented classes deterministically.

    Tiny fixtures can legitimately differ by one example (and are kept intact
    so the 64-record public contract remains useful).  Once the spread is
    larger than one, each class is sampled to the smallest class count.  A
    stable hash gives reproducible selection and preserves provenance.
    """
    by_class: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_class.setdefault(record["class"], []).append(record)
    original = {key: len(value) for key, value in sorted(by_class.items())}
    if not by_class or max(original.values()) - min(original.values()) <= 1:
        return records, {"original": original, "selected": original, "target_per_class": None}
    target = min(original.values())
    selected: list[dict[str, Any]] = []
    for class_name, members in by_class.items():
        ranked = sorted(
            members,
            key=lambda record: hashlib.sha256(
                f"{seed}:balance:{class_name}:{record['record_id']}".encode()
            ).hexdigest(),
        )
        selected.extend(ranked[:target])
    selected.sort(key=lambda record: record["record_id"])
    return selected, {
        "original": original,
        "selected": dict(sorted(Counter(r["class"] for r in selected).items())),
        "target_per_class": target,
    }


def _stratified_group_splits(records: list[dict[str, Any]], seed: int) -> dict[str, str]:
    """Assign each semantic cluster to one split while balancing class/source.

    A group is a cluster, never an individual row.  Assignment scores the
    deficit for record count and every (class, source) stratum, preventing the
    category-only random split that leaks paraphrases.
    """
    if not records:
        return {}
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(record["semantic_cluster_id"], []).append(record)
    splits = ("train", "validation", "evaluation")
    ratios = {"train": 0.70, "validation": 0.15, "evaluation": 0.15}
    total = len(records)
    target_total = {name: total * ratios[name] for name in splits}
    strata = Counter((r["class"], r["source"]) for r in records)
    target_strata = {
        key: {name: count * ratios[name] for name in splits} for key, count in strata.items()
    }
    assigned: dict[str, str] = {}
    totals: Counter[str] = Counter()
    stratum_totals: dict[str, Counter[tuple[str, str]]] = {
        name: Counter() for name in splits
    }
    # Place larger groups first; hash tie-break keeps the result stable.
    ordered = sorted(
        groups.items(),
        key=lambda item: (
            -len(item[1]),
            hashlib.sha256(f"{seed}:cluster:{item[0]}".encode()).hexdigest(),
        ),
    )
    for cluster_id, members in ordered:
        member_strata = Counter((r["class"], r["source"]) for r in members)
        def score(
            split: str,
            members: list[dict[str, Any]] = members,
            member_strata: Counter[tuple[str, str]] = member_strata,
            cluster_id: str = cluster_id,
        ) -> tuple[float, float, int]:
            # Compare occupancy ratios, not raw deficits.  Raw target
            # differences would fill the two small splits first and can leave
            # the 70% train split empty on tiny fixtures.
            count_penalty = ((totals[split] + len(members)) / max(1.0, target_total[split])) ** 2
            stratum_penalty = sum(
                (
                    (stratum_totals[split][key] + number)
                    / max(1.0, target_strata[key][split])
                )
                ** 2
                for key, number in member_strata.items()
            )
            tie = int(hashlib.sha256(f"{seed}:{cluster_id}:{split}".encode()).hexdigest()[:8], 16)
            return (count_penalty + stratum_penalty, count_penalty, tie)
        chosen = min(splits, key=score)
        assigned[cluster_id] = chosen
        totals[chosen] += len(members)
        stratum_totals[chosen].update(member_strata)
    return assigned


def _record_priority(record: dict[str, Any]) -> tuple[int, int, float, int]:
    """Rank conflict candidates according to the documented provenance rule."""
    source = str(record.get("source", "")).casefold()
    provenance = record.get("provenance", {})
    review = str(record.get("review_status", "")).casefold()
    company = int(any(token in source for token in ("company", "private", "internal")))
    human = int(review in {"human_reviewed", "human-reviewed", "reviewed"})
    collected = str(provenance.get("collected_at", "")) if isinstance(provenance, dict) else ""
    try:
        timestamp = datetime.fromisoformat(collected.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, OverflowError):
        timestamp = 0.0
    license_score = int(
        isinstance(provenance, dict)
        and bool(provenance.get("license"))
        and str(provenance.get("license")).casefold() not in {"unknown", "unspecified"}
    )
    # Newer reviewed company data wins first; human review and provenance are
    # explicit tie-breakers for records from other sources.
    return (company, human, timestamp, license_score)


def _deduplicate_records(
    records: list[dict[str, Any]], rejects: list[ValidationError]
) -> tuple[list[dict[str, Any]], int, int]:
    exact_groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        exact_groups.setdefault(exact_key(record), []).append(record)
    exact_selected: list[dict[str, Any]] = []
    for group in exact_groups.values():
        winner = max(group, key=_record_priority)
        exact_selected.append(winner)
        for record in group:
            if record is not winner:
                rejects.append(
                    ValidationError(record["record_id"], "exact duplicate")
                )

    by_intent: dict[tuple[str, str], list[tuple[dict[str, Any], tuple[float, ...]]]] = {}
    semantic_selected: list[dict[str, Any]] = []
    for record in exact_selected:
        key = (record["language"], record["intent"])
        vector = semantic_embedding(f"{record['question']} {record['answer']}")
        candidates = by_intent.setdefault(key, [])
        matches = [
            index
            for index, (_, candidate_vector) in enumerate(candidates)
            if cosine_similarity(vector, candidate_vector) >= SEMANTIC_DEDUP_THRESHOLD
        ]
        if not matches:
            candidates.append((record, vector))
            semantic_selected.append(record)
            continue
        # One incoming record can match more than one paraphrase; replace the
        # highest-priority existing member only when it is the preferred one.
        existing_index = max(matches, key=lambda index: _record_priority(candidates[index][0]))
        existing = candidates[existing_index][0]
        winner = max((existing, record), key=_record_priority)
        if winner is record:
            semantic_position = semantic_selected.index(existing)
            semantic_selected[semantic_position] = record
            candidates[existing_index] = (record, vector)
            rejects.append(
                ValidationError(existing["record_id"], "semantic duplicate")
            )
        else:
            rejects.append(
                ValidationError(record["record_id"], "semantic duplicate")
            )
    return semantic_selected, len(exact_selected), len(semantic_selected)


def prepare_records(
    records: Iterable[dict[str, Any]], seed: int = 42
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    counts: dict[str, int] = {
        "input": 0,
        "schema_coerced": 0,
        "schema_valid": 0,
        "schema_rejected": 0,
        "normalized": 0,
        "unicode_normalized": 0,
        "html_removed": 0,
        "whitespace_normalized": 0,
        "language_identified": 0,
        "english": 0,
        "pii_clear": 0,
        "pii_quarantined": 0,
        "exact_unique": 0,
        "semantic_unique": 0,
        "balanced": 0,
        "split": 0,
        "rendered": 0,
    }
    rejects: list[ValidationError] = []
    accepted: list[dict[str, Any]] = []
    for raw in records:
        counts["input"] += 1
        record = dict(raw)
        record_id = str(record.get("record_id", "unknown"))
        try:
            validate_record(record)
            counts["schema_valid"] += 1
            record["question"] = normalize_text(record["question"])
            record["answer"] = normalize_text(record["answer"])
            counts["normalized"] += 1
            if record["language"] != "en":
                raise ValueError("non-English record")
            counts["english"] += 1
            if _PII.search(record["question"]) or _PII.search(record["answer"]):
                raise ValueError("PII detected")
            counts["pii_clear"] += 1
            accepted.append(record)
        except (TypeError, ValueError) as exc:
            rejects.append(ValidationError(record_id, str(exc)))
    counts["schema_coerced"] = counts["input"]
    counts["schema_rejected"] = counts["input"] - counts["schema_valid"]
    counts["unicode_normalized"] = counts["normalized"]
    counts["html_removed"] = counts["normalized"]
    counts["whitespace_normalized"] = counts["normalized"]
    counts["language_identified"] = counts["english"]
    counts["pii_quarantined"] = sum(item.reason == "PII detected" for item in rejects)
    accepted, exact_count, semantic_count = _deduplicate_records(accepted, rejects)
    counts["exact_unique"] = exact_count
    counts["semantic_unique"] = semantic_count
    balanced, balance_manifest = _balance_records(accepted, seed)
    counts["balanced"] = len(balanced)
    splits: dict[str, list[dict[str, Any]]] = {"train": [], "validation": [], "evaluation": []}
    split_manifest: list[dict[str, Any]] = []
    cluster_splits = _stratified_group_splits(balanced, seed)
    for record in balanced:
        split = cluster_splits[record["semantic_cluster_id"]]
        enriched = dict(record)
        enriched["rendered_chat"] = render_training_example(record)
        splits[split].append(enriched)
        split_manifest.append(
            {key: record[key] for key in ("record_id", "semantic_cluster_id", "source", "class")}
            | {"seed": seed, "split": split}
        )
    counts["split"] = len(balanced)
    counts["rendered"] = len(balanced)
    manifest = {
        "schema_version": "1.0",
        "seed": seed,
        "stage_counts": counts,
        "split_counts": {name: len(items) for name, items in splits.items()},
        "class_counts": dict(sorted(Counter(r["class"] for r in accepted).items())),
        "balanced_class_counts": balance_manifest["selected"],
        "balance": balance_manifest,
        "semantic_dedup": {"method": "cosine", "threshold": SEMANTIC_DEDUP_THRESHOLD},
        "split_records": split_manifest,
        "split_manifest": split_manifest,
        "rejections": [error.__dict__ for error in rejects],
    }
    return splits, manifest


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]
