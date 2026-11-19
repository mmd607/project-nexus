"""Dependency / file → technology knowledge base.

Each technology entry is ``(display_name, kind, {category: weight})``. Weights
are evidence strengths in (0, 1] combined by the classifier; they are *not*
probabilities of anything and the UI labels them as rule confidence.
"""
from __future__ import annotations

AI, SEC, BE, FE, DATA, OPS, MOB, DOC, PE = (
    "AI/ML", "Security", "Backend", "Frontend", "Data", "DevOps", "Mobile", "Documentation", "Prompt Engineering",
)

TechEntry = tuple[str, str, dict[str, float]]

TECH_MAP: dict[str, TechEntry] = {
    # ---- Python: AI / ML ----
    "torch": ("PyTorch", "framework", {AI: .85}), "torchvision": ("PyTorch", "framework", {AI: .8}),
    "torchaudio": ("PyTorch", "framework", {AI: .8}), "pytorch-lightning": ("PyTorch Lightning", "framework", {AI: .8}),
    "lightning": ("PyTorch Lightning", "framework", {AI: .7}), "tensorflow": ("TensorFlow", "framework", {AI: .85}),
    "tensorflow-gpu": ("TensorFlow", "framework", {AI: .85}), "tf-keras": ("Keras", "framework", {AI: .8}),
    "keras": ("Keras", "framework", {AI: .8}), "jax": ("JAX", "framework", {AI: .8}), "flax": ("Flax", "framework", {AI: .8}),
    "transformers": ("Hugging Face Transformers", "library", {AI: .85}), "datasets": ("Hugging Face Datasets", "library", {AI: .6, DATA: .3}),
    "tokenizers": ("Hugging Face Tokenizers", "library", {AI: .6}), "accelerate": ("Hugging Face Accelerate", "library", {AI: .7}),
    "peft": ("PEFT", "library", {AI: .8}), "trl": ("TRL", "library", {AI: .8}), "diffusers": ("Diffusers", "library", {AI: .85}),
    "sentence-transformers": ("Sentence Transformers", "library", {AI: .8}), "scikit-learn": ("scikit-learn", "library", {AI: .7, DATA: .4}),
    "sklearn": ("scikit-learn", "library", {AI: .7, DATA: .4}), "xgboost": ("XGBoost", "library", {AI: .7, DATA: .3}),
    "lightgbm": ("LightGBM", "library", {AI: .7, DATA: .3}), "catboost": ("CatBoost", "library", {AI: .7, DATA: .3}),
    "opencv-python": ("OpenCV", "library", {AI: .55}), "opencv-python-headless": ("OpenCV", "library", {AI: .55}),
    "opencv-contrib-python": ("OpenCV", "library", {AI: .55}), "ultralytics": ("YOLO (Ultralytics)", "library", {AI: .85}),
    "mediapipe": ("MediaPipe", "library", {AI: .8}), "detectron2": ("Detectron2", "library", {AI: .85}),
    "timm": ("timm", "library", {AI: .8}), "albumentations": ("Albumentations", "library", {AI: .6}),
    "onnx": ("ONNX", "library", {AI: .7}), "onnxruntime": ("ONNX Runtime", "library", {AI: .7}), "onnxruntime-gpu": ("ONNX Runtime", "library", {AI: .7}),
    "spacy": ("spaCy", "library", {AI: .7}), "nltk": ("NLTK", "library", {AI: .6}), "gensim": ("Gensim", "library", {AI: .6}),
    "openai-whisper": ("Whisper", "library", {AI: .8}), "whisper": ("Whisper", "library", {AI: .6}), "faster-whisper": ("Whisper", "library", {AI: .8}),
    "speechrecognition": ("SpeechRecognition", "library", {AI: .5}), "librosa": ("librosa", "library", {AI: .4, DATA: .3}),
    "stable-baselines3": ("Stable-Baselines3", "library", {AI: .8}), "gymnasium": ("Gymnasium", "library", {AI: .7}), "gym": ("OpenAI Gym", "library", {AI: .6}),
    "optuna": ("Optuna", "library", {AI: .6}), "ray": ("Ray", "framework", {AI: .5, DATA: .3}), "mlflow": ("MLflow", "tool", {AI: .7, OPS: .3}),
    "wandb": ("Weights & Biases", "tool", {AI: .7}), "tensorboard": ("TensorBoard", "tool", {AI: .6}), "dvc": ("DVC", "tool", {AI: .5, DATA: .4, OPS: .2}),
    "deepspeed": ("DeepSpeed", "library", {AI: .85}), "bitsandbytes": ("bitsandbytes", "library", {AI: .8}), "vllm": ("vLLM", "library", {AI: .85}),
    "llama-cpp-python": ("llama.cpp", "library", {AI: .85}), "ctransformers": ("ctransformers", "library", {AI: .8}),
    "faiss-cpu": ("FAISS", "library", {AI: .7}), "faiss-gpu": ("FAISS", "library", {AI: .7}), "chromadb": ("ChromaDB", "database", {AI: .7}),
    "qdrant-client": ("Qdrant", "database", {AI: .7}), "pinecone-client": ("Pinecone", "database", {AI: .7}), "pinecone": ("Pinecone", "database", {AI: .7}),
    "weaviate-client": ("Weaviate", "database", {AI: .7}), "pgvector": ("pgvector", "database", {AI: .6, DATA: .3}), "pymilvus": ("Milvus", "database", {AI: .7}),
    "langchain": ("LangChain", "framework", {AI: .8, PE: .5}), "langchain-core": ("LangChain", "framework", {AI: .8, PE: .5}),
    "langchain-community": ("LangChain", "framework", {AI: .8, PE: .5}), "langchain-openai": ("LangChain", "framework", {AI: .8, PE: .5}),
    "langgraph": ("LangGraph", "framework", {AI: .8, PE: .6}), "llama-index": ("LlamaIndex", "framework", {AI: .8, PE: .4}),
    "llama-index-core": ("LlamaIndex", "framework", {AI: .8, PE: .4}), "haystack-ai": ("Haystack", "framework", {AI: .8}),
    "openai": ("OpenAI SDK", "library", {AI: .65, PE: .5}), "anthropic": ("Anthropic SDK", "library", {AI: .65, PE: .5}),
    "google-generativeai": ("Gemini SDK", "library", {AI: .65, PE: .5}), "google-genai": ("Gemini SDK", "library", {AI: .65, PE: .5}),
    "cohere": ("Cohere SDK", "library", {AI: .6, PE: .4}), "mistralai": ("Mistral SDK", "library", {AI: .6, PE: .4}),
    "ollama": ("Ollama", "library", {AI: .7, PE: .4}), "litellm": ("LiteLLM", "library", {AI: .7, PE: .5}),
    "dspy": ("DSPy", "framework", {AI: .7, PE: .85}), "dspy-ai": ("DSPy", "framework", {AI: .7, PE: .85}),
    "guidance": ("Guidance", "library", {AI: .6, PE: .85}), "outlines": ("Outlines", "library", {AI: .6, PE: .7}),
    "instructor": ("Instructor", "library", {AI: .6, PE: .7}), "promptflow": ("Prompt Flow", "framework", {AI: .6, PE: .85}),
    "promptify": ("Promptify", "library", {PE: .8}), "guardrails-ai": ("Guardrails", "library", {AI: .5, PE: .7}),
    "crewai": ("CrewAI", "framework", {AI: .75, PE: .6}), "autogen": ("AutoGen", "framework", {AI: .75, PE: .6}),
    "pyautogen": ("AutoGen", "framework", {AI: .75, PE: .6}), "semantic-kernel": ("Semantic Kernel", "framework", {AI: .7, PE: .6}),
    "mcp": ("Model Context Protocol", "library", {AI: .6, PE: .5}), "tiktoken": ("tiktoken", "library", {AI: .5, PE: .4}),
    "gradio": ("Gradio", "framework", {AI: .5, FE: .35}), "streamlit": ("Streamlit", "framework", {DATA: .55, FE: .35}),
    # ---- Python: Data ----
    "numpy": ("NumPy", "library", {DATA: .3}), "pandas": ("pandas", "library", {DATA: .65}), "polars": ("Polars", "library", {DATA: .65}),
    "pyspark": ("Apache Spark", "framework", {DATA: .8}), "dask": ("Dask", "framework", {DATA: .7}), "scipy": ("SciPy", "library", {DATA: .4}),
    "statsmodels": ("statsmodels", "library", {DATA: .6}), "matplotlib": ("Matplotlib", "library", {DATA: .4}), "seaborn": ("seaborn", "library", {DATA: .5}),
    "plotly": ("Plotly", "library", {DATA: .5}), "bokeh": ("Bokeh", "library", {DATA: .5}), "altair": ("Altair", "library", {DATA: .5}),
    "dash": ("Dash", "framework", {DATA: .6, FE: .3}), "jupyter": ("Jupyter", "tool", {DATA: .5}), "jupyterlab": ("Jupyter", "tool", {DATA: .5}),
    "notebook": ("Jupyter", "tool", {DATA: .5}), "ipykernel": ("Jupyter", "tool", {DATA: .3}), "apache-airflow": ("Apache Airflow", "framework", {DATA: .8, OPS: .3}),
    "prefect": ("Prefect", "framework", {DATA: .7, OPS: .3}), "dagster": ("Dagster", "framework", {DATA: .8}), "dbt-core": ("dbt", "tool", {DATA: .85}),
    "great-expectations": ("Great Expectations", "library", {DATA: .7}), "pyarrow": ("Apache Arrow", "library", {DATA: .5}), "duckdb": ("DuckDB", "database", {DATA: .7}),
    "sqlalchemy": ("SQLAlchemy", "library", {BE: .35, DATA: .3}), "alembic": ("Alembic", "tool", {BE: .4}), "psycopg2": ("PostgreSQL", "database", {BE: .3, DATA: .2}),
    "psycopg2-binary": ("PostgreSQL", "database", {BE: .3, DATA: .2}), "psycopg": ("PostgreSQL", "database", {BE: .4, DATA: .2}), "asyncpg": ("PostgreSQL", "database", {BE: .4}),
    "pymongo": ("MongoDB", "database", {BE: .4}), "motor": ("MongoDB", "database", {BE: .4}), "redis": ("Redis", "database", {BE: .4}),
    "pymysql": ("MySQL", "database", {BE: .4}), "mysqlclient": ("MySQL", "database", {BE: .4}), "beautifulsoup4": ("BeautifulSoup", "library", {DATA: .4}),
    "scrapy": ("Scrapy", "framework", {DATA: .6}), "kafka-python": ("Apache Kafka", "platform", {BE: .4, DATA: .4}), "confluent-kafka": ("Apache Kafka", "platform", {BE: .4, DATA: .4}),
    # ---- Python: Backend ----
    "fastapi": ("FastAPI", "framework", {BE: .85}), "flask": ("Flask", "framework", {BE: .8}), "django": ("Django", "framework", {BE: .85}),
    "djangorestframework": ("Django REST Framework", "framework", {BE: .85}), "starlette": ("Starlette", "framework", {BE: .7}),
    "uvicorn": ("Uvicorn", "tool", {BE: .5}), "gunicorn": ("Gunicorn", "tool", {BE: .5}), "hypercorn": ("Hypercorn", "tool", {BE: .5}),
    "aiohttp": ("aiohttp", "library", {BE: .5}), "tornado": ("Tornado", "framework", {BE: .7}), "sanic": ("Sanic", "framework", {BE: .8}),
    "litestar": ("Litestar", "framework", {BE: .85}), "falcon": ("Falcon", "framework", {BE: .8}), "bottle": ("Bottle", "framework", {BE: .7}),
    "celery": ("Celery", "framework", {BE: .55}), "rq": ("RQ", "library", {BE: .4}), "pydantic": ("Pydantic", "library", {BE: .25}),
    "graphene": ("GraphQL", "library", {BE: .6}), "strawberry-graphql": ("GraphQL", "library", {BE: .6}), "grpcio": ("gRPC", "library", {BE: .6}),
    "httpx": ("HTTPX", "library", {}), "requests": ("Requests", "library", {}), "python-telegram-bot": ("Telegram Bot", "library", {BE: .45}),
    "telethon": ("Telegram (Telethon)", "library", {BE: .4}), "aiogram": ("Telegram Bot", "library", {BE: .45}), "discord.py": ("Discord Bot", "library", {BE: .45}),
    "pyjwt": ("JWT", "library", {BE: .3, SEC: .2}), "python-jose": ("JWT", "library", {BE: .3, SEC: .2}), "passlib": ("passlib", "library", {BE: .3, SEC: .3}),
    "bcrypt": ("bcrypt", "library", {BE: .25, SEC: .3}), "authlib": ("Authlib", "library", {BE: .4, SEC: .3}), "boto3": ("AWS SDK", "platform", {OPS: .35, BE: .2}),
    # ---- Python: Security ----
    "cryptography": ("cryptography", "library", {SEC: .45}), "pycryptodome": ("PyCryptodome", "library", {SEC: .5}), "scapy": ("Scapy", "library", {SEC: .85}),
    "python-nmap": ("Nmap", "tool", {SEC: .85}), "impacket": ("Impacket", "library", {SEC: .9}), "pwntools": ("pwntools", "library", {SEC: .9}),
    "yara-python": ("YARA", "library", {SEC: .85}), "paramiko": ("Paramiko (SSH)", "library", {SEC: .25, OPS: .3}), "shodan": ("Shodan", "platform", {SEC: .8}),
    "pyshark": ("Wireshark (pyshark)", "library", {SEC: .8}), "mitmproxy": ("mitmproxy", "tool", {SEC: .85}), "requests-ntlm": ("NTLM", "library", {SEC: .5}),
    "python-whois": ("WHOIS", "library", {SEC: .5}), "dnspython": ("dnspython", "library", {SEC: .3, BE: .2}), "pyopenssl": ("OpenSSL", "library", {SEC: .4}),
    "bandit": ("Bandit", "tool", {SEC: .4}), "semgrep": ("Semgrep", "tool", {SEC: .6}), "volatility3": ("Volatility", "tool", {SEC: .9}), "pefile": ("pefile", "library", {SEC: .7}),
    "capstone": ("Capstone", "library", {SEC: .8}), "angr": ("angr", "framework", {SEC: .9}), "frida": ("Frida", "tool", {SEC: .85}), "ropgadget": ("ROPgadget", "tool", {SEC: .9}),
    # ---- Python: DevOps / tooling ----
    "docker": ("Docker SDK", "library", {OPS: .55}), "kubernetes": ("Kubernetes", "platform", {OPS: .75}), "ansible": ("Ansible", "tool", {OPS: .85}),
    "ansible-core": ("Ansible", "tool", {OPS: .85}), "fabric": ("Fabric", "tool", {OPS: .6}), "pulumi": ("Pulumi", "tool", {OPS: .85}), "invoke": ("Invoke", "tool", {OPS: .3}),
    "prometheus-client": ("Prometheus", "tool", {OPS: .5, BE: .2}), "sentry-sdk": ("Sentry", "tool", {OPS: .3}), "loguru": ("Loguru", "library", {}),
    "pytest": ("pytest", "tool", {}), "mypy": ("mypy", "tool", {}), "ruff": ("Ruff", "tool", {}), "black": ("Black", "tool", {}),
    "typer": ("Typer (CLI)", "framework", {}), "click": ("Click (CLI)", "library", {}), "rich": ("Rich", "library", {}), "textual": ("Textual (TUI)", "framework", {FE: .3}),
    "mkdocs": ("MkDocs", "tool", {DOC: .85}), "mkdocs-material": ("MkDocs", "tool", {DOC: .85}), "sphinx": ("Sphinx", "tool", {DOC: .85}),
    "kivy": ("Kivy", "framework", {MOB: .7}), "toga": ("BeeWare Toga", "framework", {MOB: .5}), "briefcase": ("BeeWare Briefcase", "tool", {MOB: .5}),
    "pyqt5": ("PyQt", "framework", {FE: .35}), "pyqt6": ("PyQt", "framework", {FE: .35}), "pyside6": ("PySide", "framework", {FE: .35}), "pyside2": ("PySide", "framework", {FE: .35}),
    "customtkinter": ("Tkinter", "framework", {FE: .3}), "pygame": ("Pygame", "framework", {FE: .3}), "flet": ("Flet", "framework", {FE: .4, MOB: .3}),
    "selenium": ("Selenium", "tool", {}), "playwright": ("Playwright", "tool", {}), "pyautogui": ("PyAutoGUI", "library", {}),
    # ---- JavaScript / TypeScript ----
    "react": ("React", "framework", {FE: .85}), "react-dom": ("React", "framework", {FE: .8}), "next": ("Next.js", "framework", {FE: .75, BE: .45}),
    "vue": ("Vue", "framework", {FE: .85}), "nuxt": ("Nuxt", "framework", {FE: .75, BE: .45}), "svelte": ("Svelte", "framework", {FE: .85}),
    "@sveltejs/kit": ("SvelteKit", "framework", {FE: .75, BE: .45}), "@angular/core": ("Angular", "framework", {FE: .9}), "solid-js": ("SolidJS", "framework", {FE: .85}),
    "preact": ("Preact", "framework", {FE: .8}), "astro": ("Astro", "framework", {FE: .8}), "@remix-run/react": ("Remix", "framework", {FE: .7, BE: .5}),
    "gatsby": ("Gatsby", "framework", {FE: .8}), "vite": ("Vite", "tool", {FE: .5}), "webpack": ("webpack", "tool", {FE: .4}), "parcel": ("Parcel", "tool", {FE: .4}),
    "tailwindcss": ("Tailwind CSS", "library", {FE: .6}), "bootstrap": ("Bootstrap", "library", {FE: .5}), "@mui/material": ("Material UI", "library", {FE: .6}),
    "antd": ("Ant Design", "library", {FE: .6}), "@chakra-ui/react": ("Chakra UI", "library", {FE: .6}), "styled-components": ("styled-components", "library", {FE: .5}),
    "sass": ("Sass", "tool", {FE: .4}), "three": ("Three.js", "library", {FE: .55}), "@react-three/fiber": ("React Three Fiber", "library", {FE: .6}),
    "d3": ("D3.js", "library", {FE: .4, DATA: .45}), "chart.js": ("Chart.js", "library", {FE: .4, DATA: .3}), "recharts": ("Recharts", "library", {FE: .4, DATA: .3}),
    "echarts": ("ECharts", "library", {FE: .4, DATA: .3}), "framer-motion": ("Framer Motion", "library", {FE: .5}), "gsap": ("GSAP", "library", {FE: .5}),
    "react-router-dom": ("React Router", "library", {FE: .5}), "@tanstack/react-query": ("TanStack Query", "library", {FE: .5}), "zustand": ("Zustand", "library", {FE: .5}),
    "redux": ("Redux", "library", {FE: .5}), "@reduxjs/toolkit": ("Redux", "library", {FE: .5}), "pinia": ("Pinia", "library", {FE: .5}), "vuex": ("Vuex", "library", {FE: .5}),
    "express": ("Express", "framework", {BE: .8}), "koa": ("Koa", "framework", {BE: .8}), "fastify": ("Fastify", "framework", {BE: .85}), "@hapi/hapi": ("hapi", "framework", {BE: .8}),
    "@nestjs/core": ("NestJS", "framework", {BE: .9}), "hono": ("Hono", "framework", {BE: .8}), "socket.io": ("Socket.IO", "library", {BE: .5}), "ws": ("WebSocket (ws)", "library", {BE: .4}),
    "graphql": ("GraphQL", "library", {BE: .5}), "apollo-server": ("Apollo Server", "framework", {BE: .7}), "@apollo/server": ("Apollo Server", "framework", {BE: .7}),
    "@apollo/client": ("Apollo Client", "library", {FE: .5}), "prisma": ("Prisma", "tool", {BE: .55}), "@prisma/client": ("Prisma", "library", {BE: .55}),
    "typeorm": ("TypeORM", "library", {BE: .6}), "sequelize": ("Sequelize", "library", {BE: .6}), "mongoose": ("MongoDB (Mongoose)", "database", {BE: .6}),
    "knex": ("Knex", "library", {BE: .5}), "drizzle-orm": ("Drizzle ORM", "library", {BE: .55}), "pg": ("PostgreSQL", "database", {BE: .45}), "mysql2": ("MySQL", "database", {BE: .45}),
    "ioredis": ("Redis", "database", {BE: .4}), "jsonwebtoken": ("JWT", "library", {BE: .35, SEC: .2}), "passport": ("Passport", "library", {BE: .45, SEC: .2}),
    "bcryptjs": ("bcrypt", "library", {BE: .25, SEC: .3}), "helmet": ("Helmet", "library", {BE: .3, SEC: .2}), "cors": ("CORS", "library", {BE: .3}),
    "dotenv": ("dotenv", "library", {}), "axios": ("Axios", "library", {}), "zod": ("Zod", "library", {}), "typescript": ("TypeScript", "language", {}),
    "react-native": ("React Native", "framework", {MOB: .9}), "expo": ("Expo", "framework", {MOB: .9}), "@ionic/react": ("Ionic", "framework", {MOB: .8}),
    "@ionic/core": ("Ionic", "framework", {MOB: .8}), "@capacitor/core": ("Capacitor", "framework", {MOB: .8}), "nativescript": ("NativeScript", "framework", {MOB: .85}),
    "electron": ("Electron", "framework", {FE: .55}), "@tauri-apps/api": ("Tauri", "framework", {FE: .55}), "@tauri-apps/cli": ("Tauri", "tool", {FE: .5}),
    "@anthropic-ai/sdk": ("Anthropic SDK", "library", {AI: .65, PE: .5}), "@langchain/core": ("LangChain", "framework", {AI: .8, PE: .5}),
    "@langchain/openai": ("LangChain", "framework", {AI: .8, PE: .5}), "llamaindex": ("LlamaIndex", "framework", {AI: .8, PE: .4}),
    "ai": ("Vercel AI SDK", "library", {AI: .6, PE: .45}), "@ai-sdk/openai": ("Vercel AI SDK", "library", {AI: .6, PE: .45}),
    "@google/generative-ai": ("Gemini SDK", "library", {AI: .65, PE: .5}), "@tensorflow/tfjs": ("TensorFlow.js", "framework", {AI: .8}),
    "@tensorflow/tfjs-node": ("TensorFlow.js", "framework", {AI: .8}), "onnxruntime-web": ("ONNX Runtime", "library", {AI: .7}), "onnxruntime-node": ("ONNX Runtime", "library", {AI: .7}),
    "@xenova/transformers": ("Transformers.js", "library", {AI: .8}), "@huggingface/transformers": ("Transformers.js", "library", {AI: .8}),
    "@huggingface/inference": ("Hugging Face Inference", "library", {AI: .7}), "ml5": ("ml5.js", "library", {AI: .7}), "brain.js": ("brain.js", "library", {AI: .7}),
    "@mediapipe/tasks-vision": ("MediaPipe", "library", {AI: .8}), "@modelcontextprotocol/sdk": ("Model Context Protocol", "library", {AI: .6, PE: .5}),
    "jest": ("Jest", "tool", {}), "vitest": ("Vitest", "tool", {}), "mocha": ("Mocha", "tool", {}), "cypress": ("Cypress", "tool", {}), "@playwright/test": ("Playwright", "tool", {}),
    "eslint": ("ESLint", "tool", {}), "prettier": ("Prettier", "tool", {}), "@docusaurus/core": ("Docusaurus", "framework", {DOC: .85}),
    "vitepress": ("VitePress", "framework", {DOC: .85}), "vuepress": ("VuePress", "framework", {DOC: .85}), "@storybook/react": ("Storybook", "tool", {FE: .5}),
    "puppeteer": ("Puppeteer", "tool", {}), "cheerio": ("Cheerio", "library", {DATA: .3}), "serverless": ("Serverless Framework", "tool", {OPS: .6, BE: .3}),
    "aws-sdk": ("AWS SDK", "platform", {OPS: .35, BE: .2}), "firebase": ("Firebase", "platform", {BE: .4, MOB: .2}), "firebase-admin": ("Firebase", "platform", {BE: .5}),
    "@supabase/supabase-js": ("Supabase", "platform", {BE: .45}), "ethers": ("Ethers.js (Web3)", "library", {BE: .3}), "web3": ("Web3.js", "library", {BE: .3}),
    "hardhat": ("Hardhat", "tool", {BE: .4}), "@solana/web3.js": ("Solana Web3", "library", {BE: .3}), "telegraf": ("Telegram Bot", "library", {BE: .45}),
    "discord.js": ("Discord Bot", "library", {BE: .45}), "grammy": ("Telegram Bot", "library", {BE: .45}), "node-fetch": ("node-fetch", "library", {}),
    "pm2": ("PM2", "tool", {OPS: .4}), "dockerode": ("Docker SDK", "library", {OPS: .5}), "@kubernetes/client-node": ("Kubernetes", "platform", {OPS: .7}),
    "nodemon": ("nodemon", "tool", {BE: .2}), "ts-node": ("ts-node", "tool", {}), "tsx": ("tsx", "tool", {}), "esbuild": ("esbuild", "tool", {}),
    # ---- Rust ----
    "tokio": ("Tokio", "framework", {BE: .35}), "actix-web": ("Actix Web", "framework", {BE: .85}), "axum": ("Axum", "framework", {BE: .85}), "rocket": ("Rocket", "framework", {BE: .85}),
    "warp": ("Warp", "framework", {BE: .8}), "hyper": ("Hyper", "library", {BE: .5}), "reqwest": ("reqwest", "library", {}), "serde": ("Serde", "library", {}),
    "diesel": ("Diesel", "library", {BE: .55}), "sqlx": ("SQLx", "library", {BE: .55}), "sea-orm": ("SeaORM", "library", {BE: .55}), "tch": ("PyTorch (tch-rs)", "framework", {AI: .8}),
    "candle-core": ("Candle", "framework", {AI: .8}), "burn": ("Burn", "framework", {AI: .8}), "ndarray": ("ndarray", "library", {DATA: .4}), "clap": ("clap (CLI)", "library", {}),
    "yew": ("Yew", "framework", {FE: .85}), "leptos": ("Leptos", "framework", {FE: .8, BE: .3}), "dioxus": ("Dioxus", "framework", {FE: .75}), "tauri": ("Tauri", "framework", {FE: .55}),
    "bevy": ("Bevy", "framework", {FE: .3}), "wgpu": ("wgpu", "library", {FE: .3}), "ring": ("ring (crypto)", "library", {SEC: .4}), "rustls": ("rustls", "library", {SEC: .4}),
    "openssl": ("OpenSSL", "library", {SEC: .3}), "pnet": ("pnet (packets)", "library", {SEC: .7}), "wasm-bindgen": ("WebAssembly", "library", {FE: .5}),
    # ---- Go ----
    "github.com/gin-gonic/gin": ("Gin", "framework", {BE: .85}), "github.com/labstack/echo/v4": ("Echo", "framework", {BE: .85}), "github.com/labstack/echo": ("Echo", "framework", {BE: .85}),
    "github.com/gofiber/fiber/v2": ("Fiber", "framework", {BE: .85}), "github.com/gorilla/mux": ("Gorilla Mux", "library", {BE: .75}), "github.com/go-chi/chi/v5": ("chi", "library", {BE: .75}),
    "google.golang.org/grpc": ("gRPC", "library", {BE: .6}), "k8s.io/client-go": ("Kubernetes", "platform", {OPS: .75}), "github.com/spf13/cobra": ("Cobra (CLI)", "library", {}),
    "github.com/docker/docker": ("Docker SDK", "library", {OPS: .55}), "gorm.io/gorm": ("GORM", "library", {BE: .55}), "github.com/aws/aws-sdk-go": ("AWS SDK", "platform", {OPS: .35}),
    "github.com/hashicorp/terraform-plugin-sdk/v2": ("Terraform", "tool", {OPS: .85}), "github.com/prometheus/client_golang": ("Prometheus", "tool", {OPS: .5}),
    "github.com/google/gopacket": ("gopacket", "library", {SEC: .7}), "github.com/projectdiscovery/nuclei/v2": ("Nuclei", "tool", {SEC: .9}),
    # ---- Dart / Flutter ----
    "flutter": ("Flutter", "framework", {MOB: .9}), "flutter_bloc": ("Flutter (BLoC)", "library", {MOB: .7}), "provider": ("Flutter (Provider)", "library", {MOB: .5}),
    "riverpod": ("Riverpod", "library", {MOB: .6}), "flutter_riverpod": ("Riverpod", "library", {MOB: .6}), "dio": ("Dio", "library", {MOB: .4}),
    "firebase_core": ("Firebase", "platform", {MOB: .5}), "tflite_flutter": ("TensorFlow Lite", "library", {AI: .7, MOB: .5}), "get": ("GetX", "library", {MOB: .5}),
    # ---- Ruby / PHP / Elixir ----
    "rails": ("Ruby on Rails", "framework", {BE: .85}), "sinatra": ("Sinatra", "framework", {BE: .8}), "devise": ("Devise", "library", {BE: .3, SEC: .2}),
    "jekyll": ("Jekyll", "tool", {DOC: .6, FE: .3}), "laravel/framework": ("Laravel", "framework", {BE: .85}), "symfony/symfony": ("Symfony", "framework", {BE: .85}),
    "symfony/framework-bundle": ("Symfony", "framework", {BE: .85}), "slim/slim": ("Slim", "framework", {BE: .8}), "phoenix": ("Phoenix", "framework", {BE: .85}),
    # ---- Java / Kotlin / .NET ----
    "junit": ("JUnit", "tool", {}), "org.apache.spark:spark-core": ("Apache Spark", "framework", {DATA: .8}), "org.apache.kafka:kafka-clients": ("Apache Kafka", "platform", {BE: .4, DATA: .4}),
    "org.deeplearning4j:deeplearning4j-core": ("Deeplearning4j", "framework", {AI: .8}), "org.tensorflow:tensorflow": ("TensorFlow", "framework", {AI: .8}),
    "org.hibernate:hibernate-core": ("Hibernate", "library", {BE: .55}), "com.squareup.retrofit2:retrofit": ("Retrofit", "library", {MOB: .4}),
    "microsoft.entityframeworkcore": ("Entity Framework Core", "library", {BE: .55}), "microsoft.ml": ("ML.NET", "framework", {AI: .8}), "avalonia": ("Avalonia", "framework", {FE: .4}),
    "unity": ("Unity", "platform", {}), "swashbuckle.aspnetcore": ("Swagger", "tool", {BE: .5}),
    # ---- Terraform providers etc. handled by file rules ----
}

