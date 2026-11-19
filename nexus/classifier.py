"""Deterministic, explainable classification.

Every category and technology carries the list of evidence that produced it.
Weights combine as ``1 - Π(1 - w)`` so several weak signals can add up, but a
single strong signal (a framework dependency) is enough on its own.

Nothing here reads file contents: it only sees names, extensions, manifest
dependency names and a README excerpt captured by the scanner.
"""
from __future__ import annotations

import re
from collections import defaultdict

from .languages import CODE_LANGUAGES
from .model import CategoryDetection, Evidence, ProjectFacts, TechDetection
from .tech import AI, BE, DATA, DOC, FE, MOB, OPS, PE, SEC, lookup, lookup_image

INCLUDE_THRESHOLD = 0.45
NAME_ONLY_THRESHOLD = 0.5
MAX_CATEGORIES = 4

# Keywords that only apply to *names* (folder, manifest name, README title) — never to free text.
NAME_KEYWORDS: dict[str, list[tuple[str, float]]] = {
    AI: [("llm", .45), ("rag", .45), ("gpt", .4), ("neural", .45), ("deep-learning", .5), ("deep_learning", .5), ("machine-learning", .5),
         ("machine_learning", .5), ("ml-", .3), ("-ml", .3), ("ai-", .3), ("-ai", .3), ("chatbot", .4), ("yolo", .5), ("detection", .3),
         ("classifier", .35), ("recognition", .35), ("nlp", .45), ("vision", .3), ("embedding", .4), ("transformer", .4), ("agent", .3),
         ("semantic", .3), ("predict", .3), ("forecast", .3), ("inference", .4), ("model", .2), ("speech", .3), ("whisper", .4), ("diffusion", .45)],
    SEC: [("security", .5), ("pentest", .6), ("exploit", .6), ("cve-", .6), ("ctf", .55), ("vuln", .55), ("malware", .6), ("forensic", .55),
          ("honeypot", .6), ("firewall", .5), ("siem", .55), ("threat", .45), ("recon", .5), ("osint", .55), ("phish", .55), ("crypt", .3),
          ("cipher", .4), ("auth", .2), ("payload", .4), ("scanner", .35), ("sniff", .5), ("ids-", .4), ("waf", .5), ("hack", .45), ("red-team", .6), ("blue-team", .6)],
    BE: [("backend", .55), ("api", .4), ("server", .4), ("service", .3), ("microservice", .5), ("gateway", .4), ("bot", .3), ("webhook", .4)],
    FE: [("frontend", .55), ("front-end", .55), ("ui", .3), ("website", .4), ("web-app", .3), ("landing", .4), ("portfolio", .4), ("dashboard", .35),
         ("theme", .3), ("client", .25), ("widget", .3), ("design-system", .5)],
    DATA: [("data", .3), ("dataset", .4), ("analytics", .45), ("analysis", .4), ("etl", .55), ("pipeline", .3), ("warehouse", .5), ("scrap", .4),
           ("crawler", .4), ("dashboard", .3), ("report", .25), ("statistic", .4), ("visualization", .4), ("churn", .4), ("tracking", .25)],
    OPS: [("devops", .6), ("infra", .5), ("deploy", .45), ("terraform", .6), ("ansible", .6), ("kubernetes", .6), ("k8s", .6), ("docker", .35),
          ("ci-cd", .5), ("cicd", .5), ("helm", .5), ("monitoring", .4), ("automation", .3), ("provision", .45)],
    MOB: [("mobile", .55), ("android", .6), ("ios-", .5), ("flutter", .6), ("react-native", .6), ("app-", .15)],
    DOC: [("docs", .5), ("documentation", .6), ("wiki", .5), ("notes", .3), ("handbook", .5), ("guide", .35), ("book", .35), ("tutorial", .35), ("knowledge", .35)],
    PE: [("prompt", .6), ("prompts", .65), ("prompt-engineering", .8), ("few-shot", .6), ("chain-of-thought", .6), ("persona", .3), ("agentic", .4),
         ("system-prompt", .7), ("instruction", .3)],
}

