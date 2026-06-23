# Privacy Policy — VOKARI

_Last updated: 2026-06-23_

VOKARI is a **local-first desktop application**. It has **no backend servers of its own**, performs **no analytics or telemetry**, and its author does **not collect, store, or receive any of your data**. Everything below describes what happens *on your own device* and the few cases where data leaves it **only because you chose an option that requires it**.

## What stays on your device (always)

- **Your audio.** Recordings and imported audio files are processed **entirely on your machine** (conversion with ffmpeg, transcription with [faster-whisper](https://github.com/SYSTRAN/faster-whisper)). **Audio is never uploaded anywhere.**
- **Your artifacts.** The generated `briefing.md`, recap, PDF, and Obsidian notes are written to a local folder **you choose**. They are not sent anywhere.
- **Your sessions and settings.** Stored locally in your user data folder. Not transmitted.

## What leaves your device — only by your choice

- **Transcribed text → the AI provider you select.**
  - If you choose **Claude (Anthropic API)**, the *transcribed text* (not the audio) is sent to Anthropic to produce the analysis, under [Anthropic's privacy policy and terms](https://www.anthropic.com/legal/privacy). You provide your own API key.
  - If you choose **Ollama (local)**, the text is processed by a model running **on your own machine** and **nothing leaves your device**.
- **Your Claude API key** is stored in the **Windows Credential Manager (OS keyring)** — never in a plaintext file, never in the app's settings JSON. It is transmitted only to Anthropic, only to authenticate your own requests.
- **Model downloads.** On first use, transcription models are downloaded **to your machine** from [Hugging Face](https://huggingface.co/); if you use Ollama, its models are downloaded from the Ollama registry. These are downloads *to* you — no personal data is sent.
- **Public version/stars check (optional, cosmetic).** The app may fetch VOKARI's public GitHub star count to display it. This is an anonymous request to GitHub's public API and sends no personal data.

## What we never do

- We do not run servers that receive your data.
- We do not collect analytics, telemetry, or usage statistics.
- We do not sell, share, or monetize any data.
- VOKARI is not directed at children and does not knowingly process children's data.

## Your control

- Choose **Ollama** to keep the entire pipeline 100% offline.
- Delete sessions and artifacts at any time from within the app or your file system.
- Remove your API key from the OS keyring at any time (Windows *Credential Manager*).

## Contact

VOKARI is open source ([MIT](LICENSE)). Questions or concerns: open an issue at
<https://github.com/salvoclemenza-hub/vokari/issues>.

---

> ℹ️ This policy reflects the application's actual behavior. When you select the Claude provider, your use of the Anthropic API is additionally governed by Anthropic's own terms.
