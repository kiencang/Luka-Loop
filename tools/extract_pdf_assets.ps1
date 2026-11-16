<#
.SYNOPSIS
    Step 1 PDF Asset Extraction Wrapper (Supports Direct -PdfPath or Drag-and-Drop -TranscriptPath).
.DESCRIPTION
    Resolves the PDF file path (either directly via -PdfPath or by locating the most recent PDF attachment
    in transcript.jsonl via -TranscriptPath), prints the resolved PDF path, invokes extract_assets.exe,
    and prints manifest.json to stdout when -Meta is set and its size is within -MaxMetaBytes.
#>
param(
    [string]$PdfPath = '',
    [string]$TranscriptPath = '',
    [string]$OutDir = 'work\assets',
    [int]$Dpi = 180,
    [switch]$Meta,
    [int]$MaxMetaBytes = 16384,
    [int]$MaxMetaWords = 20
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Resolve-PdfFromLine {
    param([string]$Line)
    if ($Line -notmatch '"type"\s*:\s*"USER_INPUT"' -or $Line -notmatch '\.pdf') {
        return $null
    }
    try {
        $entry = $Line | ConvertFrom-Json
    } catch {
        return $null
    }
    if ($entry.type -ne 'USER_INPUT' -or -not $entry.media) {
        return $null
    }
    foreach ($m in @($entry.media)) {
        $uri = [string]$m.uri
        if ($uri -and ($m.mime_type -eq 'application/pdf' -or $uri -match '(?i)\.pdf$')) {
            if ($uri -match '^file:///') {
                $uri = ([System.Uri]$uri).LocalPath
            }
            return $uri
        }
    }
    return $null
}

function Find-LatestPdfInTranscript {
    param([string]$PathToTranscript)
    if (-not (Test-Path -LiteralPath $PathToTranscript -PathType Leaf)) {
        throw "Transcript file not found: $PathToTranscript"
    }
    $absTranscript = (Resolve-Path -LiteralPath $PathToTranscript).Path

    # Fast path: scan last 50 lines first to avoid reading huge history files
    $tailLines = @(Get-Content -LiteralPath $absTranscript -Tail 50 -Encoding UTF8)
    for ($i = $tailLines.Count - 1; $i -ge 0; $i--) {
        $found = Resolve-PdfFromLine -Line $tailLines[$i]
        if ($found) { return $found }
    }

    # Fallback: scan earlier lines in reverse if PDF was sent earlier in the conversation
    $allLines = [System.IO.File]::ReadAllLines($absTranscript, [System.Text.Encoding]::UTF8)
    for ($i = $allLines.Length - 1; $i -ge 0; $i--) {
        $found = Resolve-PdfFromLine -Line $allLines[$i]
        if ($found) { return $found }
    }

    throw "No PDF attachment found in USER_INPUT entries of transcript: $absTranscript"
}

$targetPdf = $PdfPath
if (-not $targetPdf) {
    if (-not $TranscriptPath) {
        throw "Either -PdfPath or -TranscriptPath must be provided."
    }
    $targetPdf = Find-LatestPdfInTranscript -PathToTranscript $TranscriptPath
}

if (-not (Test-Path -LiteralPath $targetPdf -PathType Leaf)) {
    throw "Resolved PDF file does not exist: $targetPdf"
}
$absPdf = (Resolve-Path -LiteralPath $targetPdf).Path
Write-Output ("Resolved PDF -> {0}" -f $absPdf)

$exePath = Join-Path $PSScriptRoot 'extract_assets\extract_assets.exe'
if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
    throw "Extractor executable not found: $exePath"
}

$exeArgs = @($absPdf, '--out-dir', $OutDir, '--dpi', [string]$Dpi)
if ($Meta) {
    $exeArgs += '--meta'
}

& $exePath @exeArgs
if ($LASTEXITCODE -ne 0) {
    throw "extract_assets.exe failed with exit code $LASTEXITCODE"
}

function Limit-ManifestWords {
    param(
        [string]$Text,
        [int]$MaxWords = 20
    )
    if ($null -eq $Text) { return '' }
    $normalized = ($Text -replace '[\x00-\x1F]+', ' ').Trim()
    if (-not $normalized -or $MaxWords -le 0) {
        return $normalized
    }
    $words = @($normalized -split '\s+' | Where-Object { $_ -ne '' })
    if ($words.Count -le $MaxWords) {
        return ($words -join ' ')
    }
    return (($words[0..($MaxWords - 1)] -join ' ') + '...')
}

function Get-CompactedManifestText {
    param(
        [string]$ManifestPath,
        [int]$MaxWords = 20
    )
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        return ''
    }
    $rawJson = [System.IO.File]::ReadAllText($ManifestPath, [System.Text.Encoding]::UTF8)
    if ($MaxWords -le 0) {
        return $rawJson.TrimEnd()
    }
    $updatedJson = [regex]::Replace($rawJson, '("(?<key>caption|context)"\s*:\s*)(?<val>"(?:\\.|[^"\\])*")', {
        param($m)
        $decoded = [string]($m.Groups['val'].Value | ConvertFrom-Json)
        $short = Limit-ManifestWords -Text $decoded -MaxWords $MaxWords
        $jsonStr = ConvertTo-Json -InputObject ([string]$short) -Compress
        return ($m.Groups[1].Value + $jsonStr)
    })
    return $updatedJson.TrimEnd()
}

if ($Meta) {
    $manifestPath = Join-Path $OutDir 'manifest.json'
    if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
        $absManifest = (Resolve-Path -LiteralPath $manifestPath).Path
        $stdoutJson = Get-CompactedManifestText -ManifestPath $absManifest -MaxWords $MaxMetaWords
        $stdoutBytes = [System.Text.Encoding]::UTF8.GetByteCount($stdoutJson)
        if ($stdoutBytes -le $MaxMetaBytes) {
            Write-Output '=== MANIFEST JSON START ==='
            Write-Output $stdoutJson
            Write-Output '=== MANIFEST JSON END ==='
        } else {
            Write-Output ("Manifest too large for stdout ({0:N0} bytes > {1:N0} limit); use read_file -> {2}" -f $stdoutBytes, $MaxMetaBytes, $absManifest)
        }
    }
}