PREFIX_MAP: list[tuple[str, TechEntry]] = [
    ("@aws-sdk/", ("AWS SDK", "platform", {OPS: .35, BE: .2})), ("@azure/", ("Azure SDK", "platform", {OPS: .35, BE: .2})),
    ("@google-cloud/", ("Google Cloud SDK", "platform", {OPS: .35, BE: .2})), ("azure-", ("Azure SDK", "platform", {OPS: .35})),
    ("google-cloud-", ("Google Cloud SDK", "platform", {OPS: .35})), ("@angular/", ("Angular", "framework", {FE: .85})),
    ("@nestjs/", ("NestJS", "framework", {BE: .85})), ("@react-native", ("React Native", "framework", {MOB: .85})), ("react-native-", ("React Native", "framework", {MOB: .8})),
    ("expo-", ("Expo", "framework", {MOB: .8})), ("@expo/", ("Expo", "framework", {MOB: .8})), ("@langchain/", ("LangChain", "framework", {AI: .8, PE: .5})),
    ("langchain-", ("LangChain", "framework", {AI: .8, PE: .5})), ("llama-index-", ("LlamaIndex", "framework", {AI: .8, PE: .4})), ("@ai-sdk/", ("Vercel AI SDK", "library", {AI: .6, PE: .45})),
    ("@mui/", ("Material UI", "library", {FE: .6})), ("@radix-ui/", ("Radix UI", "library", {FE: .6})), ("@headlessui/", ("Headless UI", "library", {FE: .5})),
    ("@tanstack/", ("TanStack", "library", {FE: .4})), ("@storybook/", ("Storybook", "tool", {FE: .5})), ("@testing-library/", ("Testing Library", "tool", {FE: .3})),
    ("@ionic/", ("Ionic", "framework", {MOB: .8})), ("@capacitor/", ("Capacitor", "framework", {MOB: .8})), ("@tauri-apps/", ("Tauri", "framework", {FE: .55})),
    ("org.springframework", ("Spring", "framework", {BE: .85})), ("io.quarkus", ("Quarkus", "framework", {BE: .85})), ("io.micronaut", ("Micronaut", "framework", {BE: .85})),
    ("com.android", ("Android", "platform", {MOB: .9})), ("androidx.", ("Android (Jetpack)", "platform", {MOB: .9})), ("com.google.android", ("Android", "platform", {MOB: .85})),
    ("io.ktor", ("Ktor", "framework", {BE: .8})), ("org.jetbrains.compose", ("Compose Multiplatform", "framework", {MOB: .6, FE: .3})),
    ("microsoft.aspnetcore", ("ASP.NET Core", "framework", {BE: .85})), ("xamarin.", ("Xamarin", "framework", {MOB: .9})), ("microsoft.maui", (".NET MAUI", "framework", {MOB: .9})),
    ("@tensorflow/", ("TensorFlow.js", "framework", {AI: .8})), ("@huggingface/", ("Hugging Face", "library", {AI: .7})), ("@modelcontextprotocol/", ("Model Context Protocol", "library", {AI: .6, PE: .5})),
    ("@sveltejs/", ("Svelte", "framework", {FE: .8})), ("@vue/", ("Vue", "framework", {FE: .8})), ("@nuxt/", ("Nuxt", "framework", {FE: .75, BE: .4})), ("@remix-run/", ("Remix", "framework", {FE: .7, BE: .5})),
    ("@solana/", ("Solana Web3", "library", {BE: .3})), ("@prisma/", ("Prisma", "tool", {BE: .55})), ("@supabase/", ("Supabase", "platform", {BE: .45})),
    ("@sentry/", ("Sentry", "tool", {OPS: .3})), ("@opentelemetry/", ("OpenTelemetry", "tool", {OPS: .4})), ("@kubernetes/", ("Kubernetes", "platform", {OPS: .7})),
    ("@pulumi/", ("Pulumi", "tool", {OPS: .85})), ("cdktf", ("Terraform CDK", "tool", {OPS: .85})), ("aws-cdk", ("AWS CDK", "tool", {OPS: .85})),
    ("opencv", ("OpenCV", "library", {AI: .5})), ("torch", ("PyTorch", "framework", {AI: .7})), ("tensorflow", ("TensorFlow", "framework", {AI: .7})),
    ("transformers", ("Hugging Face Transformers", "library", {AI: .7})), ("scikit-", ("scikit-learn", "library", {AI: .5, DATA: .3})),
    ("django-", ("Django", "framework", {BE: .7})), ("flask-", ("Flask", "framework", {BE: .7})), ("fastapi-", ("FastAPI", "framework", {BE: .7})),
    ("pytest-", ("pytest", "tool", {})), ("sqlalchemy-", ("SQLAlchemy", "library", {BE: .4})), ("celery-", ("Celery", "framework", {BE: .5})),
]

