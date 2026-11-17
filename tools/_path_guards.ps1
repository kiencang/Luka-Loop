<#
.SYNOPSIS
    Shared path safety and reparse-point guards for Windows PowerShell 5.1 scripts in tools\.
.DESCRIPTION
    Dot-sourced by extract_pdf_assets.ps1, pdf_fallback_tools.ps1, and html_packager.ps1.
    Kept in tools\ so $PSScriptRoot-based workspace root detection resolves identically.
#>

function Test-IsReparsePoint {
    <# Returns True for filesystem links (SymbolicLink/Junction), ignoring OS cloud-sync placeholders (OneDrive/Dropbox/iCloud). #>
    param([System.IO.FileSystemInfo]$Item)
    if ($null -eq $Item) { return $false }
    if (($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0) { return $false }
    return ($Item.LinkType -in @('SymbolicLink', 'Junction'))
}

function Test-HasCloudPlaceholderFiles {
    <# Detects Windows Cloud Filter offline/recall placeholder attributes (Offline | RecallOnOpen | RecallOnDataAccess = 0x441000). #>
    param([string]$DirectoryPath)
    if (-not $DirectoryPath -or -not (Test-Path -LiteralPath $DirectoryPath -PathType Container)) { return $false }
    foreach ($f in (Get-ChildItem -LiteralPath $DirectoryPath -Recurse -Force -File -ErrorAction SilentlyContinue)) {
        if (([int]$f.Attributes -band 0x441000) -ne 0) {
            return $true
        }
    }
    return $false
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
