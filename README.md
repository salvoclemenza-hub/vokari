# VOKARI — Voce → Conoscenza

**Transform voice recordings into structured knowledge artifacts.** VOKARI captures audio (local only), transcribes with faster-whisper, analyzes with Claude or Ollama, and generates markdown artifacts for your second brain — all 100% locally.

- 🎤 **Voice input** → registra/importa (mic, system audio, or both)
- 📝 **Transcription** → faster-whisper locale (no cloud)
- 🧠 **Analysis** → Claude API or Ollama (local optional)
- 📦 **Output** → `briefing.md` (for LLM) + recap + Obsidian notes
- 🔐 **Privacy** → audio never leaves your device; only text goes to AI

**Status:** v1 complete and tested (M1–M7, 379 backend tests + 137 frontend tests). Ready for use.

## Quick Start

### Requirements

- **Windows 10+** (system audio capture via WASAPI loopback; Mac/Linux support in v2)
- **Python 3.12+** (bundled with installer; or `uv 0.5+` for dev)
- **ffmpeg** in PATH (for audio conversion; install via `choco install ffmpeg` or `winget install ffmpeg`)
- **API key** for Claude (Anthropic) or local Ollama if using that brain
- **~500 MB** disk (models download on-demand via faster-whisper)

### Installation

**Windows users (recommended):**
1. Download the VOKARI installer (.exe) — *coming soon, for now use dev setup*
2. Run the installer; choose your API key in Settings
3. Launch from Start Menu

**Development setup (any OS):**
```bash
# Clone or extract repo
git clone https://github.com/salvoclemenza-hub/vokari.git && cd vokari

# Install Python dependencies (uses uv)
uv sync

# Install frontend dependencies
cd frontend && pnpm install && cd ..

# Run app (opens GUI)
"Avvia VOKARI.bat"  # Windows
# Or manually:
cd frontend && pnpm build && cd ..
uv run python app/main.py
```

## Features

### Recording & Import
- **Mic input** — your voice
- **System audio** — meeting/call participants (Windows only, via WASAPI loopback)
- **Both** — mix your voice + system audio
- **Manual markers** — pause and add labels to key moments

### Processing
- **Real-time transcription** — streaming display as audio is processed
- **Faster-whisper** — local, CPU (works on AMD; ~5–15 min per hour on typical machine)
- **Automatic model download** — distilled models by default; larger models on demand
- **Cache** — re-processing the same audio is instant (hash-based)

### Analysis & Artifacts
- **`briefing.md`** — always generated
  - YAML frontmatter (date, session ID, type, participants, duration, LLM model)
  - Context, decisions, summary, open questions
  - Raw transcript for ground truth
  - `[DA CHIARIRE: ...]` markers for clarification needed (skipped interview questions)
  - Next steps checklist
  
- **`recap.md`** — human-readable summary (Markdown)

- **PDF export** — recap as PDF for sharing

- **Obsidian export** — atomic notes + ADR template for your vault (optional second brain)

### Interview (Optional)
- Auto-detect **3–5 key questions** from transcript
- Skip any question, add open responses
- Responses merged back into briefing for refinement
- Skipped questions marked as `[DA CHIARIRE: ...]`

### Settings
- **LLM brain** — Claude (default, via Anthropic API) or Ollama local
- **API key** — stored securely in OS keyring (never in files)
- **Default session type** — solo (brainstorm) or riunione (meeting; affects analysis focus)
- **Briefing folder** — where `.md` files are saved
- **Obsidian vault** — optional, for second-brain export
- **Transcription model** — Whisper model selection + download progress
- **Language** — auto-detect or force IT/EN

### Sessions Library
- **Persistent storage** — every session saved with artifacts
- **Full-text search** — find past sessions by content
- **Filtering** — by type (solo/riunione)
- **Quick access** → click session → view artifacts

## Architecture

Three components, zero dependencies on cloud (optional: Claude API only if using that brain):

