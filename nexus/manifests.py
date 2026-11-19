"""Read-only, size-capped parsers for well-known project manifests.

Every parser is defensive: malformed input yields a partial manifest, never an
exception. Only *names* of dependencies/scripts are kept; values (URLs, tokens,
env) are discarded so nothing sensitive is retained or shown to a model.
"""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import asdict, dataclass, field
from typing import Any

MANIFEST_FILES: dict[str, str] = {
    "package.json": "package.json",
    "pyproject.toml": "pyproject",
    "requirements.txt": "requirements",
    "requirements-dev.txt": "requirements",
    "requirements_dev.txt": "requirements",
    "dev-requirements.txt": "requirements",
    "setup.py": "setup.py",
    "setup.cfg": "setup.cfg",
    "pipfile": "pipfile",
    "environment.yml": "conda",
    "environment.yaml": "conda",
    "cargo.toml": "cargo",
    "go.mod": "gomod",
    "pom.xml": "pom",
    "build.gradle": "gradle",
    "build.gradle.kts": "gradle",
    "gemfile": "gemfile",
    "composer.json": "composer",
    "pubspec.yaml": "pubspec",
    "cmakelists.txt": "cmake",
    "dockerfile": "dockerfile",
    "docker-compose.yml": "compose",
    "docker-compose.yaml": "compose",
    "compose.yml": "compose",
    "compose.yaml": "compose",
    "pnpm-workspace.yaml": "pnpm-workspace",
    "lerna.json": "lerna",
    "go.work": "gowork",
    "deno.json": "deno",
    "bun.lockb": "bun",
    "mix.exs": "mix",
    "package.swift": "swiftpm",
    "build.sbt": "sbt",
    "makefile": "makefile",
    "justfile": "justfile",
    "mkdocs.yml": "mkdocs",
    "book.toml": "mdbook",
    "_config.yml": "jekyll",
}

# Strong markers: their presence alone makes a directory a project root.
STRONG_MARKERS = {
    "package.json", "pyproject.toml", "requirements.txt", "setup.py", "pipfile", "environment.yml", "cargo.toml",
    "go.mod", "pom.xml", "build.gradle", "build.gradle.kts", "gemfile", "composer.json", "pubspec.yaml",
    "cmakelists.txt", "mix.exs", "package.swift", "build.sbt", "deno.json",
    "mkdocs.yml", "book.toml", "docusaurus.config.js", "docusaurus.config.ts", "_config.yml",
}
# Weak markers: count as a project only together with source files or another weak marker.
WEAK_MARKERS = {"dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml", "makefile",
                "justfile", "setup.cfg", "requirements-dev.txt", "readme.md"}
EXT_MARKERS = {".sln", ".csproj", ".fsproj", ".xcodeproj", ".xcworkspace"}


@dataclass
class Manifest:
    path: str
    kind: str
    name: str | None = None
    dependencies: list[str] = field(default_factory=list)
    dev_dependencies: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    workspaces: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def all_dependencies(self) -> list[str]:
        seen: list[str] = []
        for dep in self.dependencies + self.dev_dependencies:
            if dep not in seen:
                seen.append(dep)
        return seen


_PY_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _norm(name: str) -> str:
    return name.strip().strip('"\'').lower()


def _py_dep_name(spec: str) -> str | None:
    spec = spec.strip()
    if not spec or spec.startswith(("#", "-", "git+", "http")):
        return None
    m = _PY_NAME.match(spec)
    if not m:
        return None
    return m.group(1).lower().replace("_", "-")


def _limit(items: list[str], n: int = 400) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item[:120])
        if len(out) >= n:
            break
    return out


def parse_manifest(kind: str, relative_path: str, text: str) -> Manifest:
    m = Manifest(path=relative_path, kind=kind)
    try:
        parser = _PARSERS.get(kind)
        if parser:
            parser(m, text)
    except Exception:  # noqa: BLE001 - parsing must never break a scan
        m.extra["parse_error"] = True
    m.dependencies = _limit(m.dependencies)
    m.dev_dependencies = _limit(m.dev_dependencies)
    m.scripts = _limit(m.scripts, 100)
    m.workspaces = _limit(m.workspaces, 50)
    return m


