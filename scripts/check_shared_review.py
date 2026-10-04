"""Authorize shared PRs from offline owner review and attestation JSON.

Accepts flat arrays or ``gh api --paginate --slurp`` arrays of pages.
The latest substantive owner decision must approve the exact candidate head.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re


SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
STATES = frozenset({"APPROVED", "CHANGES_REQUESTED", "DISMISSED", "COMMENTED", "PENDING"})
SUBSTANTIVE = frozenset({"APPROVED", "CHANGES_REQUESTED", "DISMISSED"})
ATTESTATION = re.compile(r"approve-shared-change: ([0-9a-fA-F]{40})\Z")


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO 8601 timestamp")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO 8601 timestamp") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError(f"{label} must include a UTC offset")
    return stamp.astimezone(timezone.utc)


def _flatten(value: object, label: str) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    if all(isinstance(item, dict) for item in value):
        return value
    if all(isinstance(page, list) for page in value):
        flat = []
        for page in value:
            if not all(isinstance(item, dict) for item in page):
                raise ValueError(f"{label} pages must contain objects")
            flat.extend(page)
        return flat
    raise ValueError(f"{label} must be flat objects or arrays of pages")


def _login(item: dict, label: str, index: int) -> str:
    user = item.get("user")
    login = user.get("login") if isinstance(user, dict) else None
    if not isinstance(login, str) or not login.strip():
        raise ValueError(f"{label} {index} has no user.login")
    return login.strip()


def evaluate_shared_review(owner: str, head: str, reviews: object,
                           comments: object = None) -> dict:
    """Return JSON-compatible ``{ok, errors}`` for the exact head."""
    errors = []
    if not isinstance(owner, str) or not owner.strip():
        errors.append("repository owner must be nonempty")
    if not isinstance(head, str) or not SHA.fullmatch(head):
        errors.append("head must be a 40-character Git commit SHA")
    try:
        review_items = _flatten(reviews, "reviews")
        comment_items = _flatten([] if comments is None else comments, "comments")
    except ValueError as exc:
        errors.append(str(exc))
        review_items, comment_items = [], []
    if errors:
        return {"ok": False, "errors": errors}

    owner_name = owner.strip().casefold()
    decisions = []
    for index, item in enumerate(review_items):
        try:
            login = _login(item, "review", index)
            state = item.get("state")
            if not isinstance(state, str) or state not in STATES:
                raise ValueError(f"review {index} has an unsupported state")
            if state not in SUBSTANTIVE:
                continue
            commit = item.get("commit_id")
            if not isinstance(commit, str) or not SHA.fullmatch(commit):
                raise ValueError(f"review {index} has no valid commit_id")
            stamp = _timestamp(item.get("submitted_at"), "submitted_at")
            if login.casefold() == owner_name:
                decisions.append((stamp, index, state == "APPROVED", commit, state))
        except ValueError as exc:
            errors.append(str(exc))

    offset = len(review_items)
    for index, item in enumerate(comment_items):
        try:
            login = _login(item, "comment", index)
            body = item.get("body")
            if not isinstance(body, str):
                raise ValueError(f"comment {index} has no body")
            match = ATTESTATION.fullmatch(body.strip())
            if match is None:
                continue  # Ordinary discussion does not erase an authorization.
            stamp = _timestamp(item.get("created_at"), "created_at")
            if login.casefold() == owner_name:
                decisions.append((stamp, offset + index, True, match.group(1), "ATTESTED"))
        except ValueError as exc:
            errors.append(str(exc))
    if errors:
        return {"ok": False, "errors": errors}
    if not decisions:
        return {"ok": False, "errors": ["repository owner has no substantive review or exact attestation"]}
    latest_stamp = max(decision[0] for decision in decisions)
    latest = [decision for decision in decisions if decision[0] == latest_stamp]
    if len({(decision[2], decision[3].casefold()) for decision in latest}) != 1:
        return {"ok": False, "errors": ["conflicting repository-owner decisions share the latest timestamp"]}
    _, _, approved, commit, state = latest[0]
    if not approved:
        return {"ok": False, "errors": [f"latest repository-owner decision is {state}"]}
    if commit.casefold() != head.casefold():
        return {"ok": False, "errors": ["latest repository-owner authorization is for a different head commit"]}
    return {"ok": True, "errors": []}


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print(json.dumps({"ok": False, "errors": [message]}, sort_keys=True))
        raise SystemExit(1)


def main(argv=None) -> int:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--comments", type=Path)
    args = parser.parse_args(argv)
    try:
        reviews = json.loads(args.reviews.read_text(encoding="utf-8"))
        comments = json.loads(args.comments.read_text(encoding="utf-8")) if args.comments else []
        result = evaluate_shared_review(args.owner, args.head, reviews, comments)
    except (OSError, UnicodeError, ValueError) as exc:
        result = {"ok": False, "errors": [f"cannot read review inputs: {exc}"]}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
