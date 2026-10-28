param([string]$Url = 'http://127.0.0.1:8080')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$sample = [System.IO.Path]::GetTempFileName()
try {
    $voice = $synth.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'ru-RU' } | Select-Object -First 1
    if (-not $voice) { throw 'Russian Windows speech voice is unavailable' }
    $synth.SelectVoice($voice.VoiceInfo.Name)
    $format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
    $synth.SetOutputToWaveFile($sample, $format)
    $synth.Speak('Хочу поехать в Казань из Москвы на семь дней.')
    $synth.SetOutputToNull()
    $response = Invoke-WebRequest -UseBasicParsing -Uri ($Url.TrimEnd('/') + '/api/voice/transcribe') -Method Post -ContentType 'audio/wav' -Body ([System.IO.File]::ReadAllBytes($sample)) -TimeoutSec 45
    $reader = New-Object System.IO.StreamReader($response.RawContentStream, [System.Text.Encoding]::UTF8)
    try { $result = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
    $ok = $result.backend -eq 'gigaam' -and $result.text -match 'Казань' -and $result.text -match 'Москвы' -and $result.text -match '(семь|7)\s+дней'
    @{ status = $(if ($ok) { 'PASS' } else { 'FAIL' }); backend = $result.backend; input = 'Windows Russian TTS'; real_microphone = $false; expected_travel_details = $ok } | ConvertTo-Json -Compress
    if (-not $ok) { exit 1 }
} finally {
    $synth.Dispose()
    Remove-Item -LiteralPath $sample -ErrorAction SilentlyContinue
}
