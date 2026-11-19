"""Plain data structures shared by the scanner, classifier and API."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .manifests import Manifest

CATEGORIES: tuple[str, ...] = (
    "AI/ML", "Security", "Backend", "Frontend", "Full-stack", "Data", "DevOps", "Mobile", "Documentation",
    "Prompt Engineering", "Other",
)
STATUSES: tuple[str, ...] = ("Active", "Idle", "Needs attention", "Missing")
# How a project row came to exist. "folder": a top-level folder of the workspace (the default rule);
# "promoted": a nested folder the user marked as an independent project. The remaining values are the
# older marker-based kinds, still used to describe nested sub-project candidates.
DETECTED_TYPES: tuple[str, ...] = ("folder", "promoted", "manifest", "git", "group", "loose")
# Internal parts of a project (shown in the details panel, feeding category labels).
COMPONENT_KINDS: tuple[str, ...] = (
    "Frontend", "Backend", "AI/ML", "Data", "Documentation", "Tests", "DevOps", "Mobile", "Prompt Engineering",
    "Security", "Shared", "Module",
)


@dataclass
class FileEntry:
    relative_path: str
    extension: str
    size: int
    mtime: int
    kind: str
    sensitive: bool = False


@dataclass
class Evidence:
    rule: str
    detail: str
    weight: float
    source: str = "rules"

    def to_dict(self) -> dict[str, Any]:
        return {"rule": self.rule, "detail": self.detail, "weight": round(self.weight, 3), "source": self.source}


@dataclass
class TechDetection:
    name: str
    kind: str
    confidence: float
    evidence: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind, "confidence": round(self.confidence, 3),
                "evidence": [e.to_dict() for e in self.evidence]}


@dataclass
class CategoryDetection:
    name: str
    confidence: float
    evidence: list[Evidence] = field(default_factory=list)
    source: str = "rules"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "confidence": round(self.confidence, 3), "source": self.source,
                "evidence": [e.to_dict() for e in self.evidence]}


@dataclass
class Component:
    """An internal part of a project: ``backend/`` (Backend), ``apps/web`` (Frontend), ``docs/`` (Documentation)…"""
    kind: str                      # one of COMPONENT_KINDS
    path: str                      # directory relative to the project root ("" = evidence at the root)
    name: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    file_count: int = 0
    languages: list[str] = field(default_factory=list)
    manifests: list[str] = field(default_factory=list)
    has_git: bool = False
    candidate: bool = False        # carries its own manifest / repository → could be promoted to a project

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "path": self.path, "name": self.name, "evidence": self.evidence, "file_count": self.file_count,
                "languages": self.languages, "manifests": self.manifests, "has_git": self.has_git, "candidate": self.candidate}


@dataclass
class ProjectFacts:
    """Everything the classifier is allowed to see. No file contents except manifests/README excerpt."""
    name: str
    relative_path: str
    files: list[FileEntry]
    dir_names: set[str]            # every directory name seen (lower-case), any depth
    top_level: set[str]            # entries directly in the project root (lower-case)
    languages: dict[str, dict[str, int]]  # language -> {files, bytes}
    manifests: list[Manifest]
    readme_title: str | None = None
    readme_excerpt: str | None = None
    has_git: bool = False
    detected_type: str = "folder"
    components: list[tuple[str, str]] = field(default_factory=list)  # (kind, name) of detected internal parts
    child_categories: list[list[str]] = field(default_factory=list)  # categories of promoted sub-projects
    child_names: list[str] = field(default_factory=list)


@dataclass
class GitSnapshot:
    repo_root: str | None = None
    is_repo_root: bool = False
    branch: str | None = None
    detached: bool = False
    dirty: bool | None = None
    modified_count: int | None = None
    untracked_count: int | None = None
    staged_count: int | None = None
    ahead: int | None = None
    behind: int | None = None
    upstream: str | None = None
    last_commit_at: int | None = None
    last_commit_subject: str | None = None
    last_commit_author: str | None = None
    commits_30d: int | None = None
    recent_commits: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_root": self.repo_root, "is_repo_root": self.is_repo_root, "branch": self.branch, "detached": self.detached,
            "dirty": self.dirty, "modified_count": self.modified_count, "untracked_count": self.untracked_count,
            "staged_count": self.staged_count, "ahead": self.ahead, "behind": self.behind, "upstream": self.upstream,
            "last_commit_at": self.last_commit_at, "last_commit_subject": self.last_commit_subject,
            "last_commit_author": self.last_commit_author, "commits_30d": self.commits_30d,
            "recent_commits": self.recent_commits, "error": self.error,
        }