README_KEYWORDS: dict[str, list[tuple[str, float]]] = {
    AI: [("machine learning", .4), ("deep learning", .45), ("neural network", .45), ("large language model", .45), ("llm", .4), ("retrieval-augmented", .45),
         ("rag ", .35), ("computer vision", .45), ("object detection", .45), ("transformer", .3), ("embedding", .35), ("fine-tun", .45), ("inference", .3),
         ("model training", .4), ("classification model", .35), ("openai", .3), ("gpt", .25), ("yolo", .4), ("whisper", .35), ("langchain", .4)],
    SEC: [("penetration test", .55), ("vulnerabilit", .5), ("exploit", .45), ("malware", .5), ("threat", .35), ("encryption", .3), ("security", .35),
          ("forensic", .5), ("ctf", .45), ("osint", .5), ("intrusion", .5), ("attack", .3)],
    BE: [("rest api", .45), ("restful", .4), ("graphql api", .45), ("backend", .45), ("microservice", .45), ("endpoint", .3), ("web server", .4), ("websocket", .3)],
    FE: [("user interface", .35), ("frontend", .45), ("front-end", .45), ("single page", .4), ("responsive", .3), ("landing page", .45), ("web app", .25), ("component", .2)],
    DATA: [("data analysis", .45), ("data pipeline", .5), ("dataset", .35), ("etl", .45), ("analytics", .4), ("visualization", .35), ("dashboard", .3),
           ("data warehouse", .5), ("scrap", .35), ("statistic", .35), ("pandas", .35), ("notebook", .3)],
    OPS: [("infrastructure as code", .55), ("ci/cd", .5), ("deployment", .35), ("kubernetes", .5), ("terraform", .55), ("ansible", .55), ("docker compose", .3), ("monitoring", .35)],
    MOB: [("android", .5), ("ios app", .5), ("mobile app", .55), ("flutter", .55), ("react native", .55), ("play store", .5), ("app store", .5)],
    DOC: [("documentation", .45), ("knowledge base", .45), ("handbook", .45), ("cheat sheet", .45), ("reading notes", .4), ("tutorial", .35), ("wiki", .4)],
    PE: [("prompt engineering", .8), ("system prompt", .65), ("prompt template", .65), ("few-shot", .55), ("chain of thought", .55), ("prompt", .4),
         ("agent", .25), ("persona", .3), ("instruction", .2)],
}

GENERIC_NAMES = {"backend", "frontend", "api", "web", "app", "server", "client", "src", "core", "lib", "packages", "apps",
                 "services", "service", "ui", "mobile", "docs", "common", "shared", "utils", "main", "project", "new folder", "test", "tests"}


def _combine(weights: list[float]) -> float:
    p = 1.0
    for w in weights:
        p *= (1.0 - max(0.0, min(1.0, w)))
    return min(0.97, 1.0 - p)


def _slug(text: str) -> str:
    return re.sub(r"[\s_]+", "-", text.strip().lower())


class Collector:
    def __init__(self) -> None:
        self.categories: dict[str, list[Evidence]] = defaultdict(list)
        self.techs: dict[str, TechDetection] = {}

    def category(self, name: str, rule: str, detail: str, weight: float) -> None:
        if weight <= 0:
            return
        self.categories[name].append(Evidence(rule, detail, weight))

    def tech(self, name: str, kind: str, rule: str, detail: str, confidence: float, hints: dict[str, float] | None = None) -> None:
        existing = self.techs.get(name)
        ev = Evidence(rule, detail, confidence)
        if existing:
            existing.evidence.append(ev)
            existing.confidence = max(existing.confidence, confidence)
        else:
            self.techs[name] = TechDetection(name, kind, confidence, [ev])
        for cat, weight in (hints or {}).items():
            self.category(cat, "technology", f"{name} ({detail})", weight)


