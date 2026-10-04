"""Offline tests for exact-head owner review authorization."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.check_shared_review import evaluate_shared_review


ROOT = Path(__file__).resolve().parents[1]
HEAD = "a" * 40
OTHER = "b" * 40


def review(login="jrile018", state="APPROVED", commit=HEAD,
           submitted="2026-10-04T12:00:00Z"):
    return {"user": {"login": login}, "state": state, "commit_id": commit,
            "submitted_at": submitted}


def comment(login="jrile018", body=f"approve-shared-change: {HEAD}",
            created="2026-10-04T13:00:00Z"):
    return {"user": {"login": login}, "body": body, "created_at": created}


class SharedReviewTests(unittest.TestCase):
    def test_exact_head_owner_approval_passes_flat_or_paginated(self):
        item = review(login="JRILE018")
        self.assertEqual(evaluate_shared_review("jrile018", HEAD, [item]),
                         {"ok": True, "errors": []})
        self.assertEqual(evaluate_shared_review("jrile018", HEAD, [[], [item]]),
                         {"ok": True, "errors": []})

    def test_later_comment_does_not_erase_approval(self):
        reviews = [review(), review(state="COMMENTED", submitted="2026-10-04T13:00:00Z")]
        self.assertTrue(evaluate_shared_review("jrile018", HEAD, reviews)["ok"])

    def test_latest_substantive_owner_review_controls_even_if_pages_out_of_order(self):
        cases = [
            [review(state="CHANGES_REQUESTED", submitted="2026-10-04T13:00:00Z"),
             review(submitted="2026-10-04T12:00:00Z")],
            [review(state="DISMISSED", submitted="2026-10-04T13:00:00Z"),
             review(submitted="2026-10-04T12:00:00Z")],
            [review(commit=OTHER, submitted="2026-10-04T13:00:00Z"),
             review(submitted="2026-10-04T12:00:00Z")],
            [review(state="CHANGES_REQUESTED", commit=OTHER,
                    submitted="2026-10-04T13:00:00Z"),
             review(submitted="2026-10-04T12:00:00Z")],
        ]
        for reviews in cases:
            with self.subTest(state=reviews[0]["state"], commit=reviews[0]["commit_id"]):
                self.assertFalse(evaluate_shared_review("jrile018", HEAD, reviews)["ok"])

    def test_other_user_and_stale_approvals_do_not_authorize(self):
        for reviews in ([review(login="another-user")], [review(commit=OTHER)], []):
            with self.subTest(reviews=reviews):
                self.assertFalse(evaluate_shared_review("jrile018", HEAD, reviews)["ok"])

    def test_newer_owner_approval_on_head_overrides_old_rejection(self):
        reviews = [review(state="CHANGES_REQUESTED", commit=OTHER),
                   review(submitted="2026-10-04T13:00:00Z")]
        self.assertTrue(evaluate_shared_review("jrile018", HEAD, reviews)["ok"])

    def test_exact_owner_attestation_comment_authorizes_head(self):
        result = evaluate_shared_review("jrile018", HEAD, [[]], [[comment()]])
        self.assertEqual(result, {"ok": True, "errors": []})

    def test_generic_stale_or_other_author_comment_does_not_authorize(self):
        cases = [comment(body="LGTM"),
                 comment(body=f"approve-shared-change: {OTHER}"),
                 comment(login="someone-else"),
                 comment(body=f"approve-shared-change: {HEAD} extra")]
        for item in cases:
            with self.subTest(comment=item):
                self.assertFalse(evaluate_shared_review("jrile018", HEAD, [], [item])["ok"])

    def test_latest_owner_decision_can_revoke_or_restore_attestation(self):
        old_attestation = comment(created="2026-10-04T11:00:00Z")
        rejection = review(state="CHANGES_REQUESTED", submitted="2026-10-04T12:00:00Z")
        self.assertFalse(evaluate_shared_review("jrile018", HEAD, [rejection],
                                                [old_attestation])["ok"])
        new_attestation = comment(created="2026-10-04T13:00:00Z")
        self.assertTrue(evaluate_shared_review("jrile018", HEAD, [rejection],
                                               [new_attestation])["ok"])

    def test_equal_timestamp_conflicting_owner_decisions_fail_closed(self):
        instant = "2026-10-04T13:00:00Z"
        cases = [
            ([review(state="CHANGES_REQUESTED", submitted=instant)],
             [comment(created=instant)]),
            ([review(submitted=instant)],
             [comment(body=f"approve-shared-change: {OTHER}", created=instant)]),
        ]
        for reviews, comments in cases:
            with self.subTest(reviews=reviews, comments=comments):
                result = evaluate_shared_review("jrile018", HEAD, reviews, comments)
                self.assertFalse(result["ok"])
                self.assertTrue(result["errors"])
        self.assertTrue(evaluate_shared_review("jrile018", HEAD,
                        [review(submitted=instant)], [comment(created=instant)])["ok"])

    def test_malformed_inputs_fail_closed(self):
        cases = [
            ("", HEAD, [review()]),
            ("jrile018", "short", [review()]),
            ("jrile018", HEAD, {"reviews": [review()]}),
            ("jrile018", HEAD, [[review()], {"bad": "page"}]),
            ("jrile018", HEAD, [{"state": "APPROVED"}]),
            ("jrile018", HEAD, [review(submitted="not-a-date")]),
            ("jrile018", HEAD, [review(commit="not-a-sha")]),
        ]
        for owner, head, reviews in cases:
            with self.subTest(owner=owner, head=head, reviews=reviews):
                result = evaluate_shared_review(owner, head, reviews)
                self.assertFalse(result["ok"])
                self.assertTrue(result["errors"])

    def test_cli_reads_slurped_pages_and_returns_json_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviews.json"
            path.write_text(json.dumps([[review()]]), encoding="utf-8")
            command = [sys.executable, str(ROOT / "scripts" / "check_shared_review.py"),
                       "--owner", "jrile018", "--head", HEAD, "--reviews", str(path)]
            approved = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(approved.returncode, 0, approved.stderr)
            self.assertEqual(json.loads(approved.stdout), {"ok": True, "errors": []})
            path.write_text("{not json", encoding="utf-8")
            malformed = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(malformed.returncode, 1, malformed.stderr)
            self.assertFalse(json.loads(malformed.stdout)["ok"])

    def test_cli_accepts_exact_owner_attestation_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            reviews = Path(directory) / "reviews.json"
            comments = Path(directory) / "comments.json"
            reviews.write_text("[[]]", encoding="utf-8")
            comments.write_text(json.dumps([[comment()]]), encoding="utf-8")
            command = [sys.executable, str(ROOT / "scripts" / "check_shared_review.py"),
                       "--owner", "jrile018", "--head", HEAD,
                       "--reviews", str(reviews), "--comments", str(comments)]
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout), {"ok": True, "errors": []})


if __name__ == "__main__":
    unittest.main()
