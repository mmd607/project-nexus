"""Static knowledge: file extensions → languages, file kinds, sensitive-file patterns."""
from __future__ import annotations

import fnmatch
import os

LANGUAGES: dict[str, str] = {
    ".py": "Python", ".pyi": "Python", ".ipynb": "Jupyter Notebook",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".mts": "TypeScript", ".cts": "TypeScript",
    ".vue": "Vue", ".svelte": "Svelte", ".astro": "Astro",
    ".rs": "Rust", ".go": "Go", ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".scala": "Scala",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".hpp": "C++", ".hh": "C++",
    ".cs": "C#", ".fs": "F#", ".vb": "Visual Basic",
    ".rb": "Ruby", ".php": "PHP", ".swift": "Swift", ".m": "Objective-C", ".mm": "Objective-C",
    ".dart": "Dart", ".lua": "Lua", ".r": "R", ".jl": "Julia", ".ex": "Elixir", ".exs": "Elixir",
    ".erl": "Erlang", ".hs": "Haskell", ".clj": "Clojure", ".ml": "OCaml", ".zig": "Zig", ".nim": "Nim",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell", ".ps1": "PowerShell", ".psm1": "PowerShell", ".bat": "Batch", ".cmd": "Batch",
    ".sql": "SQL", ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".scss": "SCSS", ".sass": "SCSS", ".less": "Less",
    ".sol": "Solidity", ".proto": "Protocol Buffers", ".graphql": "GraphQL", ".gql": "GraphQL",
    ".tf": "Terraform", ".hcl": "HCL", ".cu": "CUDA", ".cuh": "CUDA", ".glsl": "GLSL", ".wgsl": "WGSL",
    ".md": "Markdown", ".mdx": "Markdown", ".rst": "reStructuredText", ".tex": "TeX",
    ".yaml": "YAML", ".yml": "YAML", ".json": "JSON", ".toml": "TOML", ".xml": "XML", ".ini": "INI", ".cfg": "INI",
    ".dockerfile": "Dockerfile", ".gradle": "Gradle", ".cmake": "CMake", ".makefile": "Makefile",
}

# Languages that count as "code" for primary-language purposes (config/markup excluded).
CODE_LANGUAGES = {
    "Python", "Jupyter Notebook", "JavaScript", "TypeScript", "Vue", "Svelte", "Astro", "Rust", "Go", "Java", "Kotlin",
    "Scala", "C", "C++", "C#", "F#", "Visual Basic", "Ruby", "PHP", "Swift", "Objective-C", "Dart", "Lua", "R", "Julia",
    "Elixir", "Erlang", "Haskell", "Clojure", "OCaml", "Zig", "Nim", "Shell", "PowerShell", "Batch", "SQL", "Solidity",
    "CUDA", "GLSL", "WGSL", "HTML", "CSS", "SCSS", "Less", "Terraform", "HCL", "Dockerfile", "Protocol Buffers", "GraphQL",
    "Makefile", "CMake", "Gradle", "Just", "Groovy",
}

SPECIAL_FILENAMES = {
    "dockerfile": "Dockerfile", "makefile": "Makefile", "cmakelists.txt": "CMake", "gemfile": "Ruby", "rakefile": "Ruby",
    "justfile": "Just", "vagrantfile": "Ruby", "jenkinsfile": "Groovy", "podfile": "Ruby",
}

DOC_EXT = {".md", ".mdx", ".rst", ".txt", ".adoc", ".tex", ".pdf", ".docx", ".doc", ".odt"}
DATA_EXT = {".csv", ".tsv", ".parquet", ".jsonl", ".ndjson", ".arrow", ".feather", ".xlsx", ".xls", ".db", ".sqlite",
            ".sqlite3", ".h5", ".hdf5", ".npy", ".npz", ".pkl", ".pickle", ".sav", ".dat"}
MODEL_EXT = {".pt", ".pth", ".ckpt", ".safetensors", ".onnx", ".gguf", ".ggml", ".tflite", ".pb", ".bin", ".joblib", ".keras"}
ASSET_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp", ".mp3", ".wav", ".ogg", ".mp4", ".mov",
             ".webm", ".ttf", ".otf", ".woff", ".woff2", ".psd", ".ai", ".fig", ".glb", ".gltf", ".obj", ".fbx"}
