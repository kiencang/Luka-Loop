<#
.SYNOPSIS
    PowerShell 5.1 & 7+ PDF Fallback Renderer & Auto-Trim Image Cropper (delegates imaging to extract_assets.exe / PyMuPDF).
.DESCRIPTION
    Uses bundled extract_assets.exe (PyMuPDF) for scanned PDFs or manual figure cropping (zero System.Drawing / WinRT):
      -Action RenderPages  : Render PDF pages to high-DPI PNGs (page_1.png, page_2.png, ...)
      -Action CropFromJson : Crop figure regions specified as normalized [x0,y0,x1,y1] boxes in JSON, with optional white-border auto-trim
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('RenderPages', 'CropFromJson')]
    [string]$Action,

    [string]$PdfPath = '',
    [string]$OutDir = '.',
    [ValidateRange(0.5, 10.0)]
    [double]$Scale = 2.5,
    [string]$Pages = '',
    [string]$SpecJson = ''
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$pathGuardsScript = Join-Path $PSScriptRoot '_path_guards.ps1'
$pathGuardsItem = Get-Item -LiteralPath $pathGuardsScript -Force -ErrorAction SilentlyContinue
if (-not $pathGuardsItem -or $pathGuardsItem.PSIsContainer) {
    throw "Required helper script not found: $pathGuardsScript"
}
if ((($pathGuardsItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) -and ($pathGuardsItem.LinkType -in @('SymbolicLink', 'Junction'))) {
    throw "Refusing to dot-source symlink/junction: $pathGuardsScript"
}
. $pathGuardsScript

function Invoke-RenderPages {
    param([string]$Pdf, [string]$DestDir, [double]$RenderScale, [string]$PageFilter = '')
    if ($RenderScale -lt 0.5 -or $RenderScale -gt 10.0) {
        throw "RenderScale out of safe range (0.5..10.0): $RenderScale"
    }
    Assert-LocalNoUncPath -PathValue $Pdf -ParamName '-PdfPath'
    if (-not $Pdf -or -not (Test-Path -LiteralPath $Pdf -PathType Leaf)) { throw "PDF not found: $Pdf" }
    $absPdf = (Resolve-Path -LiteralPath $Pdf).Path
    Assert-LocalNoUncPath -PathValue $absPdf -ParamName '-PdfPath'
    $absDest = Resolve-SafeOutDirectory -OutDir $DestDir -ParamName '-OutDir' -Create

    $scaleStr = $RenderScale.ToString([System.Globalization.CultureInfo]::InvariantCulture)
    $exeArgs = @('--mode', 'render-pages', $absPdf, '--out-dir', $absDest, '--scale', $scaleStr)
    if ($PageFilter -and $PageFilter.Trim()) {
        $exeArgs += @('--pages', $PageFilter)
    }
    Invoke-ExtractAssetsExe -Arguments $exeArgs
}

function Get-AllowedCropInputRoots {
    <# Returns canonical workspace/input roots allowed for source page_png images. #>
    param(
        [string]$JsonDir,
        [string]$DestDir
    )
    $roots = New-Object 'System.Collections.Generic.List[string]'
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)

    $blocked = @(
        $env:USERPROFILE,
        $env:PUBLIC,
        $env:WINDIR,
        $env:SystemRoot,
        $env:ProgramFiles,
        ${env:ProgramFiles(x86)}
    ) | Where-Object { $_ } | ForEach-Object { [System.IO.Path]::GetFullPath($_).TrimEnd('\', '/') }

    $repoRoot = Split-Path $PSScriptRoot -Parent
    $candidates = @($repoRoot, $JsonDir, $DestDir)
    $loc = Get-Location
    if ($loc.Provider.Name -eq 'FileSystem') {
        $candidates += $loc.ProviderPath
    }

    foreach ($c in $candidates) {
        if (-not $c) { continue }
        $norm = [System.IO.Path]::GetFullPath($c).TrimEnd('\', '/')
        $driveRoot = [System.IO.Path]::GetPathRoot($norm).TrimEnd('\', '/')
        if (-not $norm -or $norm.Equals($driveRoot, [System.StringComparison]::OrdinalIgnoreCase)) { continue }
        if ($blocked -contains $norm) { continue }
        if ($seen.Add($norm)) { [void]$roots.Add($norm) }
    }
    return @($roots)
}

function Resolve-SafeCropInputFile {
    <# Validates page_png stays inside allowed workspace/input roots and traverses no symlinks/junctions. #>
    param(
        [string]$RawPagePath,
        [string[]]$AllowedRoots
    )
    if (-not $RawPagePath -or -not $RawPagePath.Trim()) {
        throw "Missing page_png in crop spec."
    }
    $trimmed = $RawPagePath.Trim()
    Assert-LocalNoUncPath -PathValue $trimmed -ParamName 'page_png'

    [System.Management.Automation.ProviderInfo]$provider = $null
    [System.Management.Automation.PSDriveInfo]$drive = $null
    $resolved = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($trimmed, [ref]$provider, [ref]$drive)
    if ($null -eq $provider -or $provider.Name -ne 'FileSystem') {
        throw "Refusing non-filesystem page_png path: $RawPagePath"
    }
    $absSrc = [System.IO.Path]::GetFullPath($resolved).TrimEnd('\', '/')

    $matchedRoot = $null
    foreach ($r in $AllowedRoots) {
        if ($absSrc.StartsWith($r + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
            $matchedRoot = $r
            break
        }
    }
    if (-not $matchedRoot) {
        throw "Path traversal blocked: page_png '$RawPagePath' resolves outside allowed directories ($absSrc)"
    }

    $rootItem = Get-Item -LiteralPath $matchedRoot -Force -ErrorAction SilentlyContinue
    if ($rootItem -and (Test-IsReparsePoint -Item $rootItem)) {
        throw "Blocked reparse point (symlink/junction) at input root: $matchedRoot"
    }

    $rel = $absSrc.Substring($matchedRoot.Length).TrimStart('\', '/')
    $probe = $matchedRoot
    foreach ($seg in ($rel -split '[\\/]+')) {
        if (-not $seg) { continue }
        $probe = Join-Path $probe $seg
        $item = Get-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
        if (-not $item) {
            throw "Source page PNG not found: $RawPagePath"
        }
        if (Test-IsReparsePoint -Item $item) {
            throw "Blocked reparse point (symlink/junction) in page_png path: $probe"
        }
    }

    $leaf = Get-Item -LiteralPath $absSrc -Force -ErrorAction SilentlyContinue
    if (-not $leaf -or $leaf.PSIsContainer) {
        throw "Source page PNG not found: $RawPagePath"
    }
    return $absSrc
}

function Resolve-SafeCropOutFile {
    <# Enforces out_name is a bare filename directly inside $DestDir and refuses symlink overwrite. #>
    param(
        [string]$DestDir,
        [string]$OutName
    )
    if (-not $OutName -or -not $OutName.Trim()) {
        throw "Missing out_name in crop spec."
    }
    $name = $OutName.Trim()
    if ($name -eq '.' -or $name -eq '..' -or
        [System.IO.Path]::IsPathRooted($name) -or
        $name.IndexOfAny([System.IO.Path]::GetInvalidFileNameChars()) -ge 0 -or
        ([System.IO.Path]::GetFileName($name) -ne $name)) {
        throw "Path traversal blocked: invalid out_name '$OutName' (must be a plain filename inside OutDir)"
    }

    $normDest = [System.IO.Path]::GetFullPath($DestDir).TrimEnd('\', '/')
    $destItem = Get-Item -LiteralPath $normDest -Force -ErrorAction Stop
    if (Test-IsReparsePoint -Item $destItem) {
        throw "Blocked reparse point (symlink/junction) at OutDir: $normDest"
    }

    $outFile = [System.IO.Path]::GetFullPath((Join-Path $normDest $name))
    if (-not $outFile.StartsWith($normDest + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path traversal blocked: '$OutName' resolves outside '$normDest'"
    }

    $existingOut = Get-Item -LiteralPath $outFile -Force -ErrorAction SilentlyContinue
    if ($existingOut) {
        if (Test-IsReparsePoint -Item $existingOut) {
            throw "Refusing to overwrite symlink/reparse point: $outFile"
        }
        if ($existingOut.PSIsContainer) {
            throw "Refusing to overwrite directory with image file: $outFile"
        }
    }
    return $outFile
}

function Resolve-CropBoxCoords {
    <# Validates normalized [x0, y0, x1, y1] box coordinates in [0.0, 1.0] with x1 > x0 and y1 > y0. #>
    param(
        $Box,
        [string]$OutName
    )
    if ($null -eq $Box) {
        throw "Invalid crop box for '$OutName': missing 'box' array."
    }
    $items = @($Box)
    if ($items.Count -ne 4) {
        throw "Invalid crop box for '$OutName': expected 4 numeric elements [x0, y0, x1, y1], got $($items.Count)."
    }
    $vals = New-Object double[] 4
    $inv = [System.Globalization.CultureInfo]::InvariantCulture
    $style = [System.Globalization.NumberStyles]::Float
    for ($i = 0; $i -lt 4; $i++) {
        $raw = $items[$i]
        if ($null -eq $raw -or $raw -is [bool] -or $raw -is [System.Array] -or $raw -is [System.Collections.IDictionary] -or $raw -is [pscustomobject]) {
            throw "Invalid crop box coordinate at index $i for '$OutName'."
        }
        $str = [Convert]::ToString($raw, $inv)
        [double]$parsed = 0.0
        if (-not [double]::TryParse($str, $style, $inv, [ref]$parsed) -or [double]::IsNaN($parsed) -or [double]::IsInfinity($parsed)) {
            throw "Invalid non-numeric crop box coordinate '$raw' at index $i for '$OutName'."
        }
        if ($parsed -lt 0.0 -or $parsed -gt 1.0) {
            throw "Crop box coordinate $parsed at index $i out of normalized range [0.0, 1.0] for '$OutName'."
        }
        $vals[$i] = $parsed
    }
    if ($vals[2] -le $vals[0] -or $vals[3] -le $vals[1]) {
        throw "Invalid crop box [$($vals -join ',')] for '$OutName': require x1 > x0 and y1 > y0."
    }
    return $vals
}

function Invoke-CropFromJson {
    param([string]$JsonFile, [string]$DestDir)
    Assert-LocalNoUncPath -PathValue $JsonFile -ParamName '-SpecJson'
    if (-not $JsonFile -or -not (Test-Path -LiteralPath $JsonFile -PathType Leaf)) { throw "Spec JSON not found: $JsonFile" }
    $absDest = Resolve-SafeOutDirectory -OutDir $DestDir -ParamName '-OutDir' -Create
    $absJson = (Resolve-Path -LiteralPath $JsonFile).Path
    Assert-LocalNoUncPath -PathValue $absJson -ParamName '-SpecJson'
    $absJsonDir = Split-Path $absJson -Parent
    $allowedInputRoots = Get-AllowedCropInputRoots -JsonDir $absJsonDir -DestDir $absDest
    $spec = Get-Content -LiteralPath $absJson -Raw -Encoding UTF8 | ConvertFrom-Json

    $resolvedItems = New-Object 'System.Collections.Generic.List[object]'
    foreach ($item in @($spec)) {
        $srcPng = Resolve-SafeCropInputFile -RawPagePath ([string]$item.page_png) -AllowedRoots $allowedInputRoots
        $null = Resolve-SafeCropOutFile -DestDir $absDest -OutName ([string]$item.out_name)
        $box = Resolve-CropBoxCoords -Box $item.box -OutName ([string]$item.out_name)
        [void]$resolvedItems.Add(@{
            src_path  = $srcPng
            out_name  = ([string]$item.out_name).Trim()
            box       = @($box[0], $box[1], $box[2], $box[3])
            auto_trim = ($item.auto_trim -ne $false)
        })
    }

    if ($resolvedItems.Count -eq 0) {
        return
    }

    $tempBase = if ($env:TEMP -and $env:TEMP.Trim()) { $env:TEMP } else { [System.IO.Path]::GetTempPath() }
    $tmpDir = Join-Path $tempBase ("luka_crop_" + [Guid]::NewGuid().ToString("N"))
    Assert-SafeOutputPath -TargetPath $tmpDir -Label 'TempCropDir' -IsDirectory
    [void][System.IO.Directory]::CreateDirectory($tmpDir)
    try {
        $resolvedSpecPath = Join-Path $tmpDir 'crop_resolved.json'
        $payloadJson = ConvertTo-Json -InputObject ([pscustomobject]@{ items = $resolvedItems.ToArray() }) -Depth 6 -Compress
        [System.IO.File]::WriteAllText($resolvedSpecPath, $payloadJson, (New-Object System.Text.UTF8Encoding($false)))
        Invoke-ExtractAssetsExe -Arguments @('--mode', 'crop-json', '--spec', $resolvedSpecPath, '--out-dir', $absDest)
    } finally {
        Remove-Item -LiteralPath $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

switch ($Action) {
    'RenderPages'  { Invoke-RenderPages -Pdf $PdfPath -DestDir $OutDir -RenderScale $Scale -PageFilter $Pages }
    'CropFromJson' { Invoke-CropFromJson -JsonFile $SpecJson -DestDir $OutDir }
}
