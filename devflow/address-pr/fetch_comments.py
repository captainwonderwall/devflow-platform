#!/usr/bin/env python3
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Comment:
    id: str                       # REST numeric ID as string
    kind: str                     # "review_thread" | "pr_comment"
    author: str
    is_bot: bool
    body: str
    file: Optional[str]
    line: Optional[int]
    url: str
    thread_node_id: Optional[str] # GraphQL node ID — for resolveReviewThread
    verdict: Optional[str] = None # "VALID" | "INVALID"
    reason: Optional[str] = None
    reply_text: Optional[str] = None


def build_is_bot(username: str) -> bool:
    return username.endswith("[bot]")


def _author_is_bot(author: dict) -> bool:
    """Detect bots from the GraphQL author node.

    Prefer __typename=="Bot" when present (covers accounts like
    copilot-pull-request-reviewer that don't use the [bot] suffix), fall back
    to the login-suffix heuristic for older queries that omit __typename.
    """
    typename = author.get("__typename")
    if typename is not None:
        return typename == "Bot"
    return build_is_bot(author["login"])


def filter_unresolved_pr_comments(comments: list, pr_author: str) -> list:
    author_comments = [c for c in comments if c["user"]["login"] == pr_author]
    if not author_comments:
        return [c for c in comments if c["user"]["login"] != pr_author]
    last_author_ts = max(c["created_at"] for c in author_comments)
    return [
        c for c in comments
        if c["user"]["login"] != pr_author
        and c["created_at"] > last_author_ts
    ]


def parse_review_threads(threads: list) -> List[Comment]:
    result = []
    for t in threads:
        if t["isResolved"]:
            continue
        nodes = t["comments"]["nodes"]
        if not nodes:
            continue
        node = nodes[0]
        result.append(Comment(
            id=str(node["databaseId"]),
            kind="review_thread",
            author=node["author"]["login"],
            is_bot=_author_is_bot(node["author"]),
            body=node["body"],
            file=node["path"],
            line=node["line"],
            url=node["url"],
            thread_node_id=t["id"],
        ))
    return result


def build_pr_comments(raw: list, pr_author: str) -> List[Comment]:
    unresolved = filter_unresolved_pr_comments(raw, pr_author)
    return [
        Comment(
            id=str(c["id"]),
            kind="pr_comment",
            author=c["user"]["login"],
            is_bot=(c["user"].get("type") == "Bot"
                    or build_is_bot(c["user"]["login"])),
            body=c["body"],
            file=None,
            line=None,
            url=c["html_url"],
            thread_node_id=None,
        )
        for c in unresolved
    ]


def _run_gh(args: list) -> dict:
    result = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: gh {' '.join(args[:2])} failed: {result.stderr.strip()}",
              file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def get_repo_info() -> tuple:
    data = _run_gh(["repo", "view", "--json", "owner,name"])
    return data["owner"]["login"], data["name"]


def get_pr_info() -> dict:
    result = subprocess.run(
        ["gh", "pr", "view", "--json",
         "number,title,author,headRefName,baseRefName,body"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("ERROR: no open PR on the current branch", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def _fetch_review_threads_raw(owner: str, repo: str, pr_number: int) -> list:
    query = (
        "query($owner:String!,$repo:String!,$number:Int!){"
        "repository(owner:$owner,name:$repo){"
        "pullRequest(number:$number){"
        "reviewThreads(first:100){nodes{"
        "id isResolved comments(first:1){nodes{"
        "databaseId author{login __typename} body path line url"
        "}}}}}}}"
    )
    data = _run_gh([
        "api", "graphql",
        "-f", f"query={query}",
        "-F", f"owner={owner}",
        "-F", f"repo={repo}",
        "-F", f"number={pr_number}",
    ])
    return data["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]


def _fetch_issue_comments_raw(owner: str, repo: str, pr_number: int) -> list:
    return _run_gh(["api", f"/repos/{owner}/{repo}/issues/{pr_number}/comments?per_page=100"])


def collect() -> dict:
    owner, repo = get_repo_info()
    pr = get_pr_info()
    pr_number = pr["number"]
    pr_author = pr["author"]["login"]

    threads_raw = _fetch_review_threads_raw(owner, repo, pr_number)
    issue_raw = _fetch_issue_comments_raw(owner, repo, pr_number)

    review_comments = parse_review_threads(threads_raw)
    pr_comments = build_pr_comments(issue_raw, pr_author)
    all_comments = review_comments + pr_comments

    return {
        "owner": owner,
        "repo": repo,
        "pr_number": pr_number,
        "pr_title": pr["title"],
        "pr_branch": pr["headRefName"],
        "pr_base": pr["baseRefName"],
        "pr_description": pr.get("body") or "",
        "pr_author": pr_author,
        "comments": all_comments,
    }
