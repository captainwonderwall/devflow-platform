#!/usr/bin/env python3
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fetch_comments import (
    build_is_bot,
    filter_unresolved_pr_comments,
    parse_review_threads,
    build_pr_comments,
    Comment,
)


class TestBuildIsBot(unittest.TestCase):
    def test_dependabot_is_bot(self):
        self.assertTrue(build_is_bot("dependabot[bot]"))

    def test_github_actions_is_bot(self):
        self.assertTrue(build_is_bot("github-actions[bot]"))

    def test_human_is_not_bot(self):
        self.assertFalse(build_is_bot("alice"))

    def test_empty_is_not_bot(self):
        self.assertFalse(build_is_bot(""))


class TestFilterUnresolvedPrComments(unittest.TestCase):
    def test_all_unresolved_when_author_never_commented(self):
        comments = [
            {"id": 1, "user": {"login": "alice"}, "body": "fix this",
             "created_at": "2024-01-02T00:00:00Z", "html_url": "http://x"},
        ]
        result = filter_unresolved_pr_comments(comments, pr_author="phoang")
        self.assertEqual(len(result), 1)

    def test_comments_after_author_reply_are_unresolved(self):
        comments = [
            {"id": 1, "user": {"login": "alice"}, "body": "fix",
             "created_at": "2024-01-01T00:00:00Z", "html_url": "http://a"},
            {"id": 2, "user": {"login": "phoang"}, "body": "done",
             "created_at": "2024-01-02T00:00:00Z", "html_url": "http://b"},
            {"id": 3, "user": {"login": "bob"}, "body": "also this",
             "created_at": "2024-01-03T00:00:00Z", "html_url": "http://c"},
        ]
        result = filter_unresolved_pr_comments(comments, pr_author="phoang")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], 3)

    def test_comments_before_author_reply_are_resolved(self):
        comments = [
            {"id": 1, "user": {"login": "alice"}, "body": "fix",
             "created_at": "2024-01-01T00:00:00Z", "html_url": "http://a"},
            {"id": 2, "user": {"login": "phoang"}, "body": "done",
             "created_at": "2024-01-05T00:00:00Z", "html_url": "http://b"},
        ]
        result = filter_unresolved_pr_comments(comments, pr_author="phoang")
        self.assertEqual(result, [])

    def test_author_own_comments_always_excluded(self):
        comments = [
            {"id": 1, "user": {"login": "phoang"}, "body": "update",
             "created_at": "2024-01-01T00:00:00Z", "html_url": "http://a"},
        ]
        result = filter_unresolved_pr_comments(comments, pr_author="phoang")
        self.assertEqual(result, [])


class TestParseReviewThreads(unittest.TestCase):
    def _thread(self, thread_id, is_resolved, db_id, author, body,
                path="a.py", line=1):
        return {
            "id": thread_id,
            "isResolved": is_resolved,
            "comments": {"nodes": [{
                "databaseId": db_id,
                "author": {"login": author},
                "body": body,
                "path": path,
                "line": line,
                "url": "http://x",
            }]},
        }

    def test_resolved_thread_excluded(self):
        threads = [self._thread("PRRT_1", True, 10, "alice", "fix")]
        self.assertEqual(parse_review_threads(threads), [])

    def test_unresolved_thread_included(self):
        threads = [self._thread("PRRT_2", False, 20, "bob", "change this",
                                path="b.py", line=10)]
        result = parse_review_threads(threads)
        self.assertEqual(len(result), 1)
        c = result[0]
        self.assertEqual(c.id, "20")
        self.assertEqual(c.kind, "review_thread")
        self.assertEqual(c.author, "bob")
        self.assertEqual(c.thread_node_id, "PRRT_2")
        self.assertEqual(c.file, "b.py")
        self.assertEqual(c.line, 10)
        self.assertFalse(c.is_bot)

    def test_bot_author_flagged(self):
        threads = [self._thread("PRRT_3", False, 30, "dependabot[bot]",
                                "upgrade dep")]
        result = parse_review_threads(threads)
        self.assertTrue(result[0].is_bot)

    def test_empty_thread_nodes_skipped(self):
        threads = [{"id": "PRRT_4", "isResolved": False,
                    "comments": {"nodes": []}}]
        self.assertEqual(parse_review_threads(threads), [])


class TestBuildPrComments(unittest.TestCase):
    def _raw(self, comment_id, login, body, created_at):
        return {
            "id": comment_id,
            "user": {"login": login},
            "body": body,
            "created_at": created_at,
            "html_url": "http://x",
        }

    def test_converts_raw_to_comment(self):
        raw = [self._raw(99, "carol", "nit comment", "2024-01-03T00:00:00Z")]
        result = build_pr_comments(raw, pr_author="phoang")
        self.assertEqual(len(result), 1)
        c = result[0]
        self.assertEqual(c.id, "99")
        self.assertEqual(c.kind, "pr_comment")
        self.assertEqual(c.author, "carol")
        self.assertIsNone(c.file)
        self.assertIsNone(c.line)
        self.assertIsNone(c.thread_node_id)

    def test_bot_author_flagged(self):
        raw = [self._raw(88, "github-actions[bot]", "lint fail", "2024-01-01T00:00:00Z")]
        result = build_pr_comments(raw, pr_author="phoang")
        self.assertTrue(result[0].is_bot)


if __name__ == "__main__":
    unittest.main()