def _parse_package_json(m: Manifest, text: str) -> None:
    data = json.loads(text)
    if not isinstance(data, dict):
        return
    if isinstance(data.get("name"), str):
        m.name = data["name"][:120]
    for key, target in (("dependencies", m.dependencies), ("peerDependencies", m.dependencies),
                        ("devDependencies", m.dev_dependencies)):
        deps = data.get(key)
        if isinstance(deps, dict):
            for dep, version in deps.items():
                target.append(_norm(str(dep)))
                if isinstance(version, str) and (version.startswith(("file:", "link:", "workspace:")) or version.startswith(("./", "../"))):
                    m.extra.setdefault("local_dependencies", []).append({"name": _norm(str(dep)), "spec": version[:200]})
    scripts = data.get("scripts")
    if isinstance(scripts, dict):
        m.scripts = [str(k) for k in scripts.keys()]
    ws = data.get("workspaces")
    if isinstance(ws, list):
        m.workspaces = [str(x) for x in ws if isinstance(x, str)]
    elif isinstance(ws, dict) and isinstance(ws.get("packages"), list):
        m.workspaces = [str(x) for x in ws["packages"] if isinstance(x, str)]
    for key in ("private", "type"):
        if key in data and isinstance(data[key], (str, bool)):
            m.extra[key] = data[key]
    if isinstance(data.get("engines"), dict):
        m.extra["engines"] = list(data["engines"].keys())[:10]
    if isinstance(data.get("main"), str):
        m.extra["main"] = data["main"][:200]


def _parse_pyproject(m: Manifest, text: str) -> None:
    data = tomllib.loads(text)
    project = data.get("project") if isinstance(data.get("project"), dict) else {}
    tool = data.get("tool") if isinstance(data.get("tool"), dict) else {}
    if isinstance(project.get("name"), str):
        m.name = project["name"][:120]
    for spec in project.get("dependencies", []) or []:
        if isinstance(spec, str):
            dep = _py_dep_name(spec)
            if dep:
                m.dependencies.append(dep)
    optional = project.get("optional-dependencies")
    if isinstance(optional, dict):
        for group in optional.values():
            for spec in group or []:
                if isinstance(spec, str):
                    dep = _py_dep_name(spec)
                    if dep:
                        m.dev_dependencies.append(dep)
    poetry = tool.get("poetry") if isinstance(tool.get("poetry"), dict) else {}
    if poetry:
        if isinstance(poetry.get("name"), str) and not m.name:
            m.name = poetry["name"][:120]
        for dep in (poetry.get("dependencies") or {}).keys():
            if dep.lower() != "python":
                m.dependencies.append(_norm(dep).replace("_", "-"))
        for dep in (poetry.get("dev-dependencies") or {}).keys():
            m.dev_dependencies.append(_norm(dep).replace("_", "-"))
        groups = poetry.get("group")
        if isinstance(groups, dict):
            for g in groups.values():
                if isinstance(g, dict):
                    for dep in (g.get("dependencies") or {}).keys():
                        m.dev_dependencies.append(_norm(dep).replace("_", "-"))
    uv = tool.get("uv") if isinstance(tool.get("uv"), dict) else {}
    for spec in uv.get("dev-dependencies", []) or []:
        if isinstance(spec, str):
            dep = _py_dep_name(spec)
            if dep:
                m.dev_dependencies.append(dep)
    if isinstance(project.get("scripts"), dict):
        m.scripts = list(project["scripts"].keys())
    if isinstance(tool, dict):
        m.extra["tools"] = [k for k in tool.keys()][:30]


def _parse_requirements(m: Manifest, text: str) -> None:
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("-e") or line.startswith("--"):
            if line.startswith("-e") and ("./" in line or ".." in line or line.endswith(".")):
                m.extra.setdefault("local_dependencies", []).append({"name": line[2:].strip()[:200], "spec": "editable"})
            continue
        dep = _py_dep_name(line)
        if dep:
            m.dependencies.append(dep)


