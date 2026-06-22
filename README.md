# VOKARI — Voce → Conoscenza

> Turn a voice recording into structured knowledge. **100% local** transcription, AI analysis, and Markdown artifacts for your second brain.

![CI](https://github.com/salvoclemenza-hub/vokari/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)
![Platform: Windows 10/11](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6.svg)

<p align="center">
  <img src="screenshots/home.png" alt="VOKARI — schermata Home" width="820">
</p>

**VOKARI** is a local-first Windows desktop app: record or import audio, transcribe it on-device with [faster-whisper](https://github.com/SYSTRAN/faster-whisper), analyze the text with Claude or a local Ollama model, and get clean Markdown artifacts — a `briefing.md` optimized for LLMs, a human-readable recap (+PDF), and atomic Obsidian notes.

**Your audio never leaves your machine** — only the transcribed *text* is sent to the AI, and even that stays local if you choose Ollama.

- 🎤 **Record** (mic, system audio, or both) or **import** any audio file
- 📝 **On-device transcription** — faster-whisper, no cloud
- 🧠 **Analysis** — Claude API or local Ollama
- 📦 **Output** — `briefing.md` + recap + PDF + Obsidian notes
- 🔐 **Privacy-first** — audio stays on your device; secrets live in the OS keyring

**Status:** v1 — the full flow works and is CI-gated (500+ automated tests: ~380 backend with pytest, ~140 frontend with vitest).

---

## 📥 Installation

### 📦 Packaged build (easiest) — *coming on the Releases page*

A ready-to-run Windows package will be published on the **[Releases](https://github.com/salvoclemenza-hub/vokari/releases)** page: download, run the included setup script, and launch from the desktop shortcut — no toolchain required.

> ℹ️ It ships as a **ZIP + PowerShell setup script** (installed to your user folder, no admin) rather than a classic `.exe` installer, because Windows 11 Smart App Control blocks unsigned `.exe` files. A code-signed build (via [SignPath Foundation](https://signpath.org/) for open source) is planned to make installation one-click.

### 🛠 Developer setup (works today)

Requirements: **Python 3.12+** (or [`uv`](https://docs.astral.sh/uv/)), **[pnpm](https://pnpm.io/)**, **[ffmpeg](https://ffmpeg.org/)** in your `PATH`, and a **Claude API key** (or a local Ollama install).

```bash
git clone https://github.com/salvoclemenza-hub/vokari.git && cd vokari

uv sync                                   # Python deps → .venv
cd frontend && pnpm install && pnpm build && cd ..

"Avvia VOKARI.bat"                        # Windows — rebuilds the UI if needed, then opens the app
# or, manually:  uv run python app/main.py
```

ffmpeg on Windows: `winget install ffmpeg` (or `choco install ffmpeg`).

---

## 🚀 Guida rapida all'uso (Italiano)

*Per chi deve semplicemente usare VOKARI, una volta che è avviata.*

1. **Chiave API** — apri **Impostazioni** e incolla la tua chiave Claude (la ottieni su [console.anthropic.com](https://console.anthropic.com) → *API keys*). La chiave viene salvata nel **keyring di Windows**, mai in un file. In alternativa puoi usare **Ollama** in locale: nessuna chiave, nessun costo, tutto sul tuo PC.
2. **Registra o importa** — dalla **Home** scegli *Registra* (microfono, audio di sistema, o entrambi) oppure *Importa* un file audio già esistente.
3. **Trascrizione** — parte in automatico ed è **locale**. Per circa un'ora di audio servono ~5–15 minuti su CPU.
4. **Intervista (opzionale)** — VOKARI propone 3–5 domande per chiarire i punti aperti: puoi rispondere o saltare. Le risposte vengono integrate nel briefing.
5. **Artefatti** — ottieni **`briefing.md`** (pensato per essere dato in pasto a un'altra AI), un **recap** leggibile (+PDF) e, se l'hai configurato, le **note Obsidian**. La cartella di destinazione si imposta in *Impostazioni → Cartella briefing*; ogni sessione resta archiviata e ricercabile nella libreria **Sessioni**.

> 💡 La prima volta che usi un modello di trascrizione, VOKARI lo scarica (da qualche centinaio di MB fino a ~1.6 GB per i modelli grandi). Succede una sola volta.

---

## 📸 Screenshots

| Briefing artifacts (`briefing.md`) | AI models |
| :---: | :---: |
| ![Artifacts view — briefing.md with structured sections](screenshots/artifacts.png) | ![AI models — Claude / Ollama management](screenshots/models.png) |

---

## ✨ Features

**Recording & import** — mic, system audio (Windows WASAPI loopback), both mixed, or import any file. Live transcription preview while you record.

**Processing** — streaming transcription with faster-whisper on CPU (works on AMD too); automatic model download (`large-v3-turbo` by default — fast; switch to `large-v3` for maximum accuracy); hash-based cache, so re-processing the same audio is instant.

**Analysis & artifacts**
- **`briefing.md`** — YAML frontmatter (date, session ID, type, duration, LLM model), context · decisions · summary · open questions, the raw transcript for ground truth, `[DA CHIARIRE: ...]` markers for skipped interview questions, and a next-steps checklist.
- **`recap.md`** — human-readable summary · **PDF export** for sharing · **Obsidian export** — atomic notes for your vault.

**Interview (optional)** — auto-detects 3–5 key questions from the transcript; skip or answer; responses are merged back into the briefing.

**Settings** — LLM brain (Claude / Ollama), API key in OS keyring, default session type (*solo* brainstorm / *riunione* meeting), briefing folder, Obsidian vault, Whisper model + download progress, language (auto / IT / EN).

**Sessions library** — persistent storage, full-text search, filtering by type.

---

## 🏗 Architecture

Three components organized by **responsibility**, not by technical layer — zero cloud dependencies (Claude API is optional, only if you pick that brain).

### Engine (`src/vokari/`) — library + CLI
- **audio/** — capture (sounddevice mic + WASAPI system audio + mix) → WAV 16k mono
- **transcribe/** — faster-whisper + caching + model management
- **llm/** — Claude or Ollama, behind a single Protocol (`factory.make_provider`)
- **analyze/** — transcript → structured JSON (pydantic schema) + interview
- **render/** — JSON → briefing.md / recap / Obsidian / PDF
- **store/** — sessions persistence + full-text search

CLI: `vokari transcribe audio.wav` · `vokari brief audio.wav` · `vokari rec`

### App host (`app/`) — pywebview shell
- **main.py** — opens the GUI window, serves the compiled `frontend/dist/`
- **api.py** — Python methods callable from JS (`window.pywebview.api`)
- **jobs.py** — `Job` + `JobStore` for persistent state + resume-on-crash
- **pipeline.py** — orchestrates transcribe → analyze → interview → render

### Frontend (`frontend/`) — React + TypeScript + Vite → `dist/`
- **9 screens** — Home, Live, Processing, Interview, Artifacts, Sessions, Models, Settings, Error
- Shared chrome (Titlebar + Sidebar + StatusBar); custom CSS design system
- Real-time push events (`audio_level`, `transcribe_progress`, `analysis_preview`, …) — no polling

---

## 🧪 Development

> **Golden rule:** pywebview serves the **compiled** `frontend/dist/`, not the source. After editing `frontend/src/`, run `cd frontend && pnpm build` (or just relaunch — `Avvia VOKARI.bat` rebuilds when sources are newer than `dist/`).

```bash
# Backend (Python)
uv run pytest                  # test suite
uv run ruff check              # lint

# Frontend (JS/TS)
cd frontend && pnpm test       # vitest
cd frontend && pnpm exec tsc -b   # strict type check
cd frontend && pnpm build      # bundle

# End-to-end, headless (no GUI)
uv run python scripts/e2e_smoke.py your-audio.m4a
```

---

## 🔐 Privacy & Security

- ✅ **Audio never leaves your device** — all processing is local (ffmpeg + faster-whisper on CPU)
- ✅ **API key in the OS keyring** — never in files, never in git
- ✅ **Only transcript text reaches the LLM** — and nothing leaves the machine at all with Ollama
- ✅ **No telemetry** — no tracking, no analytics
- ✅ **Open source** — MIT, fully auditable

---

## 🗺 Roadmap

- ✅ **v1** — local transcription + briefing + recap + Obsidian export (done)
- 📦 **v1.x** — packaged Windows release (ZIP/setup) + code-signed build
- 📋 **v2** — macOS/Linux system-audio capture · speaker attribution · RAG over your vault · batch / watch-folder
- 🤖 **v3** — sentiment analysis, action-item extraction, multi-LLM comparison

---

## 🩹 Troubleshooting

**"After I edit the frontend, nothing changes"** — pywebview serves the compiled `frontend/dist/`. Run `cd frontend && pnpm build` (or restart; the launcher rebuilds automatically).

**"System audio isn't captured (Windows)"** — WASAPI loopback needs a playing output device. Use *Both* (it falls back to mic if the system lane is silent), or capture mic only.

**"Transcription is very slow"** — `large-v3-turbo` (the default) is small and fast; prefer it for long audio. Switch to `large-v3` in *Settings → Models* only when you need maximum accuracy (first download ~2 GB).

**"The Claude API key won't save"** — VOKARI uses the OS keyring. Make sure Windows Credential Manager is accessible, then restart and try again. (Or switch to Ollama, which needs no key.)

---

## 📄 License

[MIT](LICENSE) — use freely, modify, redistribute.

## 🙏 Credits

A personal project designed and built by **Salvo Clemenza**.

Standing on the shoulders of:
- **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** — OpenAI Whisper via CTranslate2 (efficient CPU inference)
- **[Claude API](https://www.anthropic.com/)** — Anthropic
- **[pywebview](https://pywebview.flowrl.com/)** + **React** + **Vite**

---

**Questions or bugs?** [Open an issue](https://github.com/salvoclemenza-hub/vokari/issues).
