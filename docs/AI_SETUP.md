# Optional local AI

Everything in Project Nexus works without a model. The AI Assistant is an **opt-in extra** that can suggest categories, a one-sentence description and technology names for a project, using a model that runs on your own machine.

## 1. Run a local model server

**Ollama (recommended)**

1. Install from <https://ollama.com>.
2. Pull a small instruction model: `ollama pull llama3.2` (≈2 GB). Any chat model works; smaller models answer faster.
3. Ollama normally runs as a background service on `http://127.0.0.1:11434`. If not: `ollama serve`.

**Any OpenAI-compatible local server** (LM Studio, llama.cpp `llama-server`, vLLM, LocalAI …)

- Start the server and note its base URL, e.g. LM Studio: `http://127.0.0.1:1234`.
- In Nexus choose provider *OpenAI-compatible* and enter the model id the server reports under `/v1/models`.

## 2. Enable it in Nexus

*AI Assistant* → toggle **Enable local AI** → check provider / endpoint / model → **Test connection** (shows whether the endpoint is reachable and whether the model exists) → **Save AI settings**.

By default only **local** endpoints (`127.0.0.1`, `localhost`, `::1`) are accepted. A remote URL is refused unless you deliberately tick *Allow a non-local endpoint* — then Nexus warns you, because your project metadata would leave the machine.

## 3. Ask for a suggestion

In any project's details panel press **Ask local AI about this project**. The dialog shows:

- the **fields** that will be shared (each is a checkbox):
  - project name and type
  - languages (measured file counts)
  - manifest file names
  - dependency names (max 60)
  - rule-detected technologies and categories
  - README excerpt (max 1500 characters, markdown stripped)
  - top-level file names (max 60, secret-looking files excluded)
- a **preview of the exact JSON** that will be sent;
- a consent checkbox. Nothing is sent until you tick it and press *Send*.

The answer becomes a **pending suggestion** with the model's categories, description, technologies, confidence and reasoning. *Accept* applies it as a manual category override (and optionally the description); *Reject* discards it. Pending suggestions are also listed in the AI Assistant view. Identical requests are cached, so re-asking the same question for an unchanged project costs nothing.

## What is never sent

- File contents of any kind (source code, data, notebooks). Only the README excerpt and manifest *dependency names* are text derived from files.
- Files whose names look like secrets: `.env*`, `*.pem`, `*.key`, `id_rsa*`, `*credential*`, `*secret*`, `*token*`, `*password*`, keystores, cloud credential JSON files, anything under `.ssh`, `.aws`, `.kube`, … These are flagged in the file list ("sensitive — never sent to AI") and excluded from every payload.
- Absolute paths, workspace roots, your settings, other projects.

## Safety of model output

The model's reply is parsed as JSON and **schema-validated**: categories must come from the fixed list, strings are length-capped and control characters removed, confidence is clamped to 0–1. The output is only ever shown to you and, on *Accept*, stored as a category override / description. It cannot change settings, add workspaces, open paths or run anything. Project text (README, file names) is passed to the model as *data* inside a JSON object with a system prompt stating it is untrusted; a README that contains "ignore previous instructions" is just a README.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| *Not reachable* | Ollama/LM Studio not running, wrong port, or firewall. `curl http://127.0.0.1:11434/api/tags` should answer. |
| *Model not found on server* | Pull it: `ollama pull <name>`; or pick a listed model from the dropdown. |
| *local model did not answer in time* | Increase *Timeout (s)* (large models on CPU can take a minute), or use a smaller model. |
| *model returned malformed JSON* | Some tiny models ignore the JSON instruction; try `llama3.2`, `qwen2.5`, `mistral` or a larger variant. |
| *too many AI requests queued* | Requests run one at a time; wait for the current one. |