def _parse_setup_py(m: Manifest, text: str) -> None:
    for match in re.finditer(r"['\"]([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:[<>=!~;\[]|['\"])", text):
        candidate = match.group(1).lower().replace("_", "-")
        if candidate not in {"setup", "name", "version", "install-requires"}:
            m.dependencies.append(candidate)
    name = re.search(r"name\s*=\s*['\"]([^'\"]+)['\"]", text)
    if name:
        m.name = name.group(1)[:120]


def _parse_setup_cfg(m: Manifest, text: str) -> None:
    in_deps = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("install_requires"):
            in_deps = True
            after = stripped.split("=", 1)[1] if "=" in stripped else ""
            dep = _py_dep_name(after)
            if dep:
                m.dependencies.append(dep)
            continue
        if in_deps:
            if line.startswith((" ", "\t")) and stripped:
                dep = _py_dep_name(stripped)
                if dep:
                    m.dependencies.append(dep)
            else:
                in_deps = False
        name = re.match(r"^name\s*=\s*(.+)$", stripped)
        if name and not m.name:
            m.name = name.group(1).strip()[:120]


def _parse_pipfile(m: Manifest, text: str) -> None:
    data = tomllib.loads(text)
    for dep in (data.get("packages") or {}).keys():
        m.dependencies.append(_norm(dep).replace("_", "-"))
    for dep in (data.get("dev-packages") or {}).keys():
        m.dev_dependencies.append(_norm(dep).replace("_", "-"))


def _parse_yaml_deps(m: Manifest, text: str, keys: tuple[str, ...]) -> None:
    """Tiny indentation-aware reader for `key:` list/map blocks. Not a YAML parser."""
    current: str | None = None
    base_indent = 0
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        key_match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", stripped)
        if current is not None and indent <= base_indent and not stripped.startswith("-"):
            current = None
        if current is None:
            if key_match and key_match.group(1) in keys and indent == 0 or (key_match and key_match.group(1) in keys and indent <= 2):
                current = key_match.group(1)
                base_indent = indent
                if key_match.group(1) == "name" and key_match.group(2):
                    m.name = key_match.group(2).strip().strip("\"'")[:120]
                    current = None
            elif key_match and key_match.group(1) == "name" and indent == 0 and key_match.group(2):
                m.name = key_match.group(2).strip().strip("\"'")[:120]
            continue
        if stripped.startswith("- "):
            item = stripped[2:].strip().strip("\"'")
            if item.startswith("pip:"):
                continue
            dep = _py_dep_name(item) if m.kind == "conda" else _norm(item.split(":")[0])
            if dep:
                (m.dev_dependencies if current == "dev_dependencies" else m.dependencies).append(dep)
        elif key_match and indent > base_indent:
            dep = _norm(key_match.group(1))
            (m.dev_dependencies if current == "dev_dependencies" else m.dependencies).append(dep)


def _parse_conda(m: Manifest, text: str) -> None:
    _parse_yaml_deps(m, text, ("dependencies",))
    pip_block = False
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("- pip:"):
            pip_block = True
            continue
        if pip_block:
            if s.startswith("- "):
                dep = _py_dep_name(s[2:])
                if dep:
                    m.dependencies.append(dep)
            else:
                pip_block = False


def _parse_pubspec(m: Manifest, text: str) -> None:
    _parse_yaml_deps(m, text, ("dependencies", "dev_dependencies"))


def _parse_cargo(m: Manifest, text: str) -> None:
    data = tomllib.loads(text)
    package = data.get("package") if isinstance(data.get("package"), dict) else {}
    if isinstance(package.get("name"), str):
        m.name = package["name"][:120]
    for key, target in (("dependencies", m.dependencies), ("build-dependencies", m.dependencies), ("dev-dependencies", m.dev_dependencies)):
        deps = data.get(key)
        if isinstance(deps, dict):
            for dep, spec in deps.items():
                target.append(_norm(dep))
                if isinstance(spec, dict) and isinstance(spec.get("path"), str):
                    m.extra.setdefault("local_dependencies", []).append({"name": _norm(dep), "spec": spec["path"][:200]})
    workspace = data.get("workspace")
    if isinstance(workspace, dict) and isinstance(workspace.get("members"), list):
        m.workspaces = [str(x) for x in workspace["members"] if isinstance(x, str)]
        m.extra["workspace"] = True
    target = data.get("target")
    if isinstance(target, dict):
        for cfg in target.values():
            if isinstance(cfg, dict) and isinstance(cfg.get("dependencies"), dict):
                m.dependencies.extend(_norm(d) for d in cfg["dependencies"].keys())


