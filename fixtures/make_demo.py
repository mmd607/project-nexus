"""Build a self-contained **demo workspace** with realistic, varied projects.

    python fixtures/make_demo.py <target-dir>

Unlike make_fixture.py (which also creates hostile cases for the tests), this
produces a clean showcase: 27 projects across every category, Git repositories
with commits (one dirty, one archived), a monorepo, a project group, a Persian-
named project, idle folders and secret-looking files (which Nexus flags but never
reads). Nothing here is personal data. Safe to re-run; the folder is recreated.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

NB = json.dumps({"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5})
DAY = 86400


def write(path: Path, content: str = "", age_days: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if age_days is not None:
        ts = time.time() - age_days * DAY
        os.utime(path, (ts, ts))


def git(path: Path, *args: str, date: str | None = None) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "Demo Dev", "GIT_AUTHOR_EMAIL": "demo@example.com",
           "GIT_COMMITTER_NAME": "Demo Dev", "GIT_COMMITTER_EMAIL": "demo@example.com", "GIT_TERMINAL_PROMPT": "0"}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, env=env, check=False)


def repo(path: Path, commits: list[tuple[str, float]], branch: str = "main") -> None:
    """Create a repo with the given (message, age_days) commits, oldest first."""
    git(path, "init", "-q", "-b", branch)
    git(path, "config", "commit.gpgsign", "false")
    for _i, (message, age) in enumerate(commits):
        marker = path / "CHANGELOG.md"
        with open(marker, "a", encoding="utf-8") as fh:
            fh.write(f"- {message}\n")
        git(path, "add", "-A")
        date = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - age * DAY))
        git(path, "commit", "-q", "-m", message, date=date)


def remove_tree(path: Path) -> None:
    if not path.exists():
        return

    def onerror(func, p, exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=onerror)


def build(target: Path) -> int:
    remove_tree(target)
    target.mkdir(parents=True)
    count = 0

    # ---------------- AI / ML ----------------
    p = target / "rag-assistant"
    write(p / "pyproject.toml", '[project]\nname = "rag-assistant"\ndependencies = ["fastapi", "uvicorn", "langchain", "langchain-openai", "chromadb", "sentence-transformers", "pydantic"]\n')
    write(p / "README.md", "# RAG Assistant\n\nA Retrieval-Augmented Generation system built with FastAPI, LangChain and ChromaDB for intelligent document search and Q&A.\n\n## Features\n- hybrid search\n- streaming answers\n")
    write(p / "app" / "main.py", "from fastapi import FastAPI\napp = FastAPI()\n")
    write(p / "app" / "retriever.py", "def retrieve(q):\n    return []\n")
    write(p / "app" / "embeddings.py", "")
    write(p / "tests" / "test_retriever.py", "def test_x():\n    assert True\n")
    write(p / "Dockerfile", "FROM python:3.12-slim\n")
    write(p / "docker-compose.yml", "services:\n  api:\n    build: .\n  chroma:\n    image: chromadb/chroma\n")
    write(p / ".env", "OPENAI_API_KEY=sk-demo-never-sent\n")
    repo(p, [("scaffold FastAPI app", 40), ("add Chroma retriever", 12), ("stream answers over SSE", 2)])
    count += 1

    p = target / "face-detection"
    write(p / "requirements.txt", "opencv-python\nultralytics\nnumpy\ntorch\n")
    write(p / "README.md", "# Face Detection\n\nReal-time face detection with YOLOv8 and OpenCV, exported to ONNX for edge devices.\n")
    write(p / "detect.py", "import cv2\n")
    write(p / "train.py", "")
    write(p / "models" / "yolov8n-face.pt", "binary")
    write(p / "models" / "yolov8n-face.onnx", "binary")
    write(p / "notebooks" / "evaluation.ipynb", NB)
    write(p / "data" / "samples.csv", "id,label\n1,face\n")
    count += 1

    p = target / "document-intelligence"
    write(p / "requirements.txt", "transformers\nspacy\npandas\npdfplumber\nscikit-learn\n")
    write(p / "README.md", "# Document Intelligence\n\nNLP pipeline that classifies scanned invoices and extracts entities with spaCy and Transformers.\n")
    write(p / "pipeline" / "__init__.py", "")
    write(p / "pipeline" / "classify.py", "")
    write(p / "pipeline" / "extract.py", "")
    write(p / "notebooks" / "explore.ipynb", NB)
    count += 1

    p = target / "video-search"
    write(p / "requirements.txt", "openai-whisper\nfaiss-cpu\nsentence-transformers\nfastapi\nstreamlit\n")
    write(p / "README.md", "# Video Search\n\nSemantic search over video transcripts: Whisper for speech-to-text, FAISS for vector search, Streamlit UI.\n")
    write(p / "ingest.py", "")
    write(p / "search.py", "")
    write(p / "ui" / "app.py", "import streamlit as st\n")
    write(p / "vector_db" / ".gitkeep", "")
    count += 1

    # ---------------- Data ----------------
    p = target / "sales-dashboard"
    write(p / "requirements.txt", "pandas\nplotly\nstreamlit\nsqlalchemy\npsycopg2-binary\n")
    write(p / "README.md", "# Sales Dashboard\n\nInteractive analytics dashboard for regional sales data with drill-down charts.\n")
    write(p / "dashboard.py", "import streamlit as st\n")
    write(p / "queries" / "monthly.sql", "select 1;")
    write(p / "queries" / "regions.sql", "select 2;")
    write(p / "queries" / "cohorts.sql", "select 3;")
    write(p / "data" / "sales_2025.csv", "a\n1\n")
    write(p / "data" / "regions.parquet", "")
    write(p / "notebooks" / "forecast.ipynb", NB)
    count += 1

    p = target / "etl-pipeline"
    write(p / "requirements.txt", "apache-airflow\ndbt-core\npandas\npyarrow\nduckdb\n")
    write(p / "README.md", "# ETL Pipeline\n\nAirflow DAGs and dbt models that load warehouse tables every night.\n")
    write(p / "dags" / "load_orders.py", "")
    write(p / "dags" / "load_customers.py", "")
    write(p / "dbt_project.yml", "name: warehouse\n")
    write(p / "models" / "orders.sql", "select 1")
    write(p / "Makefile", "run:\n\tairflow dags trigger load_orders\n")
    count += 1

    # ---------------- Frontend ----------------
    p = target / "portfolio-site"
    write(p / "index.html", "<!doctype html><html><body><h1>Hi</h1></body></html>")
    write(p / "about.html", "<html></html>")
    write(p / "css" / "style.css", "body{margin:0}")
    write(p / "css" / "theme.css", "")
    write(p / "js" / "main.js", "console.log('hi')")
    write(p / "assets" / "logo.svg", "<svg/>")
    write(p / "README.md", "# Portfolio\n\nPersonal portfolio website — static HTML, CSS and a little JavaScript.\n")
    count += 1

    p = target / "react-storefront"
    write(p / "package.json", json.dumps({"name": "react-storefront", "private": True, "dependencies": {"react": "^18.3", "react-dom": "^18.3", "react-router-dom": "^6", "@tanstack/react-query": "^5", "zustand": "^4"},
                                          "devDependencies": {"vite": "^5", "typescript": "^5", "tailwindcss": "^3", "vitest": "^2", "@testing-library/react": "^16"}, "scripts": {"dev": "vite", "build": "vite build", "test": "vitest"}}))
    write(p / "README.md", "# React Storefront\n\nResponsive e-commerce frontend with React, Vite and Tailwind CSS.\n")
    write(p / "index.html", "<div id=root></div>")
    write(p / "vite.config.ts", "export default {}")
    write(p / "tailwind.config.js", "module.exports = {}")
    for name in ["App", "main", "components/ProductCard", "components/Cart", "components/Header", "pages/Home", "pages/Checkout", "hooks/useCart"]:
        write(p / "src" / f"{name}.tsx", "export {}\n")
    write(p / "src" / "styles.css", "")
    write(p / "src" / "__tests__" / "Cart.test.tsx", "")
    repo(p, [("init storefront", 20), ("cart page", 5)])
    count += 1

    # ---------------- Backend ----------------
    p = target / "coffee-shop-api"
    write(p / "requirements.txt", "fastapi\nuvicorn\nsqlalchemy\nalembic\npsycopg2-binary\nredis\ncelery\npyjwt\npytest\n")
    write(p / "README.md", "# Coffee Shop API\n\nREST API backend for orders, menu and loyalty points, built with FastAPI, PostgreSQL and Redis.\n")
    write(p / "app" / "main.py", "from fastapi import FastAPI\n")
    write(p / "app" / "routers" / "orders.py", "")
    write(p / "app" / "routers" / "menu.py", "")
    write(p / "app" / "models.py", "")
    write(p / "app" / "auth.py", "")
    write(p / "migrations" / "env.py", "")
    write(p / "alembic.ini", "[alembic]\n")
    write(p / "docker-compose.yml", "services:\n  db:\n    image: postgres:16\n  cache:\n    image: redis:7\n  api:\n    build: .\n")
    write(p / "Dockerfile", "FROM python:3.12\n")
    write(p / "openapi.yaml", "openapi: 3.1.0\n")
    write(p / "tests" / "test_orders.py", "")
    write(p / "config" / "credentials.json", '{"demo": true}')
    repo(p, [("initial API", 30), ("loyalty points endpoint", 3)])
    write(p / "app" / "routers" / "loyalty.py", "# work in progress, not committed\n")   # dirty → Needs attention
    (p / "app" / "models.py").write_text("class Order: pass\n", encoding="utf-8")        # modified
    count += 1

    p = target / "express-gateway"
    write(p / "package.json", json.dumps({"name": "express-gateway", "dependencies": {"express": "^4", "jsonwebtoken": "^9", "ioredis": "^5", "helmet": "^7", "cors": "^2", "pg": "^8", "zod": "^3"}, "devDependencies": {"jest": "^29", "typescript": "^5", "nodemon": "^3"}}))
    write(p / "README.md", "# Express Gateway\n\nAPI gateway with JWT auth, rate limiting and request logging.\n")
    write(p / "src" / "server.ts", "")
    write(p / "src" / "routes" / "auth.ts", "")
    write(p / "src" / "routes" / "proxy.ts", "")
    write(p / "src" / "middleware" / "rateLimit.ts", "")
    write(p / "Dockerfile", "FROM node:22\n")
    write(p / ".github" / "workflows" / "ci.yml", "on: push\n")
    count += 1

    p = target / "rust-metrics"
    write(p / "Cargo.toml", '[package]\nname = "rust-metrics"\nversion = "0.3.0"\n[dependencies]\naxum = "0.7"\ntokio = { version = "1", features = ["full"] }\nserde = "1"\nsqlx = "0.7"\nprometheus = "0.13"\n')
    write(p / "README.md", "# rust-metrics\n\nHigh-throughput metrics ingestion service written in Rust with Axum and SQLx.\n")
    write(p / "src" / "main.rs", "fn main() {}\n")
    write(p / "src" / "routes.rs", "")
    write(p / "src" / "storage.rs", "")
    write(p / "Dockerfile", "FROM rust:1.80\n")
    count += 1

    p = target / "go-scheduler"
    write(p / "go.mod", "module example.com/go-scheduler\n\ngo 1.22\n\nrequire (\n\tgithub.com/gin-gonic/gin v1.10.0\n\tgorm.io/gorm v1.25.0\n)\n")
    write(p / "README.md", "# go-scheduler\n\nJob scheduling service exposing a Gin REST API with GORM persistence.\n")
    write(p / "main.go", "package main\n")
    write(p / "internal" / "api" / "handlers.go", "package api\n")
    write(p / "internal" / "jobs" / "runner.go", "package jobs\n")
    write(p / "Makefile", "build:\n\tgo build ./...\n")
    count += 1

    # ---------------- Full-stack ----------------
    p = target / "mono-shop"
    write(p / "package.json", json.dumps({"name": "mono-shop", "private": True, "workspaces": ["packages/*"], "devDependencies": {"turbo": "^2", "typescript": "^5"}}))
    write(p / "README.md", "# Mono Shop\n\nFull-stack monorepo: Next.js storefront, Express API and a shared TypeScript client.\n")
    write(p / "turbo.json", "{}")
    write(p / "packages" / "web" / "package.json", json.dumps({"name": "@shop/web", "dependencies": {"next": "^14", "react": "^18", "@shop/api-client": "file:../api-client"}}))
    write(p / "packages" / "web" / "next.config.js", "module.exports = {}")
    write(p / "packages" / "web" / "src" / "pages" / "index.tsx", "")
    write(p / "packages" / "web" / "src" / "pages" / "cart.tsx", "")
    write(p / "packages" / "api" / "package.json", json.dumps({"name": "@shop/api", "dependencies": {"express": "^4", "pg": "^8", "@shop/api-client": "file:../api-client"}}))
    write(p / "packages" / "api" / "src" / "server.ts", "")
    write(p / "packages" / "api" / "src" / "routes" / "orders.ts", "")
    write(p / "packages" / "api-client" / "package.json", json.dumps({"name": "@shop/api-client", "dependencies": {"axios": "^1"}}))
    write(p / "packages" / "api-client" / "index.ts", "")
    repo(p, [("monorepo scaffold", 15)])
    count += 4

    p = target / "smart-home"
    write(p / "README.md", "# Smart Home\n\nHome automation platform: Python backend talking to devices over MQTT, React dashboard.\n")
    write(p / "docker-compose.yml", "services:\n  api:\n    build: ./backend\n  web:\n    build: ./frontend\n  mqtt:\n    image: eclipse-mosquitto\n")
    write(p / "docs" / "architecture.md", "# Architecture\n")
    write(p / "backend" / "requirements.txt", "fastapi\npaho-mqtt\nsqlalchemy\n")
    write(p / "backend" / "app" / "main.py", "")
    write(p / "backend" / "app" / "devices.py", "")
    write(p / "frontend" / "package.json", json.dumps({"name": "smart-home-web", "dependencies": {"react": "^18", "recharts": "^2"}, "devDependencies": {"vite": "^5"}}))
    write(p / "frontend" / "src" / "App.tsx", "")
    write(p / "frontend" / "src" / "Dashboard.tsx", "")
    count += 3

    # ---------------- Security ----------------
    p = target / "cyber-recon"
    write(p / "requirements.txt", "scapy\npython-nmap\nimpacket\nshodan\nrequests\n")
    write(p / "README.md", "# Cyber Recon\n\nAuthorized penetration-testing helper: host discovery, port scanning and service fingerprinting.\n")
    write(p / "recon.py", "")
    write(p / "scanners" / "ports.py", "")
    write(p / "scanners" / "services.py", "")
    write(p / "exploits" / "README.md", "# PoCs (authorized lab use only)\n")
    write(p / "wordlists" / "common.txt", "admin\n")
    count += 1

    p = target / "malware-triage"
    write(p / "requirements.txt", "yara-python\npefile\ncapstone\nvolatility3\n")
    write(p / "README.md", "# Malware Triage\n\nStatic triage toolkit: YARA rules, PE parsing and memory forensics helpers.\n")
    write(p / "triage.py", "")
    write(p / "rules" / "suspicious.yar", "rule demo { condition: true }")
    write(p / "rules" / "packers.yar", "")
    write(p / "samples" / "notes.md", "hashes only\n")
    count += 1

    # ---------------- Mobile ----------------
    p = target / "mobile-notes"
    write(p / "pubspec.yaml", "name: mobile_notes\ndependencies:\n  flutter:\n    sdk: flutter\n  flutter_riverpod: ^2.0.0\n  dio: ^5.0.0\n  sqflite: ^2.0.0\ndev_dependencies:\n  flutter_test:\n    sdk: flutter\n")
    write(p / "README.md", "# Mobile Notes\n\nOffline-first notes app for Android and iOS built with Flutter.\n")
    write(p / "lib" / "main.dart", "void main() {}\n")
    write(p / "lib" / "screens" / "home.dart", "")
    write(p / "lib" / "screens" / "editor.dart", "")
    write(p / "lib" / "models" / "note.dart", "")
    write(p / "android" / "app" / "src" / "main" / "AndroidManifest.xml", "<manifest/>")
    write(p / "ios" / "Runner" / "Info.plist", "<plist/>")
    count += 1

    p = target / "fitness-tracker-app"
    write(p / "package.json", json.dumps({"name": "fitness-tracker", "dependencies": {"react-native": "0.75.0", "expo": "~51", "@react-navigation/native": "^6", "expo-sensors": "~13"}, "devDependencies": {"jest": "^29"}}))
    write(p / "README.md", "# Fitness Tracker\n\nReact Native / Expo mobile app that logs workouts using the phone's sensors.\n")
    write(p / "App.tsx", "")
    write(p / "screens" / "Home.tsx", "")
    write(p / "screens" / "Workout.tsx", "")
    write(p / "app.json", "{}")
    count += 1

    # ---------------- DevOps ----------------
    p = target / "infra-cluster"
    write(p / "main.tf", 'provider "aws" {}\n')
    write(p / "variables.tf", "")
    write(p / "modules" / "vpc" / "main.tf", "")
    write(p / "modules" / "eks" / "main.tf", "")
    write(p / "k8s" / "deployment.yaml", "apiVersion: apps/v1\n")
    write(p / "k8s" / "service.yaml", "apiVersion: v1\n")
    write(p / "helm" / "Chart.yaml", "name: platform\n")
    write(p / "helm" / "templates" / "deployment.yaml", "")
    write(p / ".github" / "workflows" / "deploy.yml", "on: push\n")
    write(p / "Makefile", "plan:\n\tterraform plan\n")
    write(p / "README.md", "# Infra Cluster\n\nInfrastructure as code for the production Kubernetes cluster: Terraform, Helm and GitHub Actions.\n")
    count += 1

    p = target / "ci-templates"
    write(p / "README.md", "# CI Templates\n\nReusable GitLab CI templates and Ansible playbooks for provisioning build agents.\n")
    write(p / ".gitlab-ci.yml", "stages: [build]\n")
    write(p / "ansible.cfg", "[defaults]\n")
    write(p / "playbooks" / "agents.yml", "- hosts: all\n")
    write(p / "playbooks" / "monitoring.yml", "- hosts: all\n")
    write(p / "roles" / "docker" / "tasks" / "main.yml", "- name: install docker\n")
    write(p / "Dockerfile", "FROM ubuntu:24.04\n")
    write(p / "scripts" / "bootstrap.sh", "#!/bin/sh\n")
    count += 1

    # ---------------- Prompt Engineering ----------------
    p = target / "prompt-library"
    write(p / "README.md", "# Prompt Library\n\nReusable system prompts, few-shot templates and evaluation harness for LLM agents.\n")
    write(p / "requirements.txt", "dspy-ai\nopenai\nanthropic\njinja2\n")
    write(p / "prompts" / "summarize.md", "You are a concise summarizer.\n")
    write(p / "prompts" / "classify.prompt", "Classify: {{ text }}\n")
    write(p / "prompts" / "extract.jinja2", "Extract fields from {{ doc }}\n")
    write(p / "prompts" / "system" / "assistant.md", "System prompt\n")
    write(p / "evals" / "run_evals.py", "")
    write(p / "CLAUDE.md", "# Instructions for coding agents\n")
    count += 1

    p = target / "agent-playbooks"
    write(p / "README.md", "# Agent Playbooks\n\nPersona and instruction sets for multi-agent workflows built on LangGraph.\n")
    write(p / "pyproject.toml", '[project]\nname = "agent-playbooks"\ndependencies = ["langgraph", "langchain", "ollama"]\n')
    write(p / "AGENTS.md", "# Agents\n")
    write(p / "prompts" / "planner.md", "")
    write(p / "prompts" / "reviewer.md", "")
    write(p / "prompts" / "coder.md", "")
    write(p / "graph.py", "")
    count += 1

    # ---------------- Documentation ----------------
    p = target / "team-handbook"
    write(p / "mkdocs.yml", "site_name: Team Handbook\n")
    write(p / "README.md", "# Team Handbook\n\nOnboarding guide, engineering standards and runbooks.\n")
    for name in ["onboarding", "standards", "runbooks", "on-call", "glossary", "faq"]:
        write(p / "docs" / f"{name}.md", f"# {name}\n")
    count += 1

    p = target / "research-notes"
    write(p / "README.md", "# Research Notes\n\nReading notes and summaries of papers on retrieval and evaluation.\n")
    for name in ["2024-q3", "2024-q4", "2025-q1", "2025-q2", "ideas"]:
        write(p / f"{name}.md", f"# {name}\n")
    count += 1

    # ---------------- Idle / archived / other ----------------
    p = target / "legacy-scripts"
    for name in ["backup", "cleanup", "convert", "report"]:
        write(p / f"{name}.py", "print('legacy')\n", age_days=200)
    write(p / "README.txt", "old utility scripts\n", age_days=200)
    os.utime(p, (time.time() - 200 * DAY, time.time() - 200 * DAY))
    count += 1

    p = target / "archived-2023"
    write(p / "requirements.txt", "flask\nrequests\n", age_days=400)
    write(p / "app.py", "from flask import Flask\n", age_days=400)
    write(p / "README.md", "# Archived 2023\n\nAn old Flask side project kept for reference.\n", age_days=400)
    repo(p, [("initial", 420), ("last fix", 380)])
    for f in p.rglob("*"):
        if f.is_file() and ".git" not in f.parts:
            os.utime(f, (time.time() - 400 * DAY, time.time() - 400 * DAY))
    count += 1

    p = target / "پروژه-فارسی"
    write(p / "README.md", "# پروژهٔ فارسی\n\nابزار پردازش متن فارسی: نرمال‌سازی، توکن‌سازی و استخراج کلیدواژه با hazm.\n")
    write(p / "requirements.txt", "hazm\nfastapi\n")
    write(p / "متن.py", "print('سلام')\n")
    write(p / "api.py", "")
    write(p / "docs" / "راهنما.md", "# راهنما\n")
    count += 1

    p = target / "sensor-firmware"
    write(p / "CMakeLists.txt", "project(sensor_firmware C)\nfind_package(FreeRTOS)\n")
    write(p / "README.md", "# Sensor Firmware\n\nEmbedded C firmware for an environmental sensor node.\n")
    write(p / "src" / "main.c", "int main(void){return 0;}\n")
    write(p / "src" / "i2c.c", "")
    write(p / "include" / "i2c.h", "")
    count += 1

    (target / "README-DEMO.md").write_text(
        "# Project Nexus demo workspace\n\nGenerated by fixtures/make_demo.py. Every folder here is synthetic sample data used to showcase "
        "discovery, classification, Git status, monorepos, groups, idle detection and sensitive-file flagging. Delete and regenerate freely.\n",
        encoding="utf-8")
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    n = build(args.target.resolve())
    print(f"demo workspace written to {args.target.resolve()} (~{n} projects incl. sub-projects)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
