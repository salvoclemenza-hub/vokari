# Changelog

User-facing changelog for **VOKARI** — the local-first Windows app that turns a voice
recording into structured Markdown (transcription, AI analysis, and second-brain notes),
all on your own machine. Items here describe what changed for *you*, not the code.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Work completed after 0.2.0 but not yet shipped in a numbered release.

### Added
- **Review and edit the transcript before analysis.** A new step lets you correct the
  transcribed text (fix names, terms, typos) before VOKARI sends it to the AI, so the
  briefing is built from exactly what you intended. Includes a live word count and a
  keyboard shortcut to continue.
- **A briefing draft beside the interview.** The optional interview now shows a draft of
  your briefing next to the questions, so you can see the picture filling in as you
  answer instead of replying blind.
- **"Add more context" field.** During the interview you can type extra background in
  free text; it's folded into the briefing along with your answers.
- **Heads-up before summarizing long recordings.** If a transcript is too long for the
  selected model, VOKARI now pauses and asks before producing a lossy summary, letting
  you proceed anyway, cancel, or switch model in Settings — instead of silently losing
  detail.
- **Low disk space warning before recording.** VOKARI checks free space before a
  recording starts: it stops you outright if there's almost none left, and warns (without
  blocking) when space is getting low — so a long recording can't quietly fail and lose
  your audio.
- **"Your context" setting.** A neutral, general-purpose setting where you can describe
  your own domain, so the analysis fits how *you* work rather than any preset use case.

### Changed
- **Cleaner handling of long audio.** Long recordings are now split into overlapping
  chunks with automatic de-duplication, so sentences are no longer cut in half (or
  repeated) at the 10-minute boundaries — more accurate transcripts for long sessions.
- **Neutral, general-purpose prompts.** The AI analysis is no longer tuned to one specific
  field, making the briefings useful across a wider range of topics.

## [0.2.0] - 2026-06-27

First release submitted to the **Microsoft Store**. The big themes: a smoother first run
on brand-new PCs, full English/Italian support, and a long list of flow fixes.

### Added
- **Fully bilingual — English and Italian.** Switch the entire app between English and
  Italian from Settings. This drives not just the interface but the **AI-generated output**
  too: the briefing, recap, and Obsidian notes are written in your chosen language,
  regardless of the spoken language of the audio. (The transcription language stays a
  separate setting.)
- **Guided first-run onboarding.** New setup help walks you through installing a local
  AI engine (Ollama) on a fresh PC — the main reason 0.1.1 felt like it "didn't work" on
  some machines.
- **Microsoft Store package (MSIX).** A Store build so VOKARI can be installed with zero
  security warnings once published, no manual unblocking required.
- **Detected-language warning.** VOKARI now warns you when the language it detected in the
  audio doesn't match the language you forced, or when the audio sounds uncertain or
  mixed — so you can catch a wrong language setting before relying on the transcript.
- **Empty-analysis warning.** If the AI returns an analysis with no real content (e.g. a
  model couldn't extract any ideas, decisions, or next steps), VOKARI now tells you
  instead of handing over an empty briefing in silence. The briefing is still produced.
- **Re-export artifacts without re-running the AI.** From a saved session you can
  regenerate the briefing, recap, and Obsidian notes instantly — no re-transcription and
  no new AI call.

### Changed
- **Smarter context handling for local models.** VOKARI now sizes the context window of
  local Ollama models to fit your prompt (up to each model's real maximum) instead of
  silently truncating it. This fixes briefings that came out with full text but empty
  lists of ideas/decisions.
- **Longer, more forgiving timeouts for AI analysis.** The optional question-detection
  step can no longer cost you the briefing: if it times out or fails, VOKARI skips the
  interview, warns you, and still produces the briefing.

### Fixed
- Resolved the most common "it doesn't work on a new PC" failure by adding the onboarding
  flow above (the local AI engine wasn't being set up).
- Numerous smaller flow corrections so the record → transcribe → analyze → briefing path
  is more reliable end to end.

## [0.1.1] - 2026-06-23

First public release.

### Added
- **Packaged Windows build (ZIP).** Bundles an embedded Python runtime, ffmpeg, and the
  built interface, so no developer toolchain is required — download, unblock, extract, run
  the installer.
- **The full v1 flow:** record (microphone, system audio, or both) or import any audio
  file → **on-device transcription** with faster-whisper → **AI analysis** with Claude or
  a local Ollama model.
- **Markdown artifacts:**
  - `briefing.md` — optimized to be fed to another LLM (context, decisions, summary, open
    questions, the raw transcript for ground truth, and a next-steps checklist).
  - A human-readable **recap** with **PDF export** for sharing.
  - **Obsidian notes** — atomic notes for your second brain / vault.
- **Optional interview.** VOKARI auto-detects a few key questions from the transcript;
  answer or skip them, and your replies are merged into the briefing.
- **Live transcription preview** while you record.
- **Sessions library** with persistent storage and full-text search.
- **Privacy-first by design.** Your audio never leaves your device — only the transcribed
  text is sent to the AI, and even that stays local if you choose Ollama. API keys are
  stored in the OS keyring, never in files. No telemetry.

[Unreleased]: https://github.com/salvoclemenza-hub/vokari/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/salvoclemenza-hub/vokari/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/salvoclemenza-hub/vokari/releases/tag/v0.1.1