def _parse_gomod(m: Manifest, text: str) -> None:
    mod = re.search(r"^module\s+(\S+)", text, re.M)
    if mod:
        m.name = mod.group(1)[:120]
    for match in re.finditer(r"^\s*(?:require\s+)?([a-zA-Z0-9.\-_/]+\.[a-z]+/[^\s]+)\s+v[\d.]+", text, re.M):
        m.dependencies.append(match.group(1).lower())
    for match in re.finditer(r"^\s*([a-zA-Z0-9.\-_/]+/[^\s]+)\s+v[\d.]+[^\n]*$", text, re.M):
        m.dependencies.append(match.group(1).lower())


def _parse_gowork(m: Manifest, text: str) -> None:
    for match in re.finditer(r"^\s*(?:use\s+)?(\./[^\s)]+)", text, re.M):
        m.workspaces.append(match.group(1))


def _parse_pom(m: Manifest, text: str) -> None:
    artifact = re.search(r"<artifactId>([^<]+)</artifactId>", text)
    if artifact:
        m.name = artifact.group(1).strip()[:120]
    for dep in re.finditer(r"<dependency>(.*?)</dependency>", text, re.S):
        group = re.search(r"<groupId>([^<]+)</groupId>", dep.group(1))
        art = re.search(r"<artifactId>([^<]+)</artifactId>", dep.group(1))
        if art:
            name = art.group(1).strip().lower()
            if group:
                name = f"{group.group(1).strip().lower()}:{name}"
            m.dependencies.append(name)
    if re.search(r"<modules>", text):
        m.workspaces = re.findall(r"<module>([^<]+)</module>", text)


def _parse_gradle(m: Manifest, text: str) -> None:
    for match in re.finditer(r"(?:implementation|api|compile|testImplementation|runtimeOnly|kapt|annotationProcessor)\s*\(?\s*['\"]([^'\"]+)['\"]", text):
        parts = match.group(1).split(":")
        m.dependencies.append(":".join(parts[:2]).lower() if len(parts) >= 2 else match.group(1).lower())
    for match in re.finditer(r"id\s*\(?\s*['\"]([^'\"]+)['\"]", text):
        m.extra.setdefault("plugins", []).append(match.group(1).lower())


def _parse_gemfile(m: Manifest, text: str) -> None:
    for match in re.finditer(r"^\s*gem\s+['\"]([^'\"]+)['\"]", text, re.M):
        m.dependencies.append(match.group(1).lower())


def _parse_composer(m: Manifest, text: str) -> None:
    data = json.loads(text)
    if isinstance(data.get("name"), str):
        m.name = data["name"][:120]
    for key, target in (("require", m.dependencies), ("require-dev", m.dev_dependencies)):
        deps = data.get(key)
        if isinstance(deps, dict):
            target.extend(_norm(d) for d in deps.keys() if d.lower() != "php")


def _parse_cmake(m: Manifest, text: str) -> None:
    name = re.search(r"project\s*\(\s*([A-Za-z0-9_\-]+)", text, re.I)
    if name:
        m.name = name.group(1)[:120]
    for match in re.finditer(r"find_package\s*\(\s*([A-Za-z0-9_\-]+)", text, re.I):
        m.dependencies.append(match.group(1).lower())


def _parse_dockerfile(m: Manifest, text: str) -> None:
    for match in re.finditer(r"^\s*FROM\s+(?:--platform=\S+\s+)?([^\s]+)", text, re.M | re.I):
        m.extra.setdefault("images", []).append(match.group(1).lower()[:120])


