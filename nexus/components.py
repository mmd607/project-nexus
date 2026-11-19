"""Internal structure of a project: which parts it is made of, and which nested folders look like projects.

A top-level folder is always exactly one project. What lives inside it (``backend/``, ``apps/web``,
``docs/``, ``notebooks/`` …) is described here as *components* — evidence for the project's category
labels and a map for the details panel — and, in "nested" scan mode, as *sub-project candidates*
that the user may promote to independent nodes. Nothing here reads file contents.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from . import classifier
from .languages import CODE_LANGUAGES, language_for, split_ext
from .manifests import EXT_MARKERS, STRONG_MARKERS, WEAK_MARKERS, Manifest
from .model import Component, FileEntry, ProjectFacts

# Folders whose children are usually independent packages (monorepo layouts).
CONTAINER_DIRS = {"apps", "packages", "services", "modules", "libs", "crates", "plugins", "projects", "examples", "workspaces",
                  "microservices", "components"}
# Folders that are never components on their own: implementation detail, assets or build output.
NOISE_DIRS = {"src", "lib", "utils", "util", "helpers", "assets", "static", "public", "config", "configs", "scripts", "migrations",
              "templates", "layouts", "partials", "includes", "css", "js", "styles", "img", "images", "fonts", "media", "resources",
              "res", "icons", "svg", "bin", "obj", "dist", "build", "out", "tmp", "temp", "logs", "log", "cache", "vendor",
              "node_modules", "__pycache__", "venv", ".venv", "env", "target", "coverage", "misc", "other", "old", "backup",
              "backups", "archive", "archives", "samples", "sample", "fixtures", "locale", "locales", "i18n", "typings", "types",
              "hooks", "store", "stores", "pages", "views", "routes", "controllers", "handlers", "middleware", "middlewares",
              "schemas", "entities", "dto", "constants", "enums", "interfaces", "mixins", "filters", "validators", "serializers",
              "settings", "conf", "etc", "var", "wwwroot", "properties", "meta", "gen", "generated", "proto", "protos"}
ASSET_FOLDER_NAMES = {"css", "js", "javascript", "scripts", "styles", "assets", "static", "public", "img", "images", "fonts", "media",
                      "vendor", "lib", "libs", "dist", "build", "resources", "res", "icons", "svg", "data", "docs", "doc", "templates",
                      "layouts", "partials", "includes", "utils", "helpers", "config", "configs", "migrations", "tests", "test", "__tests__"}

# Folder-name tokens → component kind (checked in this order; first hit wins).
NAME_HINTS: list[tuple[str, set[str]]] = [
    ("Tests", {"tests", "test", "__tests__", "spec", "e2e", "integration_tests", "integration-tests", "unit_tests", "unit-tests",
               "cypress", "playwright", "testing", "qa"}),
    ("Documentation", {"docs", "doc", "documentation", "wiki", "guides", "guide", "handbook", "specs", "specification", "adr", "rfcs",
                       "manual", "manuals", "book", "docsite"}),
    ("DevOps", {"infra", "infrastructure", "deploy", "deployment", "deployments", "devops", "ops", "k8s", "kubernetes", "helm",
                "terraform", "ansible", "docker", "ci", "cicd", "ci-cd", "nginx", "compose", "provisioning", "iac", "charts",
                "pipelines", "monitoring", "observability", ".github", ".gitlab"}),
    ("Mobile", {"mobile", "android", "ios", "flutter", "react-native", "reactnative", "expo", "apps-mobile", "mobile-app", "mobileapp"}),
    ("Prompt Engineering", {"prompts", "prompt", "prompt_templates", "prompt-templates", "personas", "system_prompts", "system-prompts",
                            "agents", "agent", "skills"}),
    ("AI/ML", {"ai", "ml", "machine_learning", "machine-learning", "deep_learning", "deep-learning", "training", "train", "inference",
               "notebooks", "notebook", "experiments", "llm", "llms", "rag", "nlp", "vision", "cv", "embeddings", "checkpoints",
               "weights", "detection", "yolo", "neural", "transformers", "finetune", "fine-tune", "fine_tune", "ml_pipeline",
               "ai_engine", "ai-engine", "intelligence", "recognition", "classifier", "predictor", "forecasting"}),
    ("Security", {"security", "pentest", "exploits", "payloads", "recon", "forensics", "malware", "yara", "wordlists"}),
    ("Data", {"data", "datasets", "dataset", "etl", "analytics", "warehouse", "dbt", "sql", "database", "databases", "db", "ingestion",
              "scraper", "scrapers", "crawler", "crawlers", "reports", "statistics", "stats", "lake"}),
    ("Shared", {"shared", "common", "sdk", "contracts", "internal", "toolkit", "commons", "base", "api-client", "apiclient", "client-sdk",
                "shared-lib", "shared_lib", "libraries", "library"}),
    ("Frontend", {"frontend", "front-end", "front_end", "client", "clients", "web", "webapp", "web-app", "web_app", "ui", "www", "site",
                  "website", "dashboard", "admin", "portal", "landing", "storefront", "spa", "pwa", "widget", "widgets", "theme",
                  "themes", "design-system", "design_system", "front"}),
    ("Backend", {"backend", "back-end", "back_end", "server", "servers", "api", "apis", "gateway", "worker", "workers", "service",
                 "microservice", "microservices", "bot", "bots", "rest", "graphql", "grpc", "webhook", "webhooks", "daemon", "engine",
                 "back", "srv", "core-api", "auth", "notifications", "scheduler", "jobs", "queue", "consumer", "producer"}),
]
# Tokens that only count with supporting evidence (they are ambiguous on their own).
CONDITIONAL_HINTS = {"models": "AI/ML", "model": "AI/ML", "app": "Frontend", "core": "Module", "src": "Module"}
# Root-level files that describe deployment / delivery.
DEPLOY_FILES = {"dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml", "procfile", "fly.toml",
                "render.yaml", "railway.json", "vercel.json", "netlify.toml", "serverless.yml", "serverless.yaml", "helmfile.yaml",
                "skaffold.yaml", "app.yaml", "nginx.conf", "kustomization.yaml"}
IMPORTANT_ROOT_FILES = {"readme.md": "readme", "readme.rst": "readme", "readme.txt": "readme", "readme": "readme",
                        "license": "license", "license.md": "license", "license.txt": "license", "licence": "license",
                        "contributing.md": "docs", "changelog.md": "docs", "changes.md": "docs", "code_of_conduct.md": "docs",
                        "security.md": "docs", "architecture.md": "docs", "dockerfile": "deploy", "docker-compose.yml": "deploy",
                        "docker-compose.yaml": "deploy", "compose.yml": "deploy", "compose.yaml": "deploy", "procfile": "deploy",
                        "fly.toml": "deploy", "render.yaml": "deploy", "railway.json": "deploy", "vercel.json": "deploy",
                        "netlify.toml": "deploy", "serverless.yml": "deploy", "makefile": "build", "justfile": "build",
                        "taskfile.yml": "build", ".env.example": "config", ".env.sample": "config", ".env.template": "config",
                        ".editorconfig": "config", ".gitignore": "config", ".pre-commit-config.yaml": "config", "codeowners": "config",
                        "claude.md": "agent", "agents.md": "agent", "agent.md": "agent", "gemini.md": "agent", ".cursorrules": "agent",
                        "copilot-instructions.md": "agent", "openapi.yaml": "api", "openapi.yml": "api", "openapi.json": "api",
                        "swagger.yaml": "api", "swagger.json": "api", "schema.prisma": "schema", "alembic.ini": "schema"}
# Files a reader opens first to understand how a project starts.
ENTRY_POINTS = {"main.py", "app.py", "manage.py", "run.py", "server.py", "wsgi.py", "asgi.py", "cli.py", "__main__.py", "index.js", "index.ts",
                "main.js", "main.ts", "server.js", "server.ts", "app.js", "app.ts", "main.go", "main.rs", "lib.rs", "main.dart", "program.cs",
                "main.java", "application.java", "index.html", "index.php", "main.swift", "app.vue", "app.tsx", "app.jsx", "main.tsx", "main.jsx"}
MAX_COMPONENTS = 24
MAX_CANDIDATES = 80
MAX_IMPORTANT = 30
_TOKEN_SPLIT = re.compile(r"[\s_\-.]+|(?<=[a-z0-9])(?=[A-Z])")

# Weight each component kind adds to the parent project's category of the same name.
KIND_CATEGORY_WEIGHT: dict[str, float] = {
    "Frontend": .55, "Backend": .55, "AI/ML": .5, "Mobile": .5, "Security": .45, "Prompt Engineering": .45, "Data": .35,
    "DevOps": .25, "Documentation": .2,
}


@dataclass
class Subtree:
    path: str                      # relative directory ("" = project root)
    files: list[FileEntry] = field(default_factory=list)
    direct_names: set[str] = field(default_factory=set)   # lower-case file names directly in the directory
    dir_names: set[str] = field(default_factory=set)
    depth: int = 0


@dataclass
class Candidate:
    """A nested folder that looks like a project of its own (nested scan mode)."""
    relative_path: str             # relative to the parent project
    name: str
    detected_type: str             # manifest | git | loose
    evidence: list[dict[str, Any]]
    depth: int
    file_count: int = 0
    primary_language: str | None = None
    manifests: list[str] = field(default_factory=list)
    has_git: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"relative_path": self.relative_path, "name": self.name, "detected_type": self.detected_type, "evidence": self.evidence,
                "depth": self.depth, "file_count": self.file_count, "primary_language": self.primary_language,
                "manifests": self.manifests, "has_git": self.has_git}


def tokens(name: str) -> list[str]:
    return [t for t in _TOKEN_SPLIT.split(name.strip()) if t]


def _languages_of(files: list[FileEntry], limit: int = 3) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for f in files:
        lang = language_for(f.relative_path.rsplit("/", 1)[-1], f.extension)
        if lang in CODE_LANGUAGES:
            counts[lang] += 1
    return [k for k, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


def _group_subtrees(files: list[FileEntry], dirs: list[str]) -> tuple[Subtree, dict[str, Subtree]]:
    """Root subtree + one subtree per depth-1 directory and per child of a container directory."""
    root = Subtree("")
    groups: dict[str, Subtree] = {}

    def get(path: str, depth: int) -> Subtree:
        st = groups.get(path)
        if st is None:
            st = groups[path] = Subtree(path, depth=depth)
        return st

    for f in files:
        parts = f.relative_path.split("/")
        name = parts[-1].lower()
        if len(parts) == 1:
            root.files.append(f)
            root.direct_names.add(name)
            continue
        root.files.append(f)
        root.dir_names.add(parts[0].lower())
        first = get(parts[0], 1)
        first.files.append(f)
        if len(parts) == 2:
            first.direct_names.add(name)
        else:
            first.dir_names.add(parts[1].lower())
            if parts[0].lower() in CONTAINER_DIRS:
                second = get(parts[0] + "/" + parts[1], 2)
                second.files.append(f)
                if len(parts) == 3:
                    second.direct_names.add(name)
                else:
                    second.dir_names.add(parts[2].lower())
    for d in dirs:
        parts = d.split("/")
        if len(parts) == 1:
            get(parts[0], 1)
            root.dir_names.add(parts[0].lower())
        elif len(parts) == 2:
            groups.get(parts[0], get(parts[0], 1)).dir_names.add(parts[1].lower())
            if parts[0].lower() in CONTAINER_DIRS:
                get(d, 2)
    return root, groups


def _name_kind(name: str, st: Subtree, kinds_of_files: dict[str, int]) -> tuple[str | None, str]:
    toks = {t.lower() for t in tokens(name)} | {name.lower()}
    for kind, words in NAME_HINTS:
        hit = toks & words
        if hit:
            return kind, f"folder name “{name}” ({sorted(hit)[0]})"
    for tok in toks:
        cond = CONDITIONAL_HINTS.get(tok)
        if cond == "AI/ML" and (kinds_of_files.get("model") or kinds_of_files.get("notebook")):
            return cond, f"folder name “{name}” with model/notebook files"
        if cond == "Frontend" and any(n in st.direct_names for n in ("package.json", "index.html")):
            return cond, f"folder name “{name}” with a web manifest"
    return None, ""


def _subtree_facts(name: str, st: Subtree, manifests: list[Manifest], has_git: bool) -> ProjectFacts:
    prefix = st.path + "/" if st.path else ""
    files = [FileEntry(f.relative_path[len(prefix):], f.extension, f.size, f.mtime, f.kind, f.sensitive) for f in st.files]
    langs: dict[str, dict[str, int]] = {}
    for f in files:
        lang = language_for(f.relative_path.rsplit("/", 1)[-1], f.extension)
        if lang:
            s = langs.setdefault(lang, {"files": 0, "bytes": 0})
            s["files"] += 1
            s["bytes"] += f.size
    dir_names = {seg.lower() for f in files for seg in f.relative_path.split("/")[:-1]}
    sub_manifests = [m for m in manifests if m.path.startswith(prefix)]
    return ProjectFacts(name=name, relative_path=st.path, files=files, dir_names=dir_names, top_level=set(st.direct_names) | {d for d in st.dir_names},
                        languages=langs, manifests=sub_manifests, has_git=has_git, detected_type="folder")


def detect_components(files: list[FileEntry], dirs: list[str], git_dirs: set[str], manifests: list[Manifest]) -> list[Component]:
    """Describe the internal parts of a project from its file listing. Deterministic and explainable."""
    root, groups = _group_subtrees(files, dirs)
    out: list[Component] = []
    manifest_paths = [m.path for m in manifests]

    for path, st in sorted(groups.items(), key=lambda kv: (kv[1].depth, kv[0].lower())):
        name = path.rsplit("/", 1)[-1]
        lower = name.lower()
        if lower in CONTAINER_DIRS and st.depth == 1:
            continue  # its children are examined individually
        if lower.startswith("."):
            continue  # CI configuration under .github/ is reported with the root-level deployment component
        own_manifests = [m for m in manifest_paths if m.rsplit("/", 1)[0] == path]
        has_git = path in git_dirs
        candidate = bool(own_manifests) or has_git
        kinds_of_files: dict[str, int] = defaultdict(int)
        for f in st.files:
            kinds_of_files[f.kind] += 1
        if lower in NOISE_DIRS and not candidate:
            continue
        kind, why = _name_kind(name, st, kinds_of_files)
        evidence: list[dict[str, Any]] = []
        if kind:
            evidence.append({"rule": "folder-name", "detail": why})
        # Content-based classification of the subtree confirms or supplies the kind.
        source_files = kinds_of_files.get("source", 0) + kinds_of_files.get("test", 0) + kinds_of_files.get("notebook", 0)
        if kind is None or candidate or source_files >= 3:
            facts = _subtree_facts(name, st, manifests, has_git)
            cats, _techs = classifier.classify(facts)
            top = cats[0] if cats else None
            if top and top.name != "Other" and top.confidence >= 0.5:
                mapped = "Module" if top.name == "Full-stack" else top.name
                if kind is None:
                    kind = mapped
                for e in top.evidence[:3]:
                    evidence.append({"rule": f"content:{e.rule}", "detail": e.detail})
        if kind is None and candidate:
            kind = "Module"
            evidence.append({"rule": "manifest" if own_manifests else "git", "detail": ", ".join(m.rsplit("/", 1)[-1] for m in own_manifests) or ".git directory"})
        if kind is None:
            continue
        if not evidence:
            evidence.append({"rule": "folder", "detail": f"{len(st.files)} files"})
        out.append(Component(kind=kind, path=path, name=name, evidence=evidence[:6], file_count=len(st.files), languages=_languages_of(st.files),
                             manifests=[m for m in manifest_paths if m.startswith(path + "/")][:6], has_git=has_git, candidate=candidate))

    # Deployment described at the root (Dockerfile, compose, CI workflows, k8s manifests).
    deploy_hits = sorted(n for n in root.direct_names if n in DEPLOY_FILES)
    ci = sorted({f.relative_path for f in files if f.relative_path.lower().startswith((".github/workflows/", ".gitlab-ci", ".circleci/"))})[:3]
    if deploy_hits or ci:
        detail = ", ".join(deploy_hits[:4] + [c.split("/")[-1] if "/" in c else c for c in ci[:2]])
        out.append(Component(kind="DevOps", path="", name="Deployment", evidence=[{"rule": "root-files", "detail": detail}],
                             file_count=len(deploy_hits) + len(ci)))
    priority = {"Frontend": 0, "Backend": 1, "AI/ML": 2, "Mobile": 3, "Data": 4, "Prompt Engineering": 5, "Security": 6, "Shared": 7,
                "Module": 8, "DevOps": 9, "Tests": 10, "Documentation": 11}
    out.sort(key=lambda c: (priority.get(c.kind, 99), -c.file_count, c.path.lower()))
    return out[:MAX_COMPONENTS]


def find_candidates(files: list[FileEntry], dirs: list[str], git_dirs: set[str], max_depth: int, detect_loose: bool,
                    root_has_marker: bool) -> list[Candidate]:
    """Nested folders that would have been projects of their own (marker-based, bounded by *max_depth*)."""
    direct: dict[str, set[str]] = defaultdict(set)
    sources: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    langs: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))   # prefix → lang → [files, bytes]
    for f in files:
        parts = f.relative_path.split("/")
        d = "/".join(parts[:-1])
        direct[d].add(parts[-1].lower())
        lang = language_for(parts[-1], f.extension)
        if lang in CODE_LANGUAGES:
            sources[d] += 1
        for i in range(1, len(parts)):
            prefix = "/".join(parts[:i])
            counts[prefix] += 1
            if lang in CODE_LANGUAGES:
                langs[prefix][lang][0] += 1
                langs[prefix][lang][1] += f.size
    all_dirs = sorted(set(dirs) | {d for d in direct if d}, key=lambda d: (d.count("/"), d.lower()))
    found: dict[str, Candidate] = {}
    for d in all_dirs:
        depth = d.count("/") + 1
        if depth > max_depth:
            continue
        name = d.rsplit("/", 1)[-1]
        names = direct.get(d, set())
        strong = sorted(n for n in names if n in STRONG_MARKERS)
        ext = sorted(n for n in names if split_ext(n) in EXT_MARKERS)
        weak = sorted(n for n in names if n in WEAK_MARKERS)
        has_git = d in git_dirs
        inside = any(d.startswith(c + "/") for c in found)
        detected: str | None = None
        evidence: list[dict[str, Any]] = []
        if strong or ext:
            detected = "manifest"
            evidence.append({"rule": "manifest" if strong else "project-file", "detail": ", ".join((strong or ext)[:5])})
        if has_git:
            detected = detected or "git"
            evidence.append({"rule": "git", "detail": ".git directory"})
        if not detected and weak and (sources[d] or len([w for w in weak if w != "readme.md"]) >= 2):
            detected = "manifest"
            evidence.append({"rule": "weak-marker", "detail": f"{', '.join(weak[:3])} + {sources[d]} source files"})
        if not detected and detect_loose and not inside and not root_has_marker and sources[d] >= 3 and name.lower() not in ASSET_FOLDER_NAMES:
            detected = "loose"
            evidence.append({"rule": "loose-sources", "detail": f"{sources[d]} source files, no manifest"})
        if not detected:
            continue
        lang_counts = langs.get(d, {})
        markup = {"HTML", "CSS", "SCSS", "Less", "Shell", "Batch", "PowerShell", "SQL"}
        ranked = sorted(((k, v) for k, v in lang_counts.items() if k not in markup) or lang_counts.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))
        primary = ranked[0][0] if ranked else None
        found[d] = Candidate(d, name, detected, evidence, depth, counts.get(d, 0), primary, strong + ext, has_git)
        if len(found) >= MAX_CANDIDATES:
            break
    return list(found.values())


def important_files(files: list[FileEntry], manifests: list[Manifest]) -> list[dict[str, str]]:
    """Manifests plus the well-known files a reader looks for first (README, LICENSE, Dockerfile, CI …)."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in sorted(manifests, key=lambda m: (m.path.count("/"), m.path.lower())):
        if m.path not in seen:
            seen.add(m.path)
            out.append({"path": m.path, "kind": "manifest", "detail": m.kind})
    for f in sorted(files, key=lambda f: (f.relative_path.count("/"), f.relative_path.lower())):
        if f.sensitive or f.relative_path in seen:
            continue
        parts = f.relative_path.split("/")
        name = parts[-1].lower()
        kind = None
        if len(parts) == 1 and name in IMPORTANT_ROOT_FILES:
            kind = IMPORTANT_ROOT_FILES[name]
        elif len(parts) == 3 and parts[0].lower() == ".github" and parts[1].lower() == "workflows":
            kind = "ci"
        elif name in {"chart.yaml", "kustomization.yaml"} and len(parts) <= 3:
            kind = "deploy"
        elif name in ENTRY_POINTS and (len(parts) == 1 or (len(parts) == 2 and parts[0].lower() in {"src", "app", "cmd", "lib", "bin"})):
            kind = "entry"
        elif name in {"schema.prisma", "schema.sql", "schema.graphql", "openapi.yaml", "openapi.json", "swagger.json", "alembic.ini"} and len(parts) <= 3:
            kind = "schema"
        if kind:
            seen.add(f.relative_path)
            out.append({"path": f.relative_path, "kind": kind, "detail": ""})
        if len(out) >= MAX_IMPORTANT:
            break
    return out[:MAX_IMPORTANT]


def structure_kind(root_names: set[str], has_root_git: bool, components: list[Component], candidates_hint: int,
                   source_files: int, doc_files: int, total_files: int, workspaces_declared: bool) -> str:
    """One word for how the folder is organised (shown as the project type)."""
    strong = any(n in STRONG_MARKERS or split_ext(n) in EXT_MARKERS for n in root_names)
    parts = [c for c in components if c.kind in {"Frontend", "Backend", "AI/ML", "Mobile"}]
    modules = [c for c in components if c.candidate]
    if workspaces_declared or (strong and len(modules) >= 2):
        return "monorepo"
    if len(parts) >= 2:
        return "multi-part"
    if not strong and not has_root_git and (len(modules) >= 2 or candidates_hint >= 2):
        return "collection"
    if has_root_git:
        return "repository"
    if strong:
        return "project"
    if total_files and source_files == 0 and doc_files / max(1, total_files) >= 0.5:
        return "documents"
    if source_files:
        return "sources"
    return "folder"
