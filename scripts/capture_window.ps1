# Cattura la finestra reale di un'app desktop (es. VOKARI/pywebview-WebView2) in un PNG,
# usando PrintWindow + PW_RENDERFULLCONTENT (cattura il contenuto Chromium anche se coperto).
# Uso:  powershell -ExecutionPolicy Bypass -File scripts/capture_window.ps1 -Title VOKARI -Out screen/real-app.png
param(
  [string]$Title = "VOKARI",
  [string]$Out = "screen/real-app.png",
  [string[]]$ProcNames = @("python", "pythonw")
)

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinCap {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdcBlt, uint nFlags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
"@

$proc = Get-Process -Name $ProcNames -ErrorAction SilentlyContinue |
  Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*$Title*" } |
  Sort-Object StartTime -Descending |
  Select-Object -First 1   # l'istanza avviata piu di recente (utile per verificare una build nuova)

if (-not $proc) { Write-Output "NOT_FOUND: nessuna finestra '$Title' tra i processi $($ProcNames -join ',')"; exit 1 }

$h = $proc.MainWindowHandle
if ([WinCap]::IsIconic($h)) { [WinCap]::ShowWindow($h, 9) | Out-Null; Start-Sleep -Milliseconds 500 }  # 9 = SW_RESTORE

$r = New-Object WinCap+RECT
[WinCap]::GetWindowRect($h, [ref]$r) | Out-Null
$w = $r.Right - $r.Left
$hgt = $r.Bottom - $r.Top
if ($w -le 0 -or $hgt -le 0) { Write-Output "BAD_RECT ${w}x${hgt}"; exit 1 }

$dir = Split-Path -Parent $Out
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

$bmp = New-Object System.Drawing.Bitmap $w, $hgt
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [WinCap]::PrintWindow($h, $hdc, 2)   # 2 = PW_RENDERFULLCONTENT
$g.ReleaseHdc($hdc)
$g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output "SAVED $Out ${w}x${hgt} (PrintWindow=$ok, pid=$($proc.Id), title='$($proc.MainWindowTitle)')"