def _scan_dependencies(facts: ProjectFacts, c: Collector) -> None:
    seen: set[tuple[str, str]] = set()
    for manifest in facts.manifests:
        for dep in manifest.all_dependencies:
            entry = lookup(dep)
            if not entry:
                continue
            name, kind, hints = entry
            key = (name, manifest.path)
            if key in seen:
                continue
            seen.add(key)
            c.tech(name, kind, "dependency", f"{dep} in {manifest.path}", 0.9, hints)
        for image in manifest.extra.get("images", []) or []:
            entry = lookup_image(image)
            if entry:
                name, kind, hints = entry
                c.tech(name, kind, "container-image", f"image {image} in {manifest.path}", 0.6, hints)
        for plugin in manifest.extra.get("plugins", []) or []:
            if "android" in plugin:
                c.tech("Android", "platform", "gradle-plugin", f"plugin {plugin} in {manifest.path}", 0.85, {MOB: .85})
            if "kotlin" in plugin:
                c.tech("Kotlin", "language", "gradle-plugin", f"plugin {plugin} in {manifest.path}", 0.8, {})
        sdk = manifest.extra.get("sdk")
        if isinstance(sdk, str):
            if "web" in sdk.lower():
                c.tech("ASP.NET Core", "framework", "project-sdk", f"Sdk {sdk} in {manifest.path}", 0.85, {BE: .8})
            if "maui" in sdk.lower():
                c.tech(".NET MAUI", "framework", "project-sdk", f"Sdk {sdk} in {manifest.path}", 0.85, {MOB: .85})
        if manifest.kind == "dockerfile":
            c.tech("Docker", "tool", "file", manifest.path, 0.8, {OPS: .2})
        if manifest.kind == "compose":
            services = manifest.extra.get("services") or []
            c.tech("Docker Compose", "tool", "file", f"{manifest.path} ({len(services)} services)" if services else manifest.path, 0.8, {OPS: .3})
        if manifest.kind == "cmake":
            c.tech("CMake", "tool", "file", manifest.path, 0.8, {})
        if manifest.kind in {"makefile", "justfile"}:
            c.tech("Make" if manifest.kind == "makefile" else "just", "tool", "file", manifest.path, 0.6, {})
        if manifest.kind == "mkdocs":
            c.tech("MkDocs", "tool", "manifest", manifest.path, 0.9, {DOC: .85})
        if manifest.kind == "mdbook":
            c.tech("mdBook", "tool", "manifest", manifest.path, 0.9, {DOC: .85})
        if manifest.kind == "jekyll":
            c.tech("Jekyll", "tool", "manifest", manifest.path, 0.8, {DOC: .5, FE: .3})
        if manifest.kind == "pubspec":
            c.tech("Dart", "language", "manifest", manifest.path, 0.9, {})
        if manifest.kind == "cargo":
            c.tech("Cargo", "tool", "manifest", manifest.path, 0.9, {})
        if manifest.kind == "gomod":
            c.tech("Go modules", "tool", "manifest", manifest.path, 0.9, {})
        if manifest.kind == "pom":
            c.tech("Maven", "tool", "manifest", manifest.path, 0.9, {})
        if manifest.kind == "gradle":
            c.tech("Gradle", "tool", "manifest", manifest.path, 0.9, {})
        if manifest.kind == "package.json":
            c.tech("npm / Node.js", "tool", "manifest", manifest.path, 0.9, {})
            for script in manifest.scripts:
                if script in {"build", "dev", "start"}:
                    continue
        if manifest.kind in {"pyproject", "requirements", "pipfile", "conda", "setup.py"}:
            c.tech("pip / Python packaging", "tool", "manifest", manifest.path, 0.9, {})
            if manifest.kind == "pyproject":
                for tool in manifest.extra.get("tools", []) or []:
                    if tool == "poetry":
                        c.tech("Poetry", "tool", "manifest", "[tool.poetry] in pyproject.toml", 0.9, {})
                    if tool == "uv":
                        c.tech("uv", "tool", "manifest", "[tool.uv] in pyproject.toml", 0.9, {})


