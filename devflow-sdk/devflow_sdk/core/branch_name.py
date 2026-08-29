import re

HOTFIX_KEYWORDS = {"hotfix", "urgent"}
FIX_KEYWORDS = {"bug", "defect", "fix"}
DOCS_KEYWORDS = {"docs", "documentation"}
CHORE_KEYWORDS = {"chore", "maintenance"}

VALID_TYPES = ("feat", "fix", "hotfix", "chore", "docs")

BRANCH_RE = re.compile(
    r'^(?P<type>feat|fix|hotfix|chore|docs)/'
    r'(?:(?P<wt>wt)/)?'
    r'(?:gh(?P<gh_id>[0-9]+)|jira-(?P<jira_id>[A-Za-z]+-[0-9]+))'
    r'-(?P<slug>.+)$'
)


def infer_type(issue):
    """Infer branch type from JIRA issuetype / GitHub labels.

    Precedence: hotfix > fix > docs > chore > feat.
    """
    itype = (issue.get("issuetype") or "").lower()
    labels = {l.lower() for l in (issue.get("labels") or [])}
    tags = labels | ({itype} if itype else set())

    if tags & HOTFIX_KEYWORDS:
        return "hotfix"
    if tags & FIX_KEYWORDS:
        return "fix"
    if tags & DOCS_KEYWORDS:
        return "docs"
    if tags & CHORE_KEYWORDS:
        return "chore"
    return "feat"


def slugify(text, max_words=6):
    text = re.sub(r"[-_]", " ", text.lower())
    words = re.sub(r"[^a-z0-9 ]", "", text).split()
    return "-".join(words[:max_words])


def _encode_source_ref(issue):
    if issue["source"] == "jira":
        return f"jira-{issue['id']}"
    return f"gh{issue['id']}"


def make_branch(issue, override=None, worktree=False):
    """Build a branch name: <type>/[wt/]<source_ref>-<slug>."""
    branch_type = override or infer_type(issue)
    source_ref = _encode_source_ref(issue)
    slug = slugify(issue["title"])
    wt_segment = "wt/" if worktree else ""
    return f"{branch_type}/{wt_segment}{source_ref}-{slug}"


def parse_branch(branch):
    """Parse a branch name built by make_branch().

    Returns {"type", "is_worktree", "source", "id", "slug"}, or None if
    branch doesn't match the expected format (old-format or manually
    created branches degrade gracefully to None).
    """
    if not branch:
        return None
    match = BRANCH_RE.match(branch)
    if not match:
        return None

    if match.group("gh_id") is not None:
        source, issue_id = "github", match.group("gh_id")
    else:
        source, issue_id = "jira", match.group("jira_id").upper()

    return {
        "type": match.group("type"),
        "is_worktree": match.group("wt") == "wt",
        "source": source,
        "id": issue_id,
        "slug": match.group("slug"),
    }
