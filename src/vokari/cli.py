"""CLI VOKARI. In M1: `version` e `config show|set`. Cresce nelle milestone successive."""

import time
from datetime import datetime
from pathlib import Path

import typer

from vokari import __version__
from vokari import settings as settings_mod
from vokari.analyze import analyzer as analyzer_mod
from vokari.audio import capture
from vokari.llm.factory import make_provider
from vokari.render import briefing as briefing_mod
from vokari.store.session import Session
from vokari.transcribe import models as models_mod
from vokari.transcribe import whisper as whisper_mod

app = typer.Typer(add_completion=False, help="VOKARI — voce -> conoscenza, 100% locale.")
config_app = typer.Typer(help="Mostra o imposta le impostazioni.")
app.add_typer(config_app, name="config")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Mostra la versione ed esci.",
    ),
) -> None:
    """VOKARI CLI."""


@app.command()
def version() -> None:
    """Mostra la versione."""
    typer.echo(__version__)


@config_app.command("show")
def config_show() -> None:
    """Mostra le impostazioni correnti."""
    s = settings_mod.load()
    for key, val in vars(s).items():
        typer.echo(f"{key} = {val}")
    state = "(impostata)" if settings_mod.get_api_key() else "(non impostata)"
    typer.echo(f"anthropic_api_key = {state}")


@config_app.command("set")
def config_set(key: str, value: str) -> None:
    """Imposta una chiave di config (o l'API key, che va nel keyring)."""
    if key == "anthropic_api_key":
        settings_mod.set_api_key(value)
        typer.echo("anthropic_api_key salvata nel keyring.")
        raise typer.Exit()
    s = settings_mod.load()
    if not hasattr(s, key):
        typer.echo(f"Chiave sconosciuta: {key}", err=True)
        raise typer.Exit(code=1)
    setattr(s, key, value)
    settings_mod.save(s)
    typer.echo(f"{key} = {value}")


@app.command()
def transcribe(
    file: str,
    model: str = typer.Option(None, "--model", "-m", help="Modello Whisper (default: da config)."),
    language: str = typer.Option(None, "--language", "-l", help="Lingua: auto|it|en (default: da config)."),
) -> None:
    """Trascrive un file audio in <file>.transcript.txt (locale)."""
    src = Path(file)
    if not src.exists():
        typer.echo(f"File non trovato: {file}", err=True)
        raise typer.Exit(code=1)
    s = settings_mod.load()
    model = model or s.whisper_model
    language = language or s.transcription_language
    typer.echo(f"Trascrivo {src.name} con {model} ({language})…")
    result = whisper_mod.transcribe(str(src), model=model, language=language)
    out = src.with_suffix(".transcript.txt")
    out.write_text(result["text"], encoding="utf-8")
    typer.echo(f"Trascrizione salvata in: {out}")


models_app = typer.Typer(help="Modelli Whisper locali.")
app.add_typer(models_app, name="models")


@models_app.command("list")
def models_list() -> None:
    """Elenca i modelli Whisper con dimensione e stato."""
    s = settings_mod.load()
    label = {"active": "attivo", "downloaded": "scaricato", "available": "da scaricare"}
    for m in models_mod.CATALOG:
        st = models_mod.state(m.name, s)
        rec = " (consigliato)" if m.recommended else ""
        typer.echo(f"{m.name:<16} {m.size_label:<9} {m.languages:<12} [{label[st]}]{rec}")


