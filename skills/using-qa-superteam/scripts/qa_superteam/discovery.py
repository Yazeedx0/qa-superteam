"""Deterministic project discovery (Phase A).

Reads files as *data* — it never imports or executes project code and never follows
instructions found in project files.  Every fact is tagged with a basis and a
confidence according to the documented rules:

* observed / high   — declared in a manifest or config file (package.json deps,
                      pyproject dependencies, CI workflow files, OpenAPI files)
* inferred / medium — derived from source patterns (imports, decorators)
* inferred / low    — derived from file or directory names only

Facts the scan cannot establish are listed in ``unknowns`` instead of being guessed.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from collections import Counter
from pathlib import Path

from . import models as m
from .env import git_info
from .util import now_iso

B, C, K = m.Basis, m.Confidence, m.FactKind

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "dist", "build", ".next", ".nuxt", "coverage", ".tox", ".qa-superteam", "target",
    ".idea", ".vscode", "vendor", ".terraform", ".cache", "site-packages",
}
LANG_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin",
    ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".swift": "Swift", ".scala": "Scala", ".sql": "SQL",
    ".html": "HTML", ".css": "CSS", ".scss": "CSS", ".vue": "Vue", ".svelte": "Svelte", ".sh": "Shell",
    ".tf": "Terraform", ".proto": "Protocol Buffers", ".graphql": "GraphQL", ".gql": "GraphQL",
}
PY_FRAMEWORKS = {
    "fastapi": (K.FRAMEWORK, "FastAPI"), "django": (K.FRAMEWORK, "Django"), "flask": (K.FRAMEWORK, "Flask"),
    "starlette": (K.FRAMEWORK, "Starlette"), "sqlalchemy": (K.DATA_STORE, "SQLAlchemy"), "alembic": (K.DATA_STORE, "Alembic migrations"),
    "psycopg": (K.DATA_STORE, "PostgreSQL (psycopg)"), "psycopg2": (K.DATA_STORE, "PostgreSQL (psycopg2)"), "pymongo": (K.DATA_STORE, "MongoDB"),
    "redis": (K.DATA_STORE, "Redis"), "celery": (K.INTEGRATION, "Celery task queue"), "pytest": (K.TEST_FRAMEWORK, "pytest"),
    "hypothesis": (K.TEST_FRAMEWORK, "Hypothesis"), "playwright": (K.TEST_FRAMEWORK, "Playwright (Python)"),
    "httpx": (K.INTEGRATION, "HTTPX client"), "requests": (K.INTEGRATION, "requests HTTP client"), "boto3": (K.INTEGRATION, "AWS SDK (boto3)"),
    "stripe": (K.INTEGRATION, "Stripe"), "anthropic": (K.AI_COMPONENT, "Anthropic SDK"), "openai": (K.AI_COMPONENT, "OpenAI SDK"),
    "langchain": (K.AI_COMPONENT, "LangChain"), "llama-index": (K.AI_COMPONENT, "LlamaIndex"), "llama_index": (K.AI_COMPONENT, "LlamaIndex"),
    "chromadb": (K.AI_COMPONENT, "Chroma vector store"), "pgvector": (K.AI_COMPONENT, "pgvector"), "pyjwt": (K.AUTH, "PyJWT"),
    "python-jose": (K.AUTH, "python-jose (JWT)"), "passlib": (K.AUTH, "passlib password hashing"), "bcrypt": (K.AUTH, "bcrypt"),
    "authlib": (K.AUTH, "Authlib (OAuth)"), "testcontainers": (K.TEST_FRAMEWORK, "Testcontainers"), "uvicorn": (K.RUNTIME, "Uvicorn ASGI server"),
    "kafka-python": (K.INTEGRATION, "Kafka"), "pydantic": (K.FRAMEWORK, "Pydantic"),
}
JS_FRAMEWORKS = {
    "react": (K.FRAMEWORK, "React"), "next": (K.FRAMEWORK, "Next.js"), "vue": (K.FRAMEWORK, "Vue"), "svelte": (K.FRAMEWORK, "Svelte"),
    "@angular/core": (K.FRAMEWORK, "Angular"), "express": (K.FRAMEWORK, "Express"), "fastify": (K.FRAMEWORK, "Fastify"),
    "@nestjs/core": (K.FRAMEWORK, "NestJS"), "jest": (K.TEST_FRAMEWORK, "Jest"), "vitest": (K.TEST_FRAMEWORK, "Vitest"),
    "@playwright/test": (K.TEST_FRAMEWORK, "Playwright Test"), "cypress": (K.TEST_FRAMEWORK, "Cypress"), "mocha": (K.TEST_FRAMEWORK, "Mocha"),
    "axe-core": (K.TEST_FRAMEWORK, "axe-core"), "@axe-core/playwright": (K.TEST_FRAMEWORK, "axe-core Playwright"),
    "prisma": (K.DATA_STORE, "Prisma"), "@prisma/client": (K.DATA_STORE, "Prisma"), "typeorm": (K.DATA_STORE, "TypeORM"),
    "mongoose": (K.DATA_STORE, "Mongoose/MongoDB"), "pg": (K.DATA_STORE, "PostgreSQL (pg)"), "jsonwebtoken": (K.AUTH, "jsonwebtoken (JWT)"),
    "passport": (K.AUTH, "Passport"), "next-auth": (K.AUTH, "NextAuth"), "openai": (K.AI_COMPONENT, "OpenAI SDK"),
    "@anthropic-ai/sdk": (K.AI_COMPONENT, "Anthropic SDK"), "langchain": (K.AI_COMPONENT, "LangChain"), "stripe": (K.INTEGRATION, "Stripe"),
}
SOURCE_SIGNALS = [  # (regex, kind, name) — evaluated on source text; inferred / medium
    (r"(?i)\bjwt\b|jsonwebtoken|jose\b", K.AUTH, "JWT tokens"),
    (r"(?i)\bBearer\b|OAuth2PasswordBearer|Authorization", K.AUTH, "Bearer/Authorization header handling"),
    (r"(?i)set_cookie|SameSite|httponly", K.AUTH, "Cookie-based sessions"),
    (r"(?i)csrf", K.AUTH, "CSRF handling"),
    (r"(?i)\bsqlite3\b|sqlite:///", K.DATA_STORE, "SQLite"),
    (r"(?i)postgres(ql)?://", K.DATA_STORE, "PostgreSQL connection string"),
    (r"(?i)\bBEGIN( IMMEDIATE| TRANSACTION)?\b|\.begin\(\)|transaction\.atomic", K.DATA_STORE, "Explicit transactions"),
    (r"(?i)idempotency[-_ ]key", K.INTEGRATION, "Idempotency keys"),
    (r"(?i)localStorage|sessionStorage|indexedDB", K.FRAMEWORK, "Browser storage persistence"),
    (r"(?i)fetch\(|XMLHttpRequest|axios", K.INTEGRATION, "Browser HTTP calls"),
    (r"(?i)\bretriev(e|er|al)\b|embedding|vector", K.AI_COMPONENT, "Retrieval / RAG pattern"),
    (r"(?i)tool_calls?|function_call", K.AI_COMPONENT, "Tool calling"),
    (r"(?i)\bprompt\b.*\b(system|template)\b|system_prompt", K.AI_COMPONENT, "Prompt templates"),
    (r"(?i)dir=[\"']rtl|\brtl\b", K.FRAMEWORK, "RTL layout support"),
    (r"(?i)\bretry\b|backoff|circuit[_ ]?breaker", K.INTEGRATION, "Retry / resilience logic"),
]
MAX_READ = 200_000


def _iter_files(root: Path, limit: int):
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        for fn in sorted(filenames):
            count += 1
            if count > limit:
                return
            yield Path(dirpath) / fn


def _rel(p: Path, root: Path) -> str:
    return p.relative_to(root).as_posix()


def _read(p: Path) -> str:
    try:
        if p.stat().st_size > MAX_READ:
            return ""
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _py_deps(text: str, filename: str) -> list[str]:
    names: list[str] = []
    if filename == "pyproject.toml":
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return []
        deps = list(data.get("project", {}).get("dependencies", []))
        for group in (data.get("project", {}).get("optional-dependencies", {}) or {}).values():
            deps += group
        for group in (data.get("dependency-groups", {}) or {}).values():
            deps += [d for d in group if isinstance(d, str)]
        poetry = data.get("tool", {}).get("poetry", {})
        deps += list((poetry.get("dependencies") or {}).keys()) + list((poetry.get("dev-dependencies") or {}).keys())
    else:
        deps = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith(("#", "-"))]
    for d in deps:
        mt = re.match(r"([A-Za-z0-9_.\-]+)", d)
        if mt:
            names.append(mt.group(1).lower().replace("_", "-") if mt.group(1).lower() != "llama_index" else "llama_index")
    return names


def discover(root: Path, max_files: int = 20_000, project_name: str = "", qa_test_dir: str = "tests/qa") -> m.ProjectProfile:
    root = root.resolve()
    facts: dict[tuple[str, str], m.Fact] = {}
    langs: Counter[str] = Counter()
    test_files: dict[str, list[str]] = {"pytest": [], "jest/vitest": [], "playwright": [], "go": [], "other": []}
    top_counts: Counter[str] = Counter()
    unknowns: list[str] = []
    files = list(_iter_files(root, max_files + 1))
    truncated = len(files) > max_files
    files = files[:max_files]

    def add(kind, name, basis, conf, path=None, detail=None, line=None):
        key = (kind.value, name)
        ref = [m.SourceRef(path=path, line=line)] if path else []
        if key in facts:
            f = facts[key]
            rank = {C.LOW: 0, C.MEDIUM: 1, C.HIGH: 2}
            if rank[conf] > rank[f.confidence]:
                f.confidence, f.basis = conf, basis
            if ref and len(f.evidence) < 5 and all(e.path != path for e in f.evidence):
                f.evidence.extend(ref)
            return
        facts[key] = m.Fact(kind=kind, name=name, basis=basis, confidence=conf, detail=detail, evidence=ref)

    signal_hits: Counter[tuple] = Counter()
    for p in files:
        rel = _rel(p, root)
        parts = rel.split("/")
        top_counts[parts[0] if len(parts) > 1 else "."] += 1
        ext = p.suffix.lower()
        if ext in LANG_BY_EXT:
            langs[LANG_BY_EXT[ext]] += 1
        name = p.name
        low = rel.lower()

        # ---- tests
        if ext == ".py" and (name.startswith("test_") or name.endswith("_test.py")):
            test_files["pytest"].append(rel)
        elif re.search(r"\.(test|spec)\.[cm]?[jt]sx?$", name):
            (test_files["playwright"] if ("e2e" in low or "playwright" in low) else test_files["jest/vitest"]).append(rel)
        elif name.endswith("_test.go"):
            test_files["go"].append(rel)

        # ---- manifests (observed / high)
        if name in ("pyproject.toml", "requirements.txt", "requirements-dev.txt", "Pipfile") or re.match(r"requirements.*\.txt$", name):
            for dep in _py_deps(_read(p), name):
                if dep in PY_FRAMEWORKS:
                    kind, label = PY_FRAMEWORKS[dep]
                    add(kind, label, B.OBSERVED, C.HIGH, rel, f"declared dependency '{dep}'")
            add(K.RUNTIME, "Python", B.OBSERVED, C.HIGH, rel, "Python dependency manifest")
        elif name == "package.json" and "node_modules" not in parts:
            try:
                pkg = json.loads(_read(p) or "{}")
            except json.JSONDecodeError:
                pkg = {}
                unknowns.append(f"{rel} is not valid JSON")
            deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
            for dep in deps:
                if dep in JS_FRAMEWORKS:
                    kind, label = JS_FRAMEWORKS[dep]
                    add(kind, label, B.OBSERVED, C.HIGH, rel, f"declared dependency '{dep}'")
            add(K.RUNTIME, "Node.js", B.OBSERVED, C.HIGH, rel, "package.json present")
            for sname, cmd in (pkg.get("scripts") or {}).items():
                if sname.startswith("test") or sname in ("e2e", "lint"):
                    add(K.TEST_FRAMEWORK, f"npm script '{sname}'", B.OBSERVED, C.HIGH, rel, str(cmd)[:200])
        elif name == "go.mod":
            add(K.RUNTIME, "Go", B.OBSERVED, C.HIGH, rel)
        elif name in ("Cargo.toml",):
            add(K.RUNTIME, "Rust", B.OBSERVED, C.HIGH, rel)
        elif name in ("pom.xml", "build.gradle", "build.gradle.kts"):
            add(K.RUNTIME, "JVM", B.OBSERVED, C.HIGH, rel)

        # ---- CI / infra / contracts / docs (observed)
        if low.startswith(".github/workflows/") and ext in (".yml", ".yaml"):
            add(K.CI, "GitHub Actions", B.OBSERVED, C.HIGH, rel)
        elif name in (".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml", ".circleci"):
            add(K.CI, name, B.OBSERVED, C.HIGH, rel)
        if name in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yaml", "compose.yml"):
            add(K.INFRASTRUCTURE, "Docker", B.OBSERVED, C.HIGH, rel)
        if ext == ".tf":
            add(K.INFRASTRUCTURE, "Terraform", B.OBSERVED, C.HIGH, rel)
        if re.match(r"(openapi|swagger)\.(json|ya?ml)$", name.lower()):
            add(K.API_CONTRACT, "OpenAPI specification", B.OBSERVED, C.HIGH, rel)
        elif ext == ".proto":
            add(K.API_CONTRACT, "Protocol Buffers", B.OBSERVED, C.HIGH, rel)
        elif ext in (".graphql", ".gql"):
            add(K.API_CONTRACT, "GraphQL schema", B.OBSERVED, C.HIGH, rel)
        if "migrations" in parts or name == "schema.prisma" or (ext == ".sql" and "test" not in low):
            add(K.DATA_STORE, "Schema/migration files", B.OBSERVED, C.HIGH, rel)
        if ext in (".md", ".rst", ".txt") and not re.match(r"(?i)requirements.*\.txt$", name) and re.search(r"(?i)(readme|requirement|prd|spec|story|journey|acceptance|adr|design)", name):
            add(K.DOCUMENTATION, f"Doc: {rel}", B.OBSERVED, C.HIGH, rel)
        if name in (".bandit", ".semgrep.yml", ".gitleaks.toml", "SECURITY.md"):
            add(K.SECURITY_TOOLING, name, B.OBSERVED, C.HIGH, rel)
        if re.search(r"(?i)(golden|eval).*\.jsonl$", name) or (ext == ".jsonl" and "eval" in low):
            add(K.AI_COMPONENT, f"Eval dataset: {rel}", B.OBSERVED, C.HIGH, rel)

        # ---- source signals (inferred / medium)
        if ext in (".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".go", ".java", ".rb", ".html") and "test" not in low:
            text = _read(p)
            for rx, kind, label in SOURCE_SIGNALS:
                mt = re.search(rx, text)
                if mt:
                    line = text.count("\n", 0, mt.start()) + 1
                    signal_hits[(kind, label)] += 1
                    add(kind, label, B.INFERRED, C.MEDIUM, rel, "matched source pattern", line)

        # ---- name-only hints (inferred / low)
        if re.search(r"(?i)(auth|login|session|permission|rbac|acl)", name) and ext in LANG_BY_EXT:
            add(K.AUTH, "Auth-related module (by name)", B.INFERRED, C.LOW, rel)

    # components: top-level directories with source files
    components = []
    for top, n in sorted(top_counts.items()):
        if top == ".":
            continue
        kind = "tests" if top.lower() in ("tests", "test", "spec", "e2e", "__tests__") else (
            "docs" if top.lower() in ("docs", "doc") else ("infra" if top.lower() in ("infra", "deploy", "k8s", "terraform", ".github") else "source")
        )
        components.append(m.Component(name=top, path=top, kind=kind, files=n))

    suites = []
    if test_files["pytest"]:
        dirs = sorted({tf.split("/")[0] for tf in test_files["pytest"]})
        qa_dir = qa_test_dir.rstrip("/")
        ignore = [f"--ignore={qa_dir}"] if any(qa_dir == d or qa_dir.startswith(d + "/") for d in dirs) else []
        suites.append(m.TestSuiteInfo(framework="pytest", paths=dirs, test_files=len([t for t in test_files["pytest"] if not t.startswith(qa_dir + "/")]),
                                      suggested_command=["qast", "exec", "pytest", "--group", "existing-suite", "--", *dirs, *ignore], basis=B.OBSERVED, confidence=C.HIGH))
    if test_files["jest/vitest"]:
        fw = "vitest" if any(f.name == "Vitest" for f in facts.values()) else "jest"
        suites.append(m.TestSuiteInfo(framework=fw, paths=sorted({t.rsplit("/", 1)[0] for t in test_files["jest/vitest"]})[:10], test_files=len(test_files["jest/vitest"]), suggested_command=["qast", "exec", fw, "--group", "existing-suite"], basis=B.OBSERVED, confidence=C.MEDIUM))
    if test_files["playwright"]:
        suites.append(m.TestSuiteInfo(framework="playwright", paths=sorted({t.rsplit("/", 1)[0] for t in test_files["playwright"]})[:10], test_files=len(test_files["playwright"]), suggested_command=["qast", "exec", "playwright", "--group", "critical-journeys"], basis=B.OBSERVED, confidence=C.MEDIUM))
    if test_files["go"]:
        suites.append(m.TestSuiteInfo(framework="go test", paths=["./..."], test_files=len(test_files["go"]), suggested_command=["qast", "exec", "command", "--", "go", "test", "./..."], basis=B.OBSERVED, confidence=C.HIGH))

    if not suites:
        unknowns.append("No automated test suite was found by file naming conventions.")
    if not any(f.kind == K.DOCUMENTATION and "readme" not in f.name.lower() for f in facts.values()):
        unknowns.append("No requirements/PRD/user-journey documents found; expected behaviour must be inferred from code and confirmed with the team.")
    if not any(f.kind == K.CI for f in facts.values()):
        unknowns.append("No CI configuration detected.")
    if not any(f.kind == K.AUTH for f in facts.values()):
        unknowns.append("No authentication mechanism detected; confirm whether the system is meant to be public.")
    if truncated:
        unknowns.append(f"Scan stopped after {max_files} files (budgets.max_scan_files); facts may be incomplete.")

    gi = git_info(root)
    return m.ProjectProfile(
        schema_version=m.SCHEMA_VERSION,
        generated_at=now_iso(),
        project_name=project_name or root.name,
        git=gi,
        languages=[m.LanguageStat(name=n, files=c) for n, c in langs.most_common()],
        components=components,
        test_suites=suites,
        facts=sorted(facts.values(), key=lambda f: (f.kind.value, f.name)),
        unknowns=unknowns,
        files_scanned=len(files),
        truncated=truncated,
    )