CONFIG_EXT = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env", ".properties", ".xml", ".plist", ".lock"}
ARCHIVE_EXT = {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz"}
PROMPT_EXT = {".prompt", ".prompty", ".jinja", ".jinja2", ".j2", ".tmpl", ".hbs"}

TEST_DIR_HINTS = {"test", "tests", "__tests__", "spec", "specs", "e2e", "cypress", "playwright"}

# Files that are never read and never sent to a model, even if the user asks for file names.
SENSITIVE_PATTERNS = [
    ".env", ".env.*", "*.env", ".envrc", "*.pem", "*.key", "*.p12", "*.pfx", "*.crt", "*.cer", "*.der", "*.jks",
    "*.keystore", "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*", "*.ppk", "*.kdbx", "*.gpg", "*.asc", ".npmrc",
    ".pypirc", ".netrc", "_netrc", ".htpasswd", "*.htpasswd", "*credential*", "*credentials*", "*secret*", "*secrets*",
    "*token*", "*password*", "*.tfstate", "*.tfstate.*", "terraform.tfvars", "*.ovpn", "*.mobileconfig", "*.pkcs12",
    "service-account*.json", "*serviceaccount*.json", "firebase-adminsdk*.json", "aws_credentials", "credentials.json",
    "client_secret*.json", ".git-credentials", ".boto", ".s3cfg", "*.age", "*.enc",
]
SENSITIVE_DIR_HINTS = {".ssh", ".aws", ".gnupg", ".azure", ".kube", ".docker", "secrets", "private_keys"}


def language_for(name: str, ext: str) -> str | None:
    lowered = name.lower()
    if lowered in SPECIAL_FILENAMES:
        return SPECIAL_FILENAMES[lowered]
    if lowered.startswith("dockerfile"):
        return "Dockerfile"
    return LANGUAGES.get(ext)


def is_sensitive(relative_path: str) -> bool:
    parts = relative_path.replace("\\", "/").split("/")
    name = parts[-1].lower()
    if any(part.lower() in SENSITIVE_DIR_HINTS for part in parts[:-1]):
        return True
    for pattern in SENSITIVE_PATTERNS:
        if fnmatch.fnmatchcase(name, pattern):
            return True
    return False


def classify_kind(relative_path: str, ext: str) -> str:
    """Coarse file kind used for stats and for choosing what may be described to a model."""
    parts = relative_path.replace("\\", "/").split("/")
    name = parts[-1].lower()
    if is_sensitive(relative_path):
        return "secret"
    if ext == ".ipynb":
        return "notebook"
    if any(seg.lower() in TEST_DIR_HINTS for seg in parts[:-1]) or name.startswith("test_") or name.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts", "_test.go")):
        if language_for(name, ext) in CODE_LANGUAGES:
            return "test"
    if name in {"package.json", "pyproject.toml", "requirements.txt", "cargo.toml", "go.mod", "pom.xml", "build.gradle",
                "build.gradle.kts", "gemfile", "composer.json", "pubspec.yaml", "setup.py", "setup.cfg", "pipfile",
                "environment.yml", "cmakelists.txt", "makefile", "dockerfile", "docker-compose.yml", "docker-compose.yaml",
                "compose.yml", "compose.yaml"} or name.endswith((".csproj", ".sln", ".fsproj")):
        return "manifest"
    if ext in PROMPT_EXT or (("prompt" in name) and ext in {".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".xml", ""}):
        return "prompt"
    if ext in MODEL_EXT:
        return "model"
    if ext in DATA_EXT:
        return "data"
    if ext in DOC_EXT:
        return "doc"
    if ext in ASSET_EXT:
        return "asset"
    if ext in ARCHIVE_EXT:
        return "archive"
    lang = language_for(name, ext)
    if lang in CODE_LANGUAGES:
        return "source"
    if ext in CONFIG_EXT or name.startswith("."):
        return "config"
    return "other"


def split_ext(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    return ext