def _scan_files(facts: ProjectFacts, c: Collector) -> None:
    dirs = facts.dir_names
    top = facts.top_level
    kinds: dict[str, int] = defaultdict(int)
    ext_counts: dict[str, int] = defaultdict(int)
    names: set[str] = set()
    for f in facts.files:
        kinds[f.kind] += 1
        ext_counts[f.extension] += 1
        names.add(f.relative_path.replace("\\", "/").split("/")[-1].lower())
    total = max(1, len(facts.files))

    # Languages are measured, confidence 1.0
    for lang, stats in facts.languages.items():
        if lang in CODE_LANGUAGES and stats["files"] > 0:
            c.tech(lang, "language", "files", f"{stats['files']} files", 1.0, {})

    def has_any(*items: str) -> bool:
        return any(i in names or i in dirs for i in items)

    # --- DevOps / infra files
    if ".github" in dirs and "workflows" in dirs:
        c.tech("GitHub Actions", "tool", "directory", ".github/workflows", 0.8, {OPS: .4})
    if ".gitlab-ci.yml" in names:
        c.tech("GitLab CI", "tool", "file", ".gitlab-ci.yml", 0.8, {OPS: .5})
    if "jenkinsfile" in names:
        c.tech("Jenkins", "tool", "file", "Jenkinsfile", 0.8, {OPS: .5})
    if "azure-pipelines.yml" in names:
        c.tech("Azure Pipelines", "tool", "file", "azure-pipelines.yml", 0.8, {OPS: .5})
    if ".circleci" in dirs:
        c.tech("CircleCI", "tool", "directory", ".circleci", 0.8, {OPS: .5})
    if ext_counts.get(".tf", 0):
        c.tech("Terraform", "tool", "files", f"{ext_counts['.tf']} .tf files", 0.9, {OPS: .8})
    if "chart.yaml" in names and ("templates" in dirs):
        c.tech("Helm", "tool", "file", "Chart.yaml + templates/", 0.85, {OPS: .7})
    if ("k8s" in dirs or "kubernetes" in dirs or "manifests" in dirs) and (ext_counts.get(".yaml", 0) + ext_counts.get(".yml", 0)) > 0:
        c.tech("Kubernetes", "platform", "directory", "k8s/kubernetes manifests", 0.7, {OPS: .55})
    if "ansible.cfg" in names or ("playbooks" in dirs) or ("roles" in dirs and (ext_counts.get(".yml", 0) > 3)):
        c.tech("Ansible", "tool", "files", "ansible.cfg / playbooks", 0.8, {OPS: .7})
    if "vagrantfile" in names:
        c.tech("Vagrant", "tool", "file", "Vagrantfile", 0.8, {OPS: .6})
    if "serverless.yml" in names or "serverless.yaml" in names:
        c.tech("Serverless Framework", "tool", "file", "serverless.yml", 0.8, {OPS: .55, BE: .3})
    if "nginx.conf" in names:
        c.tech("Nginx", "tool", "file", "nginx.conf", 0.7, {OPS: .3, BE: .2})
    if "procfile" in names:
        c.tech("Heroku (Procfile)", "platform", "file", "Procfile", 0.6, {OPS: .3, BE: .3})
    if "fly.toml" in names or "render.yaml" in names or "railway.json" in names or "vercel.json" in names or "netlify.toml" in names:
        c.category(OPS, "file", "deployment config (fly/render/railway/vercel/netlify)", 0.3)

    # --- AI / ML files
    nb = ext_counts.get(".ipynb", 0)
    if nb:
        c.tech("Jupyter", "tool", "files", f"{nb} notebooks", 0.9, {DATA: .45 if nb < 5 else .6, AI: .3 if nb < 5 else .4})
    model_files = kinds.get("model", 0)
    if model_files:
        c.category(AI, "files", f"{model_files} model weight files (.pt/.onnx/.safetensors/…)", .6)
    for hint in ("train.py", "training.py", "inference.py", "predict.py", "model.py", "models.py", "evaluate.py", "finetune.py", "fine_tune.py"):
        if hint in names:
            c.category(AI, "file", hint, .3 if hint not in {"models.py"} else .12)
    for d in ("checkpoints", "weights", "embeddings", "notebooks", "experiments"):
        if d in dirs:
            c.category(AI if d != "notebooks" else DATA, "directory", f"{d}/", .35)
    if "models" in dirs and (model_files or nb):
        c.category(AI, "directory", "models/ with model files", .3)
    if ext_counts.get(".gguf", 0) or ext_counts.get(".safetensors", 0):
        c.tech("Local LLM weights", "platform", "files", ".gguf/.safetensors present", 0.8, {AI: .6})

    # --- Prompt engineering / agent assets
    prompt_files = kinds.get("prompt", 0)
    if "prompts" in dirs or "prompt_templates" in dirs or "prompt-templates" in dirs:
        c.category(PE, "directory", "prompts/ directory", .7)
    if prompt_files >= 2:
        c.category(PE, "files", f"{prompt_files} prompt/template files", min(.7, .25 + prompt_files * .1))
    elif prompt_files == 1:
        c.category(PE, "files", "1 prompt/template file", .25)
    for marker in ("claude.md", "agents.md", "agent.md", "gemini.md", "copilot-instructions.md", ".cursorrules", "system_prompt.md", "system-prompt.md", "prompt.md", "prompts.md"):
        if marker in names:
            c.category(PE, "file", marker, .45)
    if ".claude" in dirs or ".cursor" in dirs or "skills" in dirs and "skill.md" in names:
        c.category(PE, "directory", ".claude/.cursor agent configuration", .45)

    # --- Data
    data_files = kinds.get("data", 0)
    if data_files:
        c.category(DATA, "files", f"{data_files} data files (csv/parquet/sqlite/…)", min(.55, .2 + data_files * .05))
    if "data" in dirs or "datasets" in dirs:
        c.category(DATA, "directory", "data/ or datasets/", .3)
    if ext_counts.get(".sql", 0) >= 3:
        c.category(DATA, "files", f"{ext_counts['.sql']} SQL files", .4)
    if "dbt_project.yml" in names:
        c.tech("dbt", "tool", "file", "dbt_project.yml", 0.9, {DATA: .85})
    if "dags" in dirs:
        c.tech("Apache Airflow", "framework", "directory", "dags/", 0.6, {DATA: .6})

    # --- Backend
    if "manage.py" in names:
        c.tech("Django", "framework", "file", "manage.py", 0.85, {BE: .8})
    for d in ("routes", "routers", "controllers", "handlers", "endpoints", "middleware", "middlewares"):
        if d in dirs:
            c.category(BE, "directory", f"{d}/", .35)
    if "api" in dirs:
        c.category(BE, "directory", "api/", .3)
    if "migrations" in dirs or "alembic.ini" in names or "alembic" in dirs:
        c.category(BE, "directory", "database migrations", .3)
    if "schema.prisma" in names:
        c.tech("Prisma", "tool", "file", "schema.prisma", 0.85, {BE: .5})
    if ext_counts.get(".proto", 0):
        c.tech("gRPC / Protocol Buffers", "library", "files", f"{ext_counts['.proto']} .proto files", 0.8, {BE: .45})
    if has_any("openapi.yaml", "openapi.yml", "openapi.json", "swagger.yaml", "swagger.json"):
        c.tech("OpenAPI", "tool", "file", "openapi/swagger spec", 0.8, {BE: .5})
    if ext_counts.get(".graphql", 0) or ext_counts.get(".gql", 0):
        c.tech("GraphQL", "library", "files", ".graphql schema files", 0.7, {BE: .4})
    for hint in ("server.py", "server.js", "server.ts", "app.py", "main.py", "wsgi.py", "asgi.py", "index.js", "index.ts", "main.go", "main.rs"):
        if hint in top:
            c.category(BE, "file", hint, .18)

    # --- Frontend
    if "index.html" in top and (ext_counts.get(".css", 0) or ext_counts.get(".js", 0)):
        c.category(FE, "files", "index.html + css/js at root", .45)
    if "public" in dirs and "src" in dirs and (ext_counts.get(".tsx", 0) or ext_counts.get(".jsx", 0) or ext_counts.get(".vue", 0)):
        c.category(FE, "directory", "public/ + src/ with component files", .35)
    if ext_counts.get(".tsx", 0) + ext_counts.get(".jsx", 0) >= 3:
        c.category(FE, "files", f"{ext_counts.get('.tsx', 0) + ext_counts.get('.jsx', 0)} JSX/TSX components", .4)
    if ext_counts.get(".vue", 0) or ext_counts.get(".svelte", 0):
        c.category(FE, "files", "Vue/Svelte single-file components", .5)
    if (ext_counts.get(".css", 0) + ext_counts.get(".scss", 0)) >= 3:
        c.category(FE, "files", "stylesheets", .2)
    for cfg, tech in (("tailwind.config.js", "Tailwind CSS"), ("tailwind.config.ts", "Tailwind CSS"), ("vite.config.js", "Vite"), ("vite.config.ts", "Vite"),
                      ("next.config.js", "Next.js"), ("next.config.mjs", "Next.js"), ("next.config.ts", "Next.js"), ("angular.json", "Angular"),
                      ("svelte.config.js", "Svelte"), ("nuxt.config.ts", "Nuxt"), ("nuxt.config.js", "Nuxt"), ("astro.config.mjs", "Astro"),
                      ("webpack.config.js", "webpack"), ("postcss.config.js", "PostCSS"), ("remix.config.js", "Remix")):
        if cfg in names:
            hints = {FE: .55}
            if tech in {"Next.js", "Nuxt", "Remix"}:
                hints = {FE: .6, BE: .4}
            c.tech(tech, "framework" if tech not in {"Vite", "webpack", "PostCSS"} else "tool", "file", cfg, 0.85, hints)
    if "electron" in dirs or "electron-builder.yml" in names:
        c.tech("Electron", "framework", "directory", "electron/", 0.7, {FE: .5})
    if "src-tauri" in dirs:
        c.tech("Tauri", "framework", "directory", "src-tauri/", 0.85, {FE: .55})

    # --- Mobile
    if "androidmanifest.xml" in names:
        c.tech("Android", "platform", "file", "AndroidManifest.xml", 0.9, {MOB: .8})
    if "android" in dirs and "ios" in dirs:
        c.category(MOB, "directory", "android/ + ios/ folders", .6)
    if ext_counts.get(".xcodeproj", 0) or "podfile" in names or "info.plist" in names:
        c.tech("iOS (Xcode)", "platform", "files", "Xcode project / Podfile / Info.plist", 0.85, {MOB: .8})
    if ext_counts.get(".swift", 0) >= 3:
        c.category(MOB, "files", f"{ext_counts['.swift']} Swift files", .5)
    if ext_counts.get(".kt", 0) >= 3 and ("android" in dirs or "androidmanifest.xml" in names):
        c.category(MOB, "files", "Kotlin sources with Android layout", .5)
    if ext_counts.get(".dart", 0) >= 2:
        c.category(MOB, "files", f"{ext_counts['.dart']} Dart files", .3)

    # --- Documentation
    doc_files = kinds.get("doc", 0)
    source_files = kinds.get("source", 0) + kinds.get("test", 0) + kinds.get("notebook", 0)
    if doc_files and source_files == 0 and doc_files / total >= 0.5:
        if facts.child_names:
            c.category(DOC, "files", f"{doc_files} documents at the top level (code lives in sub-projects)", .3)
        else:
            c.category(DOC, "files", f"{doc_files} documents and no source files", .8)
    elif doc_files >= 10 and doc_files / total >= 0.4:
        c.category(DOC, "files", f"{doc_files} documents ({doc_files * 100 // total}% of files)", .45)
    if "docusaurus.config.js" in names or "docusaurus.config.ts" in names:
        c.tech("Docusaurus", "framework", "file", "docusaurus.config.*", 0.9, {DOC: .85})
    if "docs" in dirs and "conf.py" in names:
        c.tech("Sphinx", "tool", "file", "docs/conf.py", 0.8, {DOC: .8})
    if "docs" in top and doc_files >= 3:
        c.category(DOC, "directory", f"docs/ with {doc_files} documents", .2)

    # --- Security files
    for d in ("exploits", "payloads", "wordlists", "shellcode", "pentest", "recon", "forensics", "malware", "yara", "rules", "signatures"):
        if d in dirs and d not in {"rules"}:
            c.category(SEC, "directory", f"{d}/", .5)
    if ext_counts.get(".yar", 0) or ext_counts.get(".yara", 0):
        c.tech("YARA", "tool", "files", ".yar rules", 0.85, {SEC: .8})
    if ext_counts.get(".pcap", 0) or ext_counts.get(".pcapng", 0):
        c.category(SEC, "files", "packet captures (.pcap)", .55)
    if ext_counts.get(".sol", 0):
        c.tech("Solidity", "language", "files", f"{ext_counts['.sol']} .sol contracts", 0.9, {BE: .3, SEC: .2})

    # --- Tests / quality (technologies only)
    if kinds.get("test", 0):
        c.tech("Automated tests", "practice", "files", f"{kinds['test']} test files", 0.9, {})
    if ".pre-commit-config.yaml" in names:
        c.tech("pre-commit", "tool", "file", ".pre-commit-config.yaml", 0.9, {})
    if "readme.md" in top or "readme.rst" in top or "readme.txt" in top or "readme" in top:
        c.tech("README", "practice", "file", "README present", 1.0, {})
    if "license" in top or "license.md" in top or "license.txt" in top:
        c.tech("License file", "practice", "file", "LICENSE present", 1.0, {})