@app.command()
def brief(
    file: str,
    mode: str = typer.Option(None, "--mode", help="solo|meeting (default: da config)."),
    model: str = typer.Option(None, "--model", "-m", help="Modello Whisper."),
    language: str = typer.Option(None, "--language", "-l", help="auto|it|en."),
) -> None:
    """Da un audio genera <file>.briefing.md (trascrizione locale + analisi LLM)."""
    src = Path(file)
    if not src.exists():
        typer.echo(f"File non trovato: {file}", err=True)
        raise typer.Exit(code=1)
    s = settings_mod.load()
    mode = mode or s.default_mode
    model = model or s.whisper_model
    language = language or s.transcription_language

    typer.echo(f"[1/3] Trascrizione {src.name} ({model})…")
    result = whisper_mod.transcribe(str(src), model=model, language=language)
    sess = Session.from_transcript_result(result, mode=mode, title=src.stem)

    typer.echo(f"[2/3] Analisi LLM ({'ollama' if s.brain == 'ollama' else s.claude_model})…")
    try:
        provider = make_provider(s)
        analysis = analyzer_mod.analyze(result["text"], mode=mode, provider=provider)
    except Exception as e:
        typer.echo(f"Analisi fallita: {e}", err=True)
        raise typer.Exit(code=1) from e

    typer.echo("[3/3] Genero briefing.md…")
    md = briefing_mod.render_briefing(
        analysis,
        source=src.name,
        transcription_model=model,
        llm_model=("ollama:" + s.ollama_model) if s.brain == "ollama" else s.claude_model,
        session_id=sess.id,
        transcript=result["text"],
    )
    out = src.with_suffix(".briefing.md")
    out.write_text(md, encoding="utf-8")
    typer.echo(f"Briefing salvato in: {out}")


@app.command()
def rec(
    source: str = typer.Option("mic", "--source", "-s", help="Sorgente: mic|system|both."),
    output: str = typer.Option(None, "--output", "-o", help="WAV di output (default: timestamp in cwd)."),
    seconds: float = typer.Option(None, "--seconds", help="Durata fissa in s; se omesso registra fino a Invio."),
    device: str = typer.Option(
        None, "--device", "-d", help="Microfono: indice (vedi --list-devices) o nome. Ignorato per --source system."
    ),
    list_devices: bool = typer.Option(False, "--list-devices", help="Elenca i dispositivi audio ed esci."),
) -> None:
    """Registra audio in un WAV 16 kHz mono pronto per `vokari brief`.

    Senza --seconds, registra fino al primo Invio vuoto. Nel corso della registrazione:
    - Etichetta + Invio: aggiungi un marcatore temporale con label
    - Invio vuoto: interrompi la registrazione
    - Ctrl+C: interrompi e salva immediatamente

    Esempi:
      vokari rec --source both -o meeting.wav
      vokari rec -s system --seconds 60
      vokari rec --list-devices
    """
    if list_devices:
        typer.echo("Microfoni / ingressi:")
        for d in capture.list_input_devices():
            typer.echo(f"  [{d['index']}] {d['name']} ({d['channels']}ch · {d['samplerate']} Hz)")
        typer.echo("Audio di sistema (loopback):")
        try:
            loop = capture.list_loopback_devices()
        except RuntimeError as e:
            typer.echo(f"  non disponibile: {e}")
            loop = []
        for d in loop:
            typer.echo(f"  [{d['index']}] {d['name']} ({d['channels']}ch · {d['samplerate']} Hz)")
        raise typer.Exit()

    if source not in ("mic", "system", "both"):
        typer.echo(f"Sorgente non valida: {source} (usa mic|system|both)", err=True)
        raise typer.Exit(code=1)

    out = Path(output) if output else Path.cwd() / f"vokari-rec-{datetime.now():%Y%m%d-%H%M%S}.wav"
    dev: str | int | None = int(device) if device is not None and device.isdigit() else device
    recorder = capture.Recorder(source, str(out), device=dev)
    recorder.start()
    try:
        if seconds is not None:
            if seconds > 0:
                typer.echo(f"Registrazione ({source}) per {seconds:g}s…")
                time.sleep(seconds)
        else:
            typer.echo(f"Registrazione ({source}). Etichetta+Invio = marcatore · Invio vuoto = stop.")
            while True:
                try:
                    line = input()
                except EOFError:
                    break
                if line.strip() == "":
                    break
                m = recorder.add_marker(line.strip())
                typer.echo(f"  marcatore @ {m['t_ms'] / 1000:.1f}s: {m['label']}")
    except KeyboardInterrupt:
        typer.echo("\nInterrotto, finalizzo…")
    result = recorder.stop()
    typer.echo(f"Registrazione salvata in: {result.wav_path} ({result.duration_s:.1f}s)")
    if result.markers:
        typer.echo(f"Marcatori: {len(result.markers)}")
    typer.echo(f'Genera il briefing con: vokari brief "{result.wav_path}"')
