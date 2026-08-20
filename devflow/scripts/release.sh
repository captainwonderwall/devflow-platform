#!/bin/bash
set -euo pipefail
MONOREPO_MODE="${MONOREPO_MODE:-0}"
RELEASE_AUTO_CONFIRM="${RELEASE_AUTO_CONFIRM:-0}"

usage() {
    echo "Usage: $0 [<tool> [version-or-tap-path] [tap-repo-path]]"
    echo "  (no args)         Release all tools with unreleased changes since their last tag."
    echo "  tap-repo-path     (as sole arg) Same as above, but using a custom tap checkout."
    echo "  tool              Tool name (e.g. draft-pr, address-pr)"
    echo "  version           Semver override (e.g. v2.0.0). If omitted, computed from commits."
    echo "  tap-repo-path     Path to homebrew-devflow checkout (default: ../homebrew-devflow)"
    echo ""
    echo "  Arg 2 is treated as a version if it starts with 'v', otherwise as tap-repo-path."
    exit 1
}

# Ensure vendor/ is in sync with shared/requirements.txt.
# If anything is out of date (missing wheels, requirements changed, untracked
# wheels), runs update-vendor.sh then commits the result automatically.
ensure_vendor_up_to_date() {
    [[ "$MONOREPO_MODE" == "1" ]] && return
    local repo_root vendor_dir
    repo_root="$(git rev-parse --show-toplevel)"
    vendor_dir="$repo_root/devflow/vendor"

    if [[ -d "$vendor_dir" ]] && \
       [[ -n "$(ls "$vendor_dir"/*.whl 2>/dev/null)" ]] && \
       [[ -z "$(git ls-files --others --exclude-standard -- devflow/vendor/ 2>/dev/null)" ]] && \
       [[ -z "$(git ls-files --deleted -- devflow/vendor/ 2>/dev/null)" ]]; then
        return
    fi

    echo "vendor/ changed — refreshing vendor/..."
    bash "$repo_root/devflow/scripts/update-vendor.sh"
    echo ""
    git add devflow/vendor/
    if ! git diff --cached --quiet -- devflow/vendor/; then
        git commit --only -m "chore: update vendor wheels" -- devflow/vendor/
        echo "Committed vendor/."
        echo ""
    fi
}

# Verify a formula references vendor/ so wheels are actually installed during brew install.
check_formula_has_vendor_install() {
    local formula="$1"
    if ! grep -qE "vendor|find.links|\.whl" "$formula" 2>/dev/null; then
        echo "ERROR: $formula does not include vendor wheel installation logic." >&2
        echo "  Update the formula's install block to install from vendor/*.whl before releasing." >&2
        exit 1
    fi
}

# Returns true if the tap_repo path lives inside this git repo (subtree mode).
is_subtree() {
    local tap_abs tap_top repo_top
    tap_abs=$(cd "$1" 2>/dev/null && pwd) || return 1
    tap_top=$(git -C "$tap_abs" rev-parse --show-toplevel 2>/dev/null) || return 1
    repo_top=$(git rev-parse --show-toplevel 2>/dev/null) || return 1
    [[ "$tap_top" == "$repo_top" ]]
}