def _scan_names(facts: ProjectFacts, c: Collector) -> None:
    candidates: list[tuple[str, str]] = [("folder name", _slug(facts.name))]
    for m in facts.manifests:
        if m.name:
            candidates.append((f"name in {m.path}", _slug(m.name)))
    if facts.readme_title:
        candidates.append(("README title", _slug(facts.readme_title)))
    for cat, keywords in NAME_KEYWORDS.items():
        best: dict[str, tuple[str, float]] = {}
        for source, text in candidates:
            padded = f"-{text}-"
            for kw, weight in keywords:
                needle = kw if kw.startswith("-") or kw.endswith("-") else f"-{kw}"
                if needle in padded or (len(kw) > 4 and kw in text):
                    if kw not in best or best[kw][1] < weight:
                        best[kw] = (source, weight)
        for kw, (source, weight) in list(best.items())[:3]:
            c.category(cat, "name-keyword", f"“{kw}” in {source}", weight)


def _scan_readme(facts: ProjectFacts, c: Collector) -> None:
    if not facts.readme_excerpt:
        return
    text = facts.readme_excerpt.lower()[:3000]
    for cat, keywords in README_KEYWORDS.items():
        hits = [(kw, w) for kw, w in keywords if kw in text]
        hits.sort(key=lambda kv: -kv[1])
        for kw, w in hits[:2]:
            c.category(cat, "readme-keyword", f"“{kw.strip()}” in README excerpt", w * 0.8)


