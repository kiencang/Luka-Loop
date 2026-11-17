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
    [ValidateRange(36, 1200)]
    [int]$Dpi = 180,
    [switch]$Meta,
    [int]$MaxMetaBytes = 16384,
    [int]$MaxMetaWords = 20
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Test-IsReparsePoint {
    param([System.IO.FileSystemInfo]$Item)
    return ($null -ne $Item) -and (($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)
}

function Assert-SafeOutputPath {
    <# Blocks symlinks/junctions (ReparsePoint) on output directory/file and workspace/temp ancestors. #>
    param(
        [string]$TargetPath,
        [string]$Label = 'OutputPath',
        [switch]$IsDirectory
    )
    if (-not $TargetPath -or -not $TargetPath.Trim()) { return }

    [System.Management.Automation.ProviderInfo]$provider = $null
    [System.Management.Automation.PSDriveInfo]$drive = $null
    $resolved = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($TargetPath, [ref]$provider, [ref]$drive)
    if ($null -eq $provider -or $provider.Name -ne 'FileSystem') {
        throw "Refusing non-filesystem path for ${Label}: $TargetPath"
    }
    $normTarget = [System.IO.Path]::GetFullPath($resolved).TrimEnd('\', '/')

    $anchors = New-Object 'System.Collections.Generic.List[string]'
    $anchorCandidates = @((Split-Path $PSScriptRoot -Parent))
    $loc = Get-Location
    if ($loc.Provider.Name -eq 'FileSystem') { $anchorCandidates += $loc.ProviderPath }
    if ($env:TEMP -and $env:TEMP.Trim()) { $anchorCandidates += $env:TEMP }
    foreach ($ac in $anchorCandidates) {
        if (-not $ac) { continue }
        $na = [System.IO.Path]::GetFullPath($ac).TrimEnd('\', '/')
        if ($na -and ($anchors -notcontains $na)) { [void]$anchors.Add($na) }
    }

    $matchedAnchor = $null
    foreach ($a in $anchors) {
        if ($normTarget.StartsWith($a + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
            if (-not $matchedAnchor -or $a.Length -gt $matchedAnchor.Length) {
                $matchedAnchor = $a
            }
        }
    }

    if ($matchedAnchor) {
        $rel = $normTarget.Substring($matchedAnchor.Length).TrimStart('\', '/')
        $probe = $matchedAnchor
        foreach ($seg in ($rel -split '[\\/]+')) {
            if (-not $seg) { continue }
            $probe = Join-Path $probe $seg
            $item = Get-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
            if ($item -and (Test-IsReparsePoint -Item $item)) {
                throw "Refusing to write through symlink/junction (ReparsePoint) for ${Label}: $probe"
            }
        }
    } else {
        $cursor = $normTarget
        $driveRoot = [System.IO.Path]::GetPathRoot($normTarget).TrimEnd('\', '/')
        while ($cursor -and -not $cursor.Equals($driveRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            $item = Get-Item -LiteralPath $cursor -Force -ErrorAction SilentlyContinue
            if ($item) {
                if (Test-IsReparsePoint -Item $item) {
                    throw "Refusing to write through symlink/junction (ReparsePoint) for ${Label}: $cursor"
                }
                break
            }
            $parent = Split-Path $cursor -Parent
            if (-not $parent -or $parent -eq $cursor) { break }
            $cursor = $parent.TrimEnd('\', '/')
        }
    }

    $leaf = Get-Item -LiteralPath $normTarget -Force -ErrorAction SilentlyContinue
    if ($leaf) {
        if (Test-IsReparsePoint -Item $leaf) {
            throw "Refusing to overwrite symlink/junction (ReparsePoint) for ${Label}: $normTarget"
        }
        if ($IsDirectory -and -not $leaf.PSIsContainer) {
            throw "Expected directory path for ${Label}, found file: $normTarget"
        }
        if (-not $IsDirectory -and $leaf.PSIsContainer) {
            throw "Expected file path for ${Label}, found directory: $normTarget"
        }
    }
}

function Assert-LocalNoUncPath {
    param([string]$PathValue, [string]$ParamName = 'Path')
    if (-not $PathValue) { return }
    $t = $PathValue.Trim()
    if ($t -match '^(?i)file://[^/]' -or
        $t -match '^(?i)(?:Microsoft\.PowerShell\.Core\\)?FileSystem::(?:\\\\|//)' -or
        $t -match '^(?:\\\\|//)') {
        throw "Refusing UNC/network path for ${ParamName}: $PathValue"
    }
    if ([System.IO.Path]::IsPathRooted($t)) {
        try {
            $u = [System.Uri]$t
            if ($u.IsUnc) {
                throw "Refusing UNC/network path for ${ParamName}: $PathValue"
            }
        } catch [System.UriFormatException] {}
    }
}

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
            Assert-LocalNoUncPath -PathValue $uri -ParamName 'TranscriptMediaUri'
            if ($uri -match '^file:///') {
                $uri = ([System.Uri]$uri).LocalPath
                Assert-LocalNoUncPath -PathValue $uri -ParamName 'TranscriptMediaUri'
            }
            return $uri
        }
    }
    return $null
}

function Find-LatestPdfInTranscript {
    param([string]$PathToTranscript)
    Assert-LocalNoUncPath -PathValue $PathToTranscript -ParamName '-TranscriptPath'
    if (-not (Test-Path -LiteralPath $PathToTranscript -PathType Leaf)) {
        throw "Transcript file not found: $PathToTranscript"
    }
    $absTranscript = (Resolve-Path -LiteralPath $PathToTranscript).Path
    Assert-LocalNoUncPath -PathValue $absTranscript -ParamName '-TranscriptPath'

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

Assert-LocalNoUncPath -PathValue $PdfPath -ParamName '-PdfPath'
Assert-LocalNoUncPath -PathValue $TranscriptPath -ParamName '-TranscriptPath'
Assert-LocalNoUncPath -PathValue $OutDir -ParamName '-OutDir'

$targetPdf = $PdfPath
if (-not $targetPdf) {
    if (-not $TranscriptPath) {
        throw "Either -PdfPath or -TranscriptPath must be provided."
    }
    $targetPdf = Find-LatestPdfInTranscript -PathToTranscript $TranscriptPath
}

Assert-LocalNoUncPath -PathValue $targetPdf -ParamName 'ResolvedPdf'
if (-not (Test-Path -LiteralPath $targetPdf -PathType Leaf)) {
    throw "Resolved PDF file does not exist: $targetPdf"
}
$absPdf = (Resolve-Path -LiteralPath $targetPdf).Path
Assert-LocalNoUncPath -PathValue $absPdf -ParamName 'ResolvedPdf'
Write-Output ("Resolved PDF -> {0}" -f $absPdf)

if (-not $OutDir -or -not $OutDir.Trim()) {
    throw "-OutDir cannot be empty."
}
$outDirFull = [System.IO.Path]::GetFullPath($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutDir)).TrimEnd('\', '/')
Assert-SafeOutputPath -TargetPath $outDirFull -Label '-OutDir' -IsDirectory
if (Test-Path -LiteralPath $outDirFull -PathType Container) {
    foreach ($entry in (New-Object System.IO.DirectoryInfo($outDirFull)).GetFileSystemInfos()) {
        if (Test-IsReparsePoint -Item $entry) {
            throw "Refusing to write into OutDir containing symlink/junction: $($entry.FullName)"
        }
    }
}

$exePath = Join-Path $PSScriptRoot 'extract_assets\extract_assets.exe'
if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
    throw "Extractor executable not found: $exePath"
}

# Avoid Python argparse misinterpreting an OutDir starting with '-' as an option flag
$cliOutDir = if ($OutDir.TrimStart().StartsWith('-')) { $outDirFull } else { $OutDir }
$exeArgs = @($absPdf, '--out-dir', $cliOutDir, '--dpi', [string]$Dpi)
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
