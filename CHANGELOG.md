# Changelog

User-facing changelog for **VOKARI** — the local-first app that turns a voice
recording into structured Markdown (transcription, AI analysis, and second-brain notes),
all on your own machine. Items here describe what changed for *you*, not the code.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-10-01

Speaker attribution, subtitles, and a vocabulary that finally counts.

### Added
- **Speaker attribution (optional).** The transcript becomes a dialogue, with the speaker's
  name next to each line — in the transcript and in the subtitles. It runs locally on your
  CPU and adds roughly one minute for every three minutes of recording. Telling VOKARI how
  many people are speaking improves the result a lot; left on "I don't know", one person
  sometimes gets split in two. Voice models (~35 MB) download on demand, only if you enable
  the feature. On audio that mixes microphone and system sound into a single channel the
  quality degrades — the app says so.
- **`.srt` subtitle export** from the artifacts, with the timing of every line and the
  speaker's name when attribution is on. Sessions recorded before this version have no
  stored timings, and the export says so instead of writing an empty file.
- **A warning when the briefing drifts from the recording.** If names or figures appear that
  cannot be heard in the audio, VOKARI tells you. Nothing is deleted — silently removing a
  correct item would be worse than showing the doubt.

### Changed
- **Your vocabulary now applies to the whole recording.** The terms you type in "Your
  context" used to reach only the first ~30 seconds, and changing them returned the old
  cached transcript anyway. Both are fixed; existing caches stay valid.
- **Long recordings are split at quiet moments** instead of at a fixed time, so fewer
  sentences get cut in half — and fewer words get invented where the cut used to land in
  the middle of one.
- **Briefings and recaps state that they were generated with AI**, in the metadata and in
  a line a person can read.

### Fixed
- **Drawing the conclusions no longer drops numbers.** Dates, quantities and amounts found
  in the first pass come back into the briefing even when the summary left them out.
- **"Cancel" really stops the briefing regeneration** instead of discarding the result while
  the model keeps working for minutes.
- On long recordings the final check no longer re-sends the whole transcript in one call —
  the very thing that reading it in passes was meant to avoid.

## [0.2.2] - 2026-09-24

Long recordings stop losing their second half. *(Built but never shipped publicly — its
changes reach you with 0.3.0.)*

### Added
- **The full transcript can be downloaded** from the artifacts, not just copied.
- **A dedicated model to draw the conclusions.** With a local brain you can pick a more
  capable model (e.g. `granite4.2:8b`) just for the final merge, keeping the fast one for
  everything else. It is more precise and noticeably slower — and it compresses: the raw
  merge stays the most faithful, only messier.
- **A warning when the analysis extracts little** for the length of the recording.

### Changed
- **Long recordings are analyzed in passes** instead of all at once. On a real 10-minute
  recording the extracted items went from 7 to 21, recovering dates, commitments and topics
  that used to disappear. The problem was never the context window — it was attention.

### Fixed
- Models that "think out loud" (granite, qwen3, deepseek-r1) no longer stall the analysis.
- Obsidian notes keep their properties when the title contains quotes.
- Pronouns, common nouns and never-spoken names no longer show up among the mentioned entities.
- The version shown in the app is the one actually installed.

## [0.2.1] - 2026-07-01

Cross-platform release — VOKARI now runs on **macOS** (Apple Silicon) and **Linux**, in
addition to Windows.

### Added
- **macOS support (Apple Silicon).** A native macOS build, shipped as an unsigned `.dmg` —
  record, transcribe, and generate briefings entirely on your Mac. Recording is
  microphone-only for now (system-audio capture stays Windows-only).
- **Linux support.** VOKARI runs on Linux from source, with microphone-only recording.
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
- **The app adapts to your platform.** On macOS and Linux the source picker shows the
  microphone only, and the Windows-only "CPU temperature" panel is hidden — no dead
  controls for features a platform doesn't have.
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

[Unreleased]: https://github.com/salvoclemenza-hub/vokari/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/salvoclemenza-hub/vokari/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/salvoclemenza-hub/vokari/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/salvoclemenza-hub/vokari/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/salvoclemenza-hub/vokari/releases/tag/v0.1.1
