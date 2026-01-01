#!/usr/bin/env python3
"""Repository hygiene checker for SciTrans.

Ensures banned artifacts (.venv, caches, etc.) are not tracked by git
and not included in build outputs.

Usage:
    python scripts/check_repo_hygiene.py --root .
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Banned patterns that should NEVER be tracked or packaged
BANNED_PATTERNS = [
    ".venv",
    ".idea",
    ".vscode",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.egg-info",
    "*.egg",
    "dist",
    "build",
    "outputs",
    "previews",
    ".DS_Store",
    ".env",
    "*.log",
]

# Patterns that should be in .gitignore
REQUIRED_GITIGNORE_PATTERNS = [
    ".venv/",
    ".idea/",
    ".vscode/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    "*.egg-info/",
    "*.egg",
    "dist/",
    "build/",
    "outputs/",
    "previews/",
    ".DS_Store",
    ".env",
    "*.log",
]


def check_git_tracked_files(root: Path) -> list[str]:
    """Check if any banned patterns are tracked by git."""
    issues = []

    # Check if git repo exists
    if not (root / ".git").exists():
        print("ℹ️  No .git directory found (not a git repo yet)")
        return issues

    try:
        # Get all tracked files
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        tracked_files = result.stdout.strip().split("\n")

        # Check for banned patterns
        for pattern in BANNED_PATTERNS:
            if "*" in pattern:
                # Wildcard pattern
                suffix = pattern.replace("*", "")
                matching = [f for f in tracked_files if f.endswith(suffix)]
                if matching:
                    issues.append(
                        f"⚠️  Found tracked files matching '{pattern}': {len(matching)} files"
                    )
                    for f in matching[:3]:  # Show first 3
                        issues.append(f"    - {f}")
                    if len(matching) > 3:
                        issues.append(f"    ... and {len(matching) - 3} more")
            else:
                # Directory or file pattern
                matching = [f for f in tracked_files if pattern in f]
                if matching:
                    issues.append(f"⚠️  Found tracked files in '{pattern}': {len(matching)} files")
                    for f in matching[:3]:
                        issues.append(f"    - {f}")
                    if len(matching) > 3:
                        issues.append(f"    ... and {len(matching) - 3} more")

    except subprocess.CalledProcessError as e:
        print(f"ℹ️  Skipping git tracked check (not a repo yet): {e}")

    return issues


def check_gitignore(root: Path) -> list[str]:
    """Check if .gitignore contains required patterns."""
    issues = []
    gitignore_path = root / ".gitignore"

    if not gitignore_path.exists():
        issues.append("❌ No .gitignore file found")
        return issues

    gitignore_content = gitignore_path.read_text()

    missing_patterns = []
    for pattern in REQUIRED_GITIGNORE_PATTERNS:
        if pattern not in gitignore_content:
            missing_patterns.append(pattern)

    if missing_patterns:
        issues.append(f"⚠️  Missing {len(missing_patterns)} patterns in .gitignore:")
        for pattern in missing_patterns[:5]:
            issues.append(f"    - {pattern}")
        if len(missing_patterns) > 5:
            issues.append(f"    ... and {len(missing_patterns) - 5} more")

    return issues


def check_local_artifacts(root: Path) -> list[str]:
    """Check for banned artifacts in the working directory."""
    issues = []

    found_artifacts = []
    for pattern in BANNED_PATTERNS:
        if "*" in pattern:
            # Wildcard pattern - check files
            suffix = pattern.replace("*", "")
            for path in root.rglob(f"*{suffix}"):
                if path.is_file():
                    found_artifacts.append(str(path.relative_to(root)))
        else:
            # Directory pattern
            path = root / pattern
            if path.exists():
                found_artifacts.append(pattern)

    if found_artifacts:
        issues.append(f"ℹ️  Found {len(found_artifacts)} local artifacts (OK if gitignored):")
        for artifact in found_artifacts[:5]:
            issues.append(f"    - {artifact}")
        if len(found_artifacts) > 5:
            issues.append(f"    ... and {len(found_artifacts) - 5} more")

    return issues


def check_manifest(root: Path) -> list[str]:
    """Check MANIFEST.in for proper exclusions."""
    issues = []
    manifest_path = root / "MANIFEST.in"

    if not manifest_path.exists():
        issues.append("⚠️  No MANIFEST.in found (may include unwanted files in sdist)")
        return issues

    manifest_content = manifest_path.read_text()

    # Check for prune directives
    required_prunes = [".venv", ".idea", ".pytest_cache", "__pycache__", "outputs", "previews"]
    missing_prunes = []

    for prune_dir in required_prunes:
        if (
            f"prune {prune_dir}" not in manifest_content
            and f"prune *{prune_dir}" not in manifest_content
        ):
            missing_prunes.append(prune_dir)

    if missing_prunes:
        issues.append(f"⚠️  MANIFEST.in missing prune for: {', '.join(missing_prunes)}")

    return issues


def main():
    parser = argparse.ArgumentParser(description="Check SciTrans repo hygiene")
    parser.add_argument("--root", type=Path, required=True, help="Repository root directory")
    parser.add_argument("--strict", action="store_true", help="Fail on local artifacts (for CI)")
    args = parser.parse_args()

    root = args.root.resolve()

    print("=" * 60)
    print("SciTrans Repository Hygiene Check")
    print("=" * 60)
    print(f"Root: {root}")
    print()

    all_issues = []

    # Check 1: Git tracked files
    print("1. Checking git tracked files...")
    git_issues = check_git_tracked_files(root)
    all_issues.extend(git_issues)
    if not git_issues:
        print("   ✅ No banned patterns tracked by git")
    else:
        for issue in git_issues:
            print(f"   {issue}")
    print()

    # Check 2: .gitignore
    print("2. Checking .gitignore...")
    gitignore_issues = check_gitignore(root)
    all_issues.extend(gitignore_issues)
    if not gitignore_issues:
        print("   ✅ .gitignore contains all required patterns")
    else:
        for issue in gitignore_issues:
            print(f"   {issue}")
    print()

    # Check 3: Local artifacts
    print("3. Checking local artifacts...")
    artifact_issues = check_local_artifacts(root)
    if not artifact_issues:
        print("   ✅ No local artifacts found")
    else:
        for issue in artifact_issues:
            print(f"   {issue}")
        if not args.strict:
            print("   ℹ️  Local artifacts are OK for development (ignored by git)")
        else:
            all_issues.extend(artifact_issues)
    print()

    # Check 4: MANIFEST.in
    print("4. Checking MANIFEST.in...")
    manifest_issues = check_manifest(root)
    all_issues.extend(manifest_issues)
    if not manifest_issues:
        print("   ✅ MANIFEST.in properly configured")
    else:
        for issue in manifest_issues:
            print(f"   {issue}")
    print()

    # Summary
    print("=" * 60)
    if all_issues:
        print(f"❌ Found {len(all_issues)} issue(s)")
        print()
        print("To fix:")
        print("  - Remove tracked artifacts: git rm -r --cached <pattern>")
        print("  - Update .gitignore with missing patterns")
        print("  - Update MANIFEST.in with prune directives")
        sys.exit(1)
    else:
        print("✅ All hygiene checks passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