IMAGE_MAP: dict[str, TechEntry] = {
    "postgres": ("PostgreSQL", "database", {BE: .4, DATA: .2}), "mysql": ("MySQL", "database", {BE: .4}), "mariadb": ("MariaDB", "database", {BE: .4}),
    "mongo": ("MongoDB", "database", {BE: .4}), "redis": ("Redis", "database", {BE: .4}), "nginx": ("Nginx", "tool", {OPS: .35, BE: .2}),
    "traefik": ("Traefik", "tool", {OPS: .5}), "rabbitmq": ("RabbitMQ", "platform", {BE: .4}), "kafka": ("Apache Kafka", "platform", {BE: .4, DATA: .4}),
    "elasticsearch": ("Elasticsearch", "database", {BE: .4, DATA: .4}), "opensearch": ("OpenSearch", "database", {BE: .4, DATA: .4}),
    "ollama": ("Ollama", "platform", {AI: .6}), "grafana": ("Grafana", "tool", {OPS: .5}), "prometheus": ("Prometheus", "tool", {OPS: .5}),
    "minio": ("MinIO", "platform", {BE: .3, OPS: .3}), "keycloak": ("Keycloak", "platform", {SEC: .45, BE: .3}), "vault": ("HashiCorp Vault", "platform", {SEC: .5, OPS: .4}),
    "pgvector": ("pgvector", "database", {AI: .5}), "qdrant": ("Qdrant", "database", {AI: .7}), "chroma": ("ChromaDB", "database", {AI: .7}),
    "weaviate": ("Weaviate", "database", {AI: .7}), "milvus": ("Milvus", "database", {AI: .7}), "clickhouse": ("ClickHouse", "database", {DATA: .6}),
    "airflow": ("Apache Airflow", "framework", {DATA: .7}), "jupyter": ("Jupyter", "tool", {DATA: .5}), "python": ("Python", "language", {}),
    "node": ("Node.js", "language", {}), "golang": ("Go", "language", {}), "rust": ("Rust", "language", {}), "nvidia": ("NVIDIA CUDA", "platform", {AI: .6}),
    "pytorch": ("PyTorch", "framework", {AI: .8}), "tensorflow": ("TensorFlow", "framework", {AI: .8}), "huggingface": ("Hugging Face", "library", {AI: .7}),
    "vllm": ("vLLM", "library", {AI: .85}), "localai": ("LocalAI", "platform", {AI: .7}), "kali": ("Kali Linux", "platform", {SEC: .8}),
    "metasploit": ("Metasploit", "tool", {SEC: .9}), "zap": ("OWASP ZAP", "tool", {SEC: .85}), "wazuh": ("Wazuh", "platform", {SEC: .8}),
}


def lookup(dep: str) -> TechEntry | None:
    dep = dep.lower()
    if dep in TECH_MAP:
        return TECH_MAP[dep]
    for prefix, entry in PREFIX_MAP:
        if dep.startswith(prefix):
            return entry
    return None


def lookup_image(image: str) -> TechEntry | None:
    base = image.split("@")[0].split(":")[0]
    last = base.split("/")[-1]
    for candidate in (base, last):
        if candidate in IMAGE_MAP:
            return IMAGE_MAP[candidate]
    for key, entry in IMAGE_MAP.items():
        if key in last:
            return entry
    return None
