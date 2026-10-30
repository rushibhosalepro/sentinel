# Draft voiceover: one WAV per scene from narration.json (Windows SAPI).
# Replace any public/voice/<id>.wav with your own recording, then run
# `uv run python video/scripts/voice_timing.py` and re-render.
#
#   powershell -ExecutionPolicy Bypass -File video/scripts/make_voice.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$outDir = Join-Path $root "public\voice"
New-Item -ItemType Directory -Force $outDir | Out-Null

Add-Type -AssemblyName System.Speech
$lines = Get-Content (Join-Path $root "narration.json") -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($line in $lines) {
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $synth.SelectVoice("Microsoft Zira Desktop")
    $synth.Rate = 1
    $path = Join-Path $outDir ($line.id + ".wav")
    $synth.SetOutputToWaveFile($path)
    $synth.Speak($line.text)
    $synth.Dispose()
    Write-Output "wrote $path"
}