# Discover tool names from the tap repo's Formula/*.rb files.
discover_tools() {
    local tap_repo="$1"
    local formula
    for formula in "$tap_repo"/Formula/*.rb; do
        [[ -e "$formula" ]] || continue
        basename "$formula" .rb
    done
}

compute_next_version() {
    local tool="$1"
    local quiet="${2:-}"
    # Find latest namespaced tag for this tool
    local last_tag
    last_tag=$(git tag --list "$tool/v*" | sort -V | tail -1)

    # Fall back to latest un-namespaced tag if no namespaced tags exist
    # (the `|| true` guards against `set -e`/pipefail exiting the script when
    # grep finds nothing to filter, e.g. no tags exist yet)
    if [[ -z "$last_tag" ]]; then
        last_tag=$(git tag --list "v*" | grep -v '/' | sort -V | tail -1) || true
    fi

    local git_range
    if [[ -z "$last_tag" ]]; then
        # No prior tag — scan all commits touching this tool
        git_range="HEAD"
    else
        git_range="${last_tag}..HEAD"
    fi

    # Collect commit subjects touching the tool directory or the shared library
    # (all tools depend on shared/, so changes there affect every release)
    local commits
    if [[ "$tool" == "devflow" ]]; then
        commits=$(git log "$git_range" --format="%s%n%b" 2>/dev/null)
    else
        commits=$(git log "$git_range" --format="%s%n%b" -- "$tool/" "shared/" 2>/dev/null)
    fi

    if [[ -z "$commits" ]]; then
        if [[ "$quiet" == "quiet" ]]; then
            return 1
        fi
        echo "ERROR: no commits touching $tool/ or shared/ since ${last_tag:-the beginning}. Nothing to release." >&2
        exit 1
    fi

    # Determine bump level
    local bump="patch"
    while IFS= read -r line; do
        if [[ "$line" =~ ^[a-z]+(\(.+\))?!: ]] || [[ "$line" == "BREAKING CHANGE"* ]] || [[ "$line" == "BREAKING-CHANGE"* ]]; then
            bump="major"
            break
        elif [[ "$line" =~ ^feat(\(.+\))?: ]] && [[ "$bump" != "major" ]]; then
            bump="minor"
        fi
    done <<< "$commits"

    # Parse last tag version or default to 0.0.0
    local base="${last_tag#"$tool/"}"   # strip "tool/" prefix → "v1.2.0"
    base="${base#v}"                    # strip "v" → "1.2.0"
    local major minor patch
    IFS='.' read -r major minor patch <<< "${base:-0.0.0}"

    case "$bump" in
        major) major=$((major + 1)); minor=0; patch=0 ;;
        minor) minor=$((minor + 1)); patch=0 ;;
        patch) patch=$((patch + 1)) ;;
    esac

    echo "v${major}.${minor}.${patch}"
}

# Release every tool that has unreleased changes since its last tag.
# Shows one combined confirmation prompt covering all affected tools.
release_all() {
    local tap_repo="$1"

    if ! git -C "$tap_repo" rev-parse --git-dir >/dev/null 2>&1; then
        echo "ERROR: $tap_repo is not a git checkout" >&2
        exit 1
    fi

    local tools=()
    local t
    while IFS= read -r t; do
        [[ -n "$t" ]] && tools+=("$t")
    done < <(discover_tools "$tap_repo")

    if [[ ${#tools[@]} -eq 0 ]]; then
        echo "ERROR: no formulas found in $tap_repo/Formula" >&2
        exit 1
    fi

    local revision short_rev
    revision="$(git rev-list -n 1 HEAD)"
    short_rev="${revision:0:7}"

    local affected_tools=() affected_versions=() affected_tags=() affected_sources=()
    local tool version last_tag git_range commit_count formula tag

    for tool in "${tools[@]}"; do
        if ! version=$(compute_next_version "$tool" quiet); then
            continue
        fi

        formula="$tap_repo/Formula/$tool.rb"
        if [[ ! -f "$formula" ]]; then
            echo "WARNING: formula not found at $formula — skipping $tool." >&2
            continue
        fi

        check_formula_has_vendor_install "$formula"

        tag="$tool/$version"
        if git rev-parse "refs/tags/$tag" >/dev/null 2>&1; then
            echo "WARNING: tag $tag already exists — skipping $tool." >&2
            continue
        fi

        last_tag=$(git tag --list "$tool/v*" | sort -V | tail -1)
        if [[ -z "$last_tag" ]]; then
            last_tag=$(git tag --list "v*" | grep -v '/' | sort -V | tail -1) || true
        fi
        git_range="${last_tag:+${last_tag}..}HEAD"
        if [[ "$tool" == "devflow" ]]; then
            commit_count=$(git log "$git_range" --oneline 2>/dev/null | wc -l | tr -d ' ')
        else
            commit_count=$(git log "$git_range" --oneline -- "$tool/" "shared/" 2>/dev/null | wc -l | tr -d ' ')
        fi

        affected_tools+=("$tool")
        affected_versions+=("$version")
        affected_tags+=("$tag")
        affected_sources+=("Computed from ${commit_count} commit(s) since ${last_tag:-the beginning}")
    done

    if [[ ${#affected_tools[@]} -eq 0 ]]; then
        echo "No tools have unreleased changes. Nothing to do."
        exit 0
    fi

    # Warn on uncommitted changes (once, applies to every tag)
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo "WARNING: you have uncommitted changes — the tags will point at the current HEAD regardless." >&2
        echo ""
    fi

    # Fail fast if the tap repo has any uncommitted or staged changes — mutating
    # formulas in a dirty tree risks clobbering local work or smuggling unrelated
    # staged hunks into the release commit.
    if ! is_subtree "$tap_repo" && [[ "$MONOREPO_MODE" != "1" ]]; then
        if ! git -C "$tap_repo" diff --quiet || ! git -C "$tap_repo" diff --cached --quiet; then
            echo "ERROR: tap repo '$tap_repo' has uncommitted changes. Please commit or stash them before releasing." >&2
            exit 1
        fi
    fi

    # Update all affected formulas (temporarily, to show what the diffs would be)
    local i
    for i in "${!affected_tools[@]}"; do
        sed -i '' "s|tag:.*|tag:      \"${affected_tags[$i]}\",|" "$tap_repo/Formula/${affected_tools[$i]}.rb"
        sed -i '' "s|revision:.*|revision: \"$revision\"|" "$tap_repo/Formula/${affected_tools[$i]}.rb"
    done

    # Install cleanup trap immediately after sed mutates the formulas
    _revert_all_formulas() {
        local rt
        for rt in "${affected_tools[@]}"; do
            git -C "$tap_repo" checkout "Formula/$rt.rb" 2>/dev/null
        done
    }
    trap _revert_all_formulas EXIT

    # Ensure every formula actually changed before we commit to pushing any tag
    for tool in "${affected_tools[@]}"; do
        if git -C "$tap_repo" diff --quiet "Formula/$tool.rb"; then
            echo "ERROR: formula for $tool was not modified by sed (tag/revision lines may not match expected format)." >&2
            exit 1
        fi
    done

    # Show combined summary and diffs
    echo "About to release ${#affected_tools[@]} tool(s):"
    echo ""
    for i in "${!affected_tools[@]}"; do
        echo "  ${affected_tools[$i]} ${affected_versions[$i]}"
        echo "    Tag:      ${affected_tags[$i]} → $short_rev"
        echo "    Version:  ${affected_sources[$i]}"
    done
    echo ""
    echo "  Push to:  origin (devflow-platform)"
    if [[ "$MONOREPO_MODE" == "1" ]]; then
        echo "  Tap:      managed by outer release script"
    elif is_subtree "$tap_repo"; then
        echo "  Tap:      $tap_repo (subtree)"
    else
        echo "  Tap repo: $tap_repo"
    fi
    echo ""
    echo "Formula diff:"
    for tool in "${affected_tools[@]}"; do
        git -C "$tap_repo" diff "Formula/$tool.rb"
    done
    echo ""
    if [[ "$RELEASE_AUTO_CONFIRM" != "1" ]]; then
        read -r -p "Proceed with releasing all ${#affected_tools[@]} tool(s)? [y/N] " REPLY
        echo ""
        if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
            # EXIT trap will revert formulas automatically
            echo "Aborted. No changes made."
            exit 0
        fi
    fi

    # User confirmed: create local tags for every affected tool
    for tag in "${affected_tags[@]}"; do
        git tag "$tag"
    done

    local cleanup_tags="" cleanup_remote_tags="" cleanup_formulas=""
    for tag in "${affected_tags[@]}"; do
        cleanup_tags+="git tag -d \"$tag\"; "
        cleanup_remote_tags+="git push origin --delete \"$tag\" 2>/dev/null; "
    done
    for tool in "${affected_tools[@]}"; do
        cleanup_formulas+="Formula/$tool.rb "
    done
    _cleanup_msg="To clean up local tags: ${cleanup_tags}To delete any already-pushed remote tags: ${cleanup_remote_tags}To revert formulas: git -C \"$tap_repo\" checkout ${cleanup_formulas}"
    trap 'echo ""; echo "ERROR: release step failed. $_cleanup_msg"' ERR
    # Clear the EXIT trap now that we're committed
    trap - EXIT

    # Push all tags to the ai-utils remote in one go
    git push origin "${affected_tags[@]}"

    # Commit and push all formulas to the tap repo in a single commit.
    local commit_msg="chore: release ${affected_tags[*]}"
    local formula_paths=()
    for tool in "${affected_tools[@]}"; do
        formula_paths+=("Formula/$tool.rb")
    done
    if [[ "$MONOREPO_MODE" != "1" ]]; then
        if is_subtree "$tap_repo"; then
            local _repo_root _subtree_prefix abs_formula_paths=()
            _repo_root=$(git rev-parse --show-toplevel)
            _subtree_prefix="${tap_repo#${_repo_root}/}"
            for tool in "${affected_tools[@]}"; do
                abs_formula_paths+=("$tap_repo/Formula/$tool.rb")
            done
            git add "${abs_formula_paths[@]}"
            git commit -m "$commit_msg"
            git push origin HEAD
            git subtree push --prefix="$_subtree_prefix" tap main
        else
            git -C "$tap_repo" commit --only -m "$commit_msg" -- "${formula_paths[@]}"
            git -C "$tap_repo" push
        fi
    fi

    echo ""
    echo "Released ${#affected_tools[@]} tool(s):"
    for i in "${!affected_tools[@]}"; do
        echo "  ${affected_tags[$i]}"
    done
    echo "Teammates can upgrade with: brew upgrade <tool>"

    # Clear error trap
    trap - ERR
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage

TAP_REPO="$(git rev-parse --show-toplevel)/homebrew-devflow"
ALL_MODE=false

if [[ $# -eq 0 ]]; then
    ALL_MODE=true
elif [[ $# -eq 1 ]] && [[ -d "$1/Formula" ]] && git -C "$1" rev-parse --git-dir >/dev/null 2>&1; then
    ALL_MODE=true
    TAP_REPO="$1"
fi

# Fetch latest tags so version computation is up-to-date
git fetch --tags --quiet 2>/dev/null || echo "WARNING: could not fetch tags — version computation uses local tag state only." >&2

ensure_vendor_up_to_date

if [[ "$ALL_MODE" == true ]]; then
    release_all "$TAP_REPO"
    exit 0
fi

TOOL="$1"
VERSION_OVERRIDE=""

# Arg 2: version override if it starts with 'v', otherwise treat as tap path
if [[ $# -ge 2 ]]; then
    if [[ "$2" == v* ]]; then
        VERSION_OVERRIDE="$2"
        TAP_REPO="${3:-$(git rev-parse --show-toplevel)/homebrew-devflow}"
    else
        TAP_REPO="$2"
    fi
fi
FORMULA="$TAP_REPO/Formula/$TOOL.rb"

# Resolve version
if [[ -n "$VERSION_OVERRIDE" ]]; then
    if ! [[ "$VERSION_OVERRIDE" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "ERROR: version must be in format v1.2.3 (got: $VERSION_OVERRIDE)" >&2
        exit 1
    fi
    VERSION="$VERSION_OVERRIDE"
    VERSION_SOURCE="Override: version specified manually"
else
    VERSION=$(compute_next_version "$TOOL")
    # Count commits for summary (apply the same un-namespaced fallback)
    last_tag=$(git tag --list "$TOOL/v*" | sort -V | tail -1)
    if [[ -z "$last_tag" ]]; then
        last_tag=$(git tag --list "v*" | grep -v '/' | sort -V | tail -1) || true
    fi
    git_range="${last_tag:+${last_tag}..}HEAD"
    if [[ "$TOOL" == "devflow" ]]; then
        commit_count=$(git log "$git_range" --oneline 2>/dev/null | wc -l | tr -d ' ')
    else
        commit_count=$(git log "$git_range" --oneline -- "$TOOL/" "shared/" 2>/dev/null | wc -l | tr -d ' ')
    fi
    VERSION_SOURCE="Computed from ${commit_count} commit(s) since ${last_tag:-the beginning}"
fi

TAG="$TOOL/$VERSION"

# Check formula exists
if [[ ! -f "$FORMULA" ]]; then
    echo "ERROR: formula not found at $FORMULA" >&2
    exit 1
fi

check_formula_has_vendor_install "$FORMULA"

# Check TAP_REPO is a valid git checkout
if ! git -C "$TAP_REPO" rev-parse --git-dir >/dev/null 2>&1; then
    echo "ERROR: $TAP_REPO is not a git checkout" >&2
    exit 1
fi

# Check tag doesn't already exist locally
if git rev-parse "refs/tags/$TAG" >/dev/null 2>&1; then
    echo "ERROR: tag $TAG already exists. To re-release, delete it first: git tag -d $TAG" >&2
    exit 1
fi

# Warn on uncommitted changes
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "WARNING: you have uncommitted changes — the tag will point at the current HEAD regardless." >&2
    echo ""
fi

# Compute the revision that would be tagged (current HEAD)
REVISION="$(git rev-list -n 1 HEAD)"
SHORT_REV="${REVISION:0:7}"

# Update formula (temporarily, to show what the diff would be)
sed -i '' "s|tag:.*|tag:      \"$TAG\",|" "$FORMULA"
sed -i '' "s|revision:.*|revision: \"$REVISION\"|" "$FORMULA"

# Install cleanup trap immediately after sed mutates the formula
_revert_formula() {
    git -C "$TAP_REPO" checkout "Formula/$TOOL.rb" 2>/dev/null
}
trap _revert_formula EXIT

# Ensure the formula actually changed before we commit to pushing the tag
if git -C "$TAP_REPO" diff --quiet "Formula/$TOOL.rb"; then
    echo "ERROR: formula was not modified by sed (tag/revision lines may not match expected format)." >&2
    exit 1
fi

# Show summary and diff
echo "About to release $TOOL $VERSION"
echo ""
echo "  Tag:      $TAG → $SHORT_REV"
echo "  Version:  $VERSION_SOURCE"
echo "  Push to:  origin (devflow-platform)"
echo "  Formula:  $FORMULA"
echo ""
echo "Formula diff:"
git -C "$TAP_REPO" diff "Formula/$TOOL.rb"
echo ""
if [[ "$RELEASE_AUTO_CONFIRM" != "1" ]]; then
    read -r -p "Proceed? [y/N] " REPLY
    echo ""
    if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
        # EXIT trap will revert formula automatically
        echo "Aborted. No changes made."
        exit 0
    fi
fi

# User confirmed: now create the local tag
git tag "$TAG"
_cleanup_msg="To clean up: git tag -d \"$TAG\" && git -C \"$TAP_REPO\" checkout Formula/$TOOL.rb"
trap 'echo ""; echo "ERROR: release step failed. $_cleanup_msg"' ERR
# Clear the EXIT trap now that we're committed
trap - EXIT

# Push tag to ai-utils remote
git push origin "$TAG"

# Commit and push formula to tap repo
if [[ "$MONOREPO_MODE" != "1" ]]; then
    if is_subtree "$TAP_REPO"; then
        _repo_root=$(git rev-parse --show-toplevel)
        _subtree_prefix="${TAP_REPO#${_repo_root}/}"
        git add "$TAP_REPO/Formula/$TOOL.rb"
        git commit -m "chore: release $TOOL $TAG"
        git push origin HEAD
        git subtree push --prefix="$_subtree_prefix" tap main
    else
        git -C "$TAP_REPO" add "Formula/$TOOL.rb"
        git -C "$TAP_REPO" commit -m "chore: release $TOOL $TAG"
        git -C "$TAP_REPO" push
    fi
fi

echo ""
echo "Released $TOOL $TAG."
echo "Teammates can upgrade with: brew upgrade $TOOL"

# Clear error trap
trap - ERR