COMPONENT_WEIGHT: dict[str, float] = {
    "Frontend": .55, "Backend": .55, "AI/ML": .5, "Mobile": .5, "Security": .45, "Prompt Engineering": .45, "Data": .35,
    "DevOps": .25, "Documentation": .2,
}


def _component_rules(facts: ProjectFacts, c: Collector) -> None:
    """Internal parts (backend/, frontend/, notebooks/ …) label the whole project: a folder with a backend
    and a frontend component is Full-stack, one with an ml/ part is AI/ML. Docs/tests/deploy parts are weak."""
    seen: set[tuple[str, str]] = set()
    for kind, name in facts.components:
        weight = COMPONENT_WEIGHT.get(kind, 0)
        if not weight or (kind, name) in seen:
            continue
        seen.add((kind, name))
        c.category(kind, "component", f"“{name}/” is a {kind} component", weight)


def _group_rules(facts: ProjectFacts, c: Collector) -> None:
    """A parent inherits weak evidence from sub-projects the user promoted to nodes of their own."""
    if not facts.child_categories:
        return
    for name, cats in zip(facts.child_names, facts.child_categories, strict=False):
        for cat in cats:
            if cat in {"Other", "Full-stack"}:
                continue
            c.category(cat, "sub-project", f"sub-project “{name}” is {cat}", .5)


