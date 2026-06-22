// Notifica di completamento per il flusso lungo (trascrizione 5-15 min): se la finestra
// è in background l'utente non ha altro richiamo. WebView2 (Edge Chromium) supporta le
// Notification HTML5 e WebAudio: nessun codice Python necessario (A1).
let audioCtx: AudioContext | null = null;

/** Richiede una sola volta il permesso notifiche. Da chiamare quando parte un'operazione lunga. */
export function initNotifications(): void {
  try {
    if ("Notification" in window && Notification.permission === "default") {
      void Notification.requestPermission();
    }
  } catch {
    /* ambienti senza Notification (test/browser) */
  }
}

function notifyOS(title: string, body: string): void {
  try {
    if ("Notification" in window && Notification.permission === "granted") {
      new Notification(title, { body });
    }
  } catch {
    /* ignora */
  }
}

function beep(): void {
  try {
    const Ctx = window.AudioContext;
    if (!Ctx) return;
    audioCtx ??= new Ctx();
    void audioCtx.resume();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = "sine";
    osc.frequency.value = 660;
    gain.gain.value = 0.05;
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + 0.15);
  } catch {
    /* WebAudio non disponibile */
  }
}

/** Richiamo a fine elaborazione SOLO se la finestra è in background (l'utente che guarda
 *  vede già la transizione di schermata): notifica OS + breve beep. */
export function notifyComplete(title: string, body: string): void {
  if (!document.hidden) return;
  notifyOS(title, body);
  beep();
}