### **Engine** (`src/vokari/`) — Library + CLI
- **audio/**: cattura (sounddevice mic + WASAPI system audio + mix) → WAV 16k mono
- **transcribe/**: faster-whisper + caching + model management
- **llm/**: Claude or Ollama interface (Protocol-based)
- **analyze/**: transcript → structured JSON (pydantic schema)
- **render/**: JSON → briefing.md/recap/obsidian
- **store/**: Sessions persistenza + full-text search

CLI: `vokari transcribe audio.wav` → `transcript.txt` | `vokari brief audio.wav` → `briefing.md` | `vokari rec` → record live

### **App Host** (`app/`) — pywebview Shell
- **main.py**: opens GUI window, serves `frontend/dist/`
- **api.py**: Python methods callable from JS (`window.pywebview.api`)
- **jobs.py**: `Job` + `JobStore` for persistent state + resume-on-crash
- **pipeline.py**: orchestrates transcribe → analyze → interview → render

### **Frontend** (`frontend/`) — React + Vite → `dist/`
- **9 screens**: Home, Live, Processing, Interview, Artifacts, Sessions, Models, Settings, Error
- **Chrome**: Titlebar + Sidebar + StatusBar (shared layout)
- **Styling**: Tailwind-like (custom CSS, `vokari.css`)
- **Real-time**: `audio_level` events for live wave display

## Development

VOKARI is built in three layers by responsibility: the **engine** (`src/vokari/`, a testable library + CLI), the **app host** (`app/`, the pywebview shell), and the **frontend** (`frontend/`, React + Vite → `dist/`).

> **Golden rule:** pywebview serves the **compiled** `frontend/dist/`, not source. After editing `frontend/src/`, run `cd frontend && pnpm build` (or just relaunch — `Avvia VOKARI.bat` rebuilds automatically when sources are newer than `dist/`).

**Test & verify:**
```bash
# Backend (Python)
uv run pytest              # 379 tests
uv run ruff check          # lint

# Frontend (JS/TS)
cd frontend && pnpm test   # 137 tests (vitest)
cd frontend && pnpm build  # type check + bundle

# End-to-end headless (no GUI)
uv run python scripts/e2e_smoke.py your-audio.m4a
```

## Roadmap (v2+)

- ✅ v1: local transcription + briefing + recap + Obsidian export (complete)
- 📋 v2: Mac/Linux system audio · speaker attribution · RAG on vault · batch/watch-folder
- 📦 v2: PyInstaller installer + CI + GitHub release
- 🤖 v3: advanced: sentiment analysis, action items extraction, multi-LLM comparison

## Privacy & Security

- ✅ **Audio never leaves device** — all processing local (ffmpeg + faster-whisper CPU)
- ✅ **API key in OS keyring** — never in files, never in git
- ✅ **Only transcript text to LLM** — audio metadata/waveforms stay private
- ✅ **No telemetry** — no tracking, no analytics
- ✅ **Open source** — MIT license, code auditable

## Troubleshooting

### "After I edit frontend, nothing changes"
→ pywebview serves the **compiled** `frontend/dist/`, not source. After editing `frontend/src/`, run:
```bash
cd frontend && pnpm build
```
(Or restart VOKARI; the launcher checks and rebuilds automatically.)

### "System audio not capturing (Windows)"
→ WASAPI loopback requires a virtual audio device. Options:
1. VB-Cable / Virtual Audio Cable (free/paid)
2. Record mic + interlocutor manually in same file
3. Use "Both" and let it fall back to mic if system fails

### "Transcription is very slow"
→ `large-v3-turbo` is intentionally small & fast. Use it for long audio (1+ hour). For accuracy, switch to `large-v3` in Settings → Models. First download takes ~2 GB.

### "Claude API key not saving"
→ Check OS keyring is accessible. On Windows: Settings → Developer Settings → enable "Use developer features" or equivalent. If keyring fails, restart and try again.

## License

MIT — use freely, modify, redistribute.

## Credits

- **faster-whisper** — OpenAI Whisper via CTranslate2 (efficient CPU inference)
- **Claude API** — Anthropic
- **Design system** — handoff from Claude Design + Material tokens
- **Built by** — Salvo Clemenza (team: 4 people, alimentary warehouse B2B/B2C)

---

**Questions?** Open an issue.