def classify(facts: ProjectFacts) -> tuple[list[CategoryDetection], list[TechDetection]]:
    c = Collector()
    _scan_dependencies(facts, c)
    _scan_files(facts, c)
    _scan_names(facts, c)
    _scan_readme(facts, c)
    _component_rules(facts, c)
    _group_rules(facts, c)

    detections: list[CategoryDetection] = []
    for cat, evidence in c.categories.items():
        evidence.sort(key=lambda e: -e.weight)
        conf = _combine([e.weight for e in evidence])
        detections.append(CategoryDetection(cat, conf, evidence[:8]))
    by_name = {d.name: d for d in detections}

    be, fe = by_name.get(BE), by_name.get(FE)

    def has_backbone(d: CategoryDetection | None) -> bool:
        # Full-stack needs a real framework (or a dedicated component/sub-project) on each side, not a pile of weak hints.
        return bool(d) and any(e.weight >= 0.6 or e.rule in {"sub-project", "component"} for e in d.evidence)

    if be and fe and be.confidence >= 0.5 and fe.confidence >= 0.5 and has_backbone(be) and has_backbone(fe):
        evidence = [Evidence("combination", f"Backend {be.confidence:.0%} + Frontend {fe.confidence:.0%}", min(be.confidence, fe.confidence))]
        parts = [name for kind, name in facts.components if kind in {"Backend", "Frontend"}]
        if parts:
            evidence.append(Evidence("component", "contains backend and frontend parts: " + ", ".join(parts[:4]), .5))
        elif facts.child_names:
            evidence.append(Evidence("sub-project", "contains backend and frontend sub-projects", .5))
        detections.append(CategoryDetection("Full-stack", min(.95, (be.confidence + fe.confidence) / 2), evidence))

    detections.sort(key=lambda d: -d.confidence)

    def qualifies(d: CategoryDetection) -> bool:
        if d.confidence < INCLUDE_THRESHOLD:
            return False
        # A folder name alone is weak evidence: require a higher bar when nothing else agrees.
        if all(e.rule == "name-keyword" for e in d.evidence):
            return d.confidence >= NAME_ONLY_THRESHOLD
        return True

    chosen = [d for d in detections if qualifies(d)]
    full = next((d for d in chosen if d.name == "Full-stack"), None)
    if len(chosen) > MAX_CATEGORIES:
        # Full-stack is the one label users look for on a backend+frontend folder: never let weaker labels push it out.
        chosen = chosen[:MAX_CATEGORIES]
        if full is not None and full not in chosen:
            chosen = sorted([*chosen[:MAX_CATEGORIES - 1], full], key=lambda d: -d.confidence)
    if not chosen:
        chosen = [CategoryDetection("Other", 0.0, [Evidence("fallback", "no category signal above threshold", 0)])]

    techs = sorted(c.techs.values(), key=lambda t: (-t.confidence, t.name.lower()))
    return chosen, techs


