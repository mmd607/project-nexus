"""Explainable classification: every category in the fixture is found with evidence; nothing is invented."""
from __future__ import annotations

from nexus import repo
from nexus.classifier import classify, heuristic_description
from nexus.manifests import parse_manifest
from nexus.model import CATEGORIES, FileEntry, ProjectFacts

EXPECTED = {
    "py-ml-cli": ["AI/ML", "Data"], "react-app": ["Frontend"], "rust-service": ["Backend"], "mono-shop": ["Full-stack"],
    "outer-repo": ["Backend"], "net-recon": ["Security"], "flutter-notes": ["Mobile"],
    "team-handbook": ["Documentation"], "prompt-library": ["Prompt Engineering"], "infra-cluster": ["DevOps"], "sales-analytics": ["Data"],
    "landing-site": ["Frontend"], "smart-store": ["Full-stack", "AI/ML"],
}
NOT_EXPECTED = {"flutter-notes": ["Documentation"], "sales-analytics": ["Backend"], "react-app": ["Backend"], "team-handbook": ["Frontend"],
                "smart-store": ["Documentation"]}


def by_rel(db):
    items, _ = repo.list_projects(db)
    return {p["relative_path"]: p for p in items}


def test_fixture_categories(scanned):
    projects = by_rel(scanned["db"])
    for rel, cats in EXPECTED.items():
        for cat in cats:
            assert cat in projects[rel]["categories"], (rel, projects[rel]["categories"])
    for rel, cats in NOT_EXPECTED.items():
        for cat in cats:
            assert cat not in projects[rel]["categories"], (rel, projects[rel]["categories"])
    assert projects["old-scripts"]["categories"] == ["Other"]


def test_every_category_has_evidence(scanned):
    projects = by_rel(scanned["db"])
    for p in projects.values():
        details = [c for c in p["category_details"] if c["source"] == "rules"]
        for c in details:
            assert c["evidence"], (p["relative_path"], c)
            assert all(0 <= e["weight"] <= 1 for e in c["evidence"])
            assert 0 <= c["confidence"] <= 0.97
        assert all(c in CATEGORIES for c in p["categories"])


def test_technologies_detected_with_evidence(scanned):
    db = scanned["db"]
    projects = by_rel(db)
    techs = {t["name"]: t for t in repo.get_project(db, projects["react-app"]["id"])["technologies"]}
    assert "React" in techs and "Vite" in techs and "Tailwind CSS" in techs
    assert techs["React"]["evidence"][0]["detail"].startswith("react in package.json")
    techs = {t["name"] for t in repo.get_project(db, projects["rust-service"]["id"])["technologies"]}
    assert {"Axum", "Tokio", "Rust", "Docker"} <= techs
    techs = {t["name"] for t in repo.get_project(db, projects["infra-cluster"]["id"])["technologies"]}
    assert {"Terraform", "Kubernetes", "GitHub Actions", "Docker"} <= techs
    techs = {t["name"] for t in repo.get_project(db, projects["net-recon"]["id"])["technologies"]}
    assert {"Scapy", "Impacket", "Nmap"} <= techs


def test_readme_description_and_injection_is_data(scanned):
    db = scanned["db"]
    projects = by_rel(db)
    p = repo.get_project(db, projects["py-ml-cli"]["id"])
    assert p["description_source"] == "readme"
    assert p["description"].startswith("A command line tool")
    # The injection line is ordinary text: it must not become the description, nor change settings.
    assert "ignore all previous" not in p["description"]
    assert scanned["settings"].section("ai")["base_url"] == "http://127.0.0.1:11434"


def test_unknown_project_is_other_with_honest_summary():
    facts = ProjectFacts(name="mystery", relative_path="mystery", files=[FileEntry("a.xyz", ".xyz", 10, 0, "other")],
                         dir_names=set(), top_level={"a.xyz"}, languages={}, manifests=[])
    cats, techs = classify(facts)
    assert [c.name for c in cats] == ["Other"]
    assert cats[0].evidence[0].rule == "fallback"
    desc = heuristic_description(facts, cats, techs, None)
    assert "1 files" in desc and "Other" not in desc


def test_name_keyword_alone_is_not_enough():
    facts = ProjectFacts(name="my-notes-app", relative_path="my-notes-app", files=[FileEntry("main.py", ".py", 10, 0, "source")],
                         dir_names=set(), top_level={"main.py"}, languages={"Python": {"files": 1, "bytes": 10}}, manifests=[])
    cats, _ = classify(facts)
    assert "Documentation" not in [c.name for c in cats]


def test_manifest_parsers_are_defensive():
    m = parse_manifest("package.json", "package.json", "{not json")
    assert m.extra.get("parse_error") and m.dependencies == []
    m = parse_manifest("pyproject", "pyproject.toml", "[project]\nname='x'\ndependencies=['fastapi>=0.1', 'Uvicorn[standard]']\n")
    assert m.dependencies == ["fastapi", "uvicorn"] and m.name == "x"
    m = parse_manifest("requirements", "requirements.txt", "# c\nDjango==4.2\n-r other.txt\nnumpy>=1\n")
    assert m.dependencies == ["django", "numpy"]
    m = parse_manifest("cargo", "Cargo.toml", "[package]\nname='t'\n[dependencies]\nserde='1'\nlocal={path='../lib'}\n[workspace]\nmembers=['crates/*']\n")
    assert "serde" in m.dependencies and m.workspaces == ["crates/*"] and m.extra["local_dependencies"][0]["name"] == "local"
    m = parse_manifest("gomod", "go.mod", "module a\n\nrequire (\n\tgithub.com/gin-gonic/gin v1.9.1\n)\n")
    assert "github.com/gin-gonic/gin" in m.dependencies
    m = parse_manifest("compose", "docker-compose.yml", "services:\n  db:\n    image: postgres:16\n  web:\n    image: nginx\n")
    assert m.extra["images"] == ["postgres:16", "nginx"] and m.extra["services"] == ["db", "web"]
