' ============================================================================
' VOKARI - Launcher silenzioso (uso quotidiano dell'utente)
' ----------------------------------------------------------------------------
' Perche' esiste: l'esperienza nativa (come Chrome / WhatsApp) vuole SOLO la
' finestra dell'app, mai un terminale. Un .bat apre sempre una console cmd, e
' "Avvia VOKARI.bat" usa python.exe (che ha la console) + termina con pause.
' Questo .vbs invece:
'   - usa pythonw.exe (Python SENZA console)
'   - lo avvia con finestra nascosta (parametro 0 di WScript.Shell.Run)
' => doppio click sul .vbs = parte solo la finestra dell'app, zero terminale.
'
' Nota: questo launcher NON ricostruisce la UI (niente pnpm build): per l'utente
' finale la cartella frontend\dist e' gia' pronta. Il rebuild + i log di errore
' restano in "Avvia VOKARI.bat", che e' il launcher di SVILUPPO.
' ============================================================================

Option Explicit

Dim fso, shell, scriptDir, pythonw, cmd

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' Cartella di questo script = root del progetto (funziona da qualunque CWD).
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Python senza console del .venv.
pythonw = fso.BuildPath(scriptDir, ".venv\Scripts\pythonw.exe")

If Not fso.FileExists(pythonw) Then
    MsgBox "Ambiente Python non trovato:" & vbCrLf & vbCrLf & _
           pythonw & vbCrLf & vbCrLf & _
           "Esegui prima nel progetto:  uv sync", _
           vbCritical, "VOKARI"
    WScript.Quit 1
End If

' Comando: pythonw.exe -m app.main   (path con eventuali spazi tra virgolette).
' In VBScript le virgolette dentro una stringa si raddoppiano ("").
cmd = """" & pythonw & """ -m app.main"

' CWD = root del progetto (cosi' app.main risolve frontend\dist e gli asset).
shell.CurrentDirectory = scriptDir

' Run(comando, stileFinestra, attendi):
'   0     = finestra nascosta (nessun terminale visibile)
'   False = non aspettare la fine del processo (lo script .vbs termina subito)
shell.Run cmd, 0, False