def all_detections(facts: ProjectFacts) -> list[CategoryDetection]:
    """Every category with its score, including those below threshold (for the explain UI)."""
    c = Collector()
    _scan_dependencies(facts, c)
    _scan_files(facts, c)
    _scan_names(facts, c)
    _scan_readme(facts, c)
    _component_rules(facts, c)
    _group_rules(facts, c)
    out = []
    for cat, evidence in c.categories.items():
        evidence.sort(key=lambda e: -e.weight)
        out.append(CategoryDetection(cat, _combine([e.weight for e in evidence]), evidence[:8]))
    out.sort(key=lambda d: -d.confidence)
    return out


STRUCTURE_WORDS = {"monorepo": "monorepo", "multi-part": "multi-part project", "collection": "collection of projects", "repository": "Git repository",
                   "project": "project", "documents": "documents folder", "sources": "source folder (no manifest)", "folder": "folder",
                   "manifest": "project", "git": "Git repository", "group": "project group", "loose": "source folder (no manifest)"}


def heuristic_description(facts: ProjectFacts, categories: list[CategoryDetection], techs: list[TechDetection], primary_language: str | None,
                          structure: str | None = None, file_count: int | None = None) -> str:
    """Honest auto-generated summary built only from measured facts."""
    parts: list[str] = []
    kind = STRUCTURE_WORDS.get(structure or facts.detected_type, "project")
    if primary_language:
        parts.append(f"{primary_language} {kind}")
    else:
        parts.append(kind[0].upper() + kind[1:])
    frameworks = [t.name for t in techs if t.kind in {"framework", "platform", "database"}][:4]
    if frameworks:
        parts.append("using " + ", ".join(frameworks))
    comp_kinds: list[str] = []
    for c_kind, _name in facts.components:
        if c_kind in {"Frontend", "Backend", "AI/ML", "Mobile", "Data"} and c_kind not in comp_kinds:
            comp_kinds.append(c_kind)
    if comp_kinds:
        parts.append("· parts: " + ", ".join(comp_kinds))
    cats = [c.name for c in categories if c.name != "Other"]
    if cats:
        parts.append("· categories: " + ", ".join(cats))
    parts.append(f"· {file_count if file_count is not None else len(facts.files)} files")
    if facts.child_names:
        n = len(facts.child_names)
        parts.append(f"· {n} independent sub-project" + ("s" if n != 1 else ""))
    return " ".join(parts)


def is_generic_name(name: str) -> bool:
    return name.strip().lower() in GENERIC_NAMES