def _parse_compose(m: Manifest, text: str) -> None:
    for match in re.finditer(r"^\s*image:\s*['\"]?([^\s'\"]+)", text, re.M):
        m.extra.setdefault("images", []).append(match.group(1).lower()[:120])
    services = re.search(r"^services:\s*$(.*?)(?=^\S|\Z)", text, re.M | re.S)
    if services:
        m.extra["services"] = [s for s in re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", services.group(1), re.M)][:40]


def _parse_pnpm_workspace(m: Manifest, text: str) -> None:
    for match in re.finditer(r"^\s*-\s*['\"]?([^'\"\n]+?)['\"]?\s*$", text, re.M):
        m.workspaces.append(match.group(1).strip())


def _parse_lerna(m: Manifest, text: str) -> None:
    data = json.loads(text)
    if isinstance(data.get("packages"), list):
        m.workspaces = [str(x) for x in data["packages"] if isinstance(x, str)]


def _parse_deno(m: Manifest, text: str) -> None:
    data = json.loads(text)
    if isinstance(data.get("name"), str):
        m.name = data["name"][:120]
    imports = data.get("imports")
    if isinstance(imports, dict):
        m.dependencies.extend(_norm(k) for k in imports.keys())
    tasks = data.get("tasks")
    if isinstance(tasks, dict):
        m.scripts = list(tasks.keys())


def _parse_mix(m: Manifest, text: str) -> None:
    for match in re.finditer(r"\{\s*:([a-z0-9_]+)\s*,", text):
        m.dependencies.append(match.group(1))
    app = re.search(r"app:\s*:([a-z0-9_]+)", text)
    if app:
        m.name = app.group(1)


def _parse_swiftpm(m: Manifest, text: str) -> None:
    name = re.search(r"name:\s*\"([^\"]+)\"", text)
    if name:
        m.name = name.group(1)[:120]
    for match in re.finditer(r"url:\s*\"[^\"]*/([^\"/]+?)(?:\.git)?\"", text):
        m.dependencies.append(match.group(1).lower())


def _parse_sbt(m: Manifest, text: str) -> None:
    for match in re.finditer(r"\"([A-Za-z0-9_.\-]+)\"\s*%%?\s*\"([A-Za-z0-9_.\-]+)\"", text):
        m.dependencies.append(f"{match.group(1)}:{match.group(2)}".lower())


def _parse_makefile(m: Manifest, text: str) -> None:
    m.scripts = [t for t in re.findall(r"^([A-Za-z0-9_\-]+):", text, re.M) if t not in {"PHONY"}][:60]


def parse_csproj(relative_path: str, text: str) -> Manifest:
    m = Manifest(path=relative_path, kind="csproj")
    try:
        for match in re.finditer(r"<PackageReference\s+Include=\"([^\"]+)\"", text):
            m.dependencies.append(match.group(1).lower())
        fw = re.search(r"<TargetFrameworks?>([^<]+)</TargetFrameworks?>", text)
        if fw:
            m.extra["target_framework"] = fw.group(1)[:80]
        sdk = re.search(r"<Project\s+Sdk=\"([^\"]+)\"", text)
        if sdk:
            m.extra["sdk"] = sdk.group(1)[:80]
    except Exception:  # noqa: BLE001
        m.extra["parse_error"] = True
    return m


_PARSERS = {
    "package.json": _parse_package_json,
    "pyproject": _parse_pyproject,
    "requirements": _parse_requirements,
    "setup.py": _parse_setup_py,
    "setup.cfg": _parse_setup_cfg,
    "pipfile": _parse_pipfile,
    "conda": _parse_conda,
    "cargo": _parse_cargo,
    "gomod": _parse_gomod,
    "gowork": _parse_gowork,
    "pom": _parse_pom,
    "gradle": _parse_gradle,
    "gemfile": _parse_gemfile,
    "composer": _parse_composer,
    "pubspec": _parse_pubspec,
    "cmake": _parse_cmake,
    "dockerfile": _parse_dockerfile,
    "compose": _parse_compose,
    "pnpm-workspace": _parse_pnpm_workspace,
    "lerna": _parse_lerna,
    "deno": _parse_deno,
    "mix": _parse_mix,
    "swiftpm": _parse_swiftpm,
    "sbt": _parse_sbt,
    "makefile": _parse_makefile,
    "justfile": _parse_makefile,
}
