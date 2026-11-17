<#
.SYNOPSIS
    Pure Windows PowerShell 5.1 PDF Fallback Renderer & Auto-Trim Image Cropper (Zero Python / Zero External Tools).
.DESCRIPTION
    Uses built-in WinRT Windows.Data.Pdf.PdfDocument + System.Drawing for scanned PDFs or manual figure cropping:
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
    [string]$SpecJson = ''
)

$ErrorActionPreference = 'Stop'

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

$script:WinRtLoaded = $false
$script:AsTaskOpMethod = $null
$script:AsTaskActionMethod = $null

function Ensure-WinRtPdf {
    if ($script:WinRtLoaded) { return }
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    [void][Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType = WindowsRuntime]
    [void][Windows.Data.Pdf.PdfPageRenderOptions, Windows.Data.Pdf, ContentType = WindowsRuntime]
    [void][Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
    [void][Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]

    $methods = [System.WindowsRuntimeSystemExtensions].GetMethods()
    $script:AsTaskOpMethod = ($methods | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    })[0]
    $script:AsTaskActionMethod = ($methods | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction'
    })[0]
    $script:WinRtLoaded = $true
}

function Await-WinRtOp {
    param($WinRtOp, [Type]$ResultType)
    $netTask = $script:AsTaskOpMethod.MakeGenericMethod($ResultType).Invoke($null, @($WinRtOp))
    $netTask.Wait() | Out-Null
    return $netTask.Result
}

function Await-WinRtAction {
    param($WinRtAction)
    $netTask = $script:AsTaskActionMethod.Invoke($null, @($WinRtAction))
    $netTask.Wait() | Out-Null
}

function Invoke-RenderPages {
    param([string]$Pdf, [string]$DestDir, [double]$RenderScale)
    if ($RenderScale -lt 0.5 -or $RenderScale -gt 10.0) {
        throw "RenderScale out of safe range (0.5..10.0): $RenderScale"
    }
    Assert-LocalNoUncPath -PathValue $Pdf -ParamName '-PdfPath'
    Assert-LocalNoUncPath -PathValue $DestDir -ParamName '-OutDir'
    if (-not $Pdf -or -not (Test-Path -LiteralPath $Pdf -PathType Leaf)) { throw "PDF not found: $Pdf" }
    $absPdf = (Resolve-Path -LiteralPath $Pdf).Path
    Assert-LocalNoUncPath -PathValue $absPdf -ParamName '-PdfPath'
    $destFull = [System.IO.Path]::GetFullPath($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($DestDir))
    Assert-LocalNoUncPath -PathValue $destFull -ParamName '-OutDir'
    Assert-SafeOutputPath -TargetPath $destFull -Label '-OutDir' -IsDirectory
    if (-not (Test-Path -LiteralPath $destFull -PathType Container)) { [void][System.IO.Directory]::CreateDirectory($destFull) }
    $absDest = (Resolve-Path -LiteralPath $destFull).Path

    Ensure-WinRtPdf
    $pdfFs = $null
    $ras = $null
    $pdfDoc = $null
    try {
        $pdfFs = [System.IO.File]::OpenRead($absPdf)
        $ras = [System.IO.WindowsRuntimeStreamExtensions]::AsRandomAccessStream($pdfFs)
        $pdfDoc = Await-WinRtOp ([Windows.Data.Pdf.PdfDocument]::LoadFromStreamAsync($ras)) ([Windows.Data.Pdf.PdfDocument])
        $count = [int]$pdfDoc.PageCount

        for ($p = 1; $p -le $count; $p++) {
            $page = $pdfDoc.GetPage([uint32]($p - 1))
            $mem = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
            $inStream = $null
            try {
                $opts = New-Object Windows.Data.Pdf.PdfPageRenderOptions
                $opts.DestinationWidth = [uint32][Math]::Max(800, [Math]::Round($page.Size.Width * $RenderScale))
                Await-WinRtAction ($page.RenderToStreamAsync($mem, $opts))
                $mem.Seek(0)
                $inStream = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($mem)
                $outPng = Join-Path $absDest ("page_{0}.png" -f $p)
                Assert-SafeOutputPath -TargetPath $outPng -Label 'RenderPageOutput'
                $fs = [System.IO.File]::Create($outPng)
                try { $inStream.CopyTo($fs) } finally { $fs.Dispose() }
                Write-Output ("Rendered page {0}/{1} -> {2} ({3}px wide)" -f $p, $count, $outPng, $opts.DestinationWidth)
            } finally {
                if ($inStream) { $inStream.Dispose() }
                $mem.Dispose()
                if ($page -is [System.IDisposable]) { $page.Dispose() }
            }
        }
    } finally {
        if ($pdfDoc -is [System.IDisposable]) { $pdfDoc.Dispose() }
        $pdfDoc = $null
        if ($ras) { $ras.Dispose() }
        if ($pdfFs) { $pdfFs.Dispose() }
    }
}

function Ensure-TrimHelper {
    if ('PdfFallbackTrimHelper' -as [type]) { return }
    Add-Type -AssemblyName System.Drawing
    Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;

public static class PdfFallbackTrimHelper {
    public static int[] FindInkBounds(Bitmap bmp, int threshold, int step) {
        int w = bmp.Width;
        int h = bmp.Height;
        Rectangle rect = new Rectangle(0, 0, w, h);
        BitmapData data = bmp.LockBits(rect, ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        try {
            int stride = data.Stride;
            int absStride = Math.Abs(stride);
            byte[] buf = new byte[absStride * h];
            if (stride > 0) {
                Marshal.Copy(data.Scan0, buf, 0, buf.Length);
            } else {
                for (int y = 0; y < h; y++) {
                    IntPtr rowPtr = IntPtr.Add(data.Scan0, y * stride);
                    Marshal.Copy(rowPtr, buf, y * absStride, w * 4);
                }
            }

            int minX = w, minY = h, maxX = -1, maxY = -1;
            int inc = step > 0 ? step : 2;
            for (int y = 0; y < h; y += inc) {
                int rowOff = y * absStride;
                for (int x = 0; x < w; x += inc) {
                    int idx = rowOff + (x * 4);
                    byte b = buf[idx];
                    byte g = buf[idx + 1];
                    byte r = buf[idx + 2];
                    byte a = buf[idx + 3];
                    if (a > 10 && (r < threshold || g < threshold || b < threshold)) {
                        if (x < minX) minX = x;
                        if (x > maxX) maxX = x;
                        if (y < minY) minY = y;
                        if (y > maxY) maxY = y;
                    }
                }
            }
            return new int[] { minX, minY, maxX, maxY };
        } finally {
            bmp.UnlockBits(data);
        }
    }
}
'@
}

function Trim-WhiteMargins {
    param([System.Drawing.Bitmap]$Bmp, [int]$Threshold = 247, [int]$Pad = 6)
    Ensure-TrimHelper
    $w = $Bmp.Width
    $h = $Bmp.Height
    $bounds = [PdfFallbackTrimHelper]::FindInkBounds($Bmp, $Threshold, 2)
    $minX = $bounds[0]; $minY = $bounds[1]; $maxX = $bounds[2]; $maxY = $bounds[3]
    if ($maxX -lt $minX -or $maxY -lt $minY) {
        return $Bmp
    }
    $x0 = [Math]::Max(0, $minX - $Pad)
    $y0 = [Math]::Max(0, $minY - $Pad)
    $x1 = [Math]::Min($w - 1, $maxX + $Pad)
    $y1 = [Math]::Min($h - 1, $maxY + $Pad)
    if ($x0 -eq 0 -and $y0 -eq 0 -and $x1 -eq ($w - 1) -and $y1 -eq ($h - 1)) {
        return $Bmp
    }
    $rect = New-Object System.Drawing.Rectangle($x0, $y0, ($x1 - $x0 + 1), ($y1 - $y0 + 1))
    $trimmed = $Bmp.Clone($rect, $Bmp.PixelFormat)
    $Bmp.Dispose()
    return $trimmed
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
    Assert-LocalNoUncPath -PathValue $DestDir -ParamName '-OutDir'
    if (-not $JsonFile -or -not (Test-Path -LiteralPath $JsonFile -PathType Leaf)) { throw "Spec JSON not found: $JsonFile" }
    Add-Type -AssemblyName System.Drawing
    $destFull = [System.IO.Path]::GetFullPath($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($DestDir))
    Assert-LocalNoUncPath -PathValue $destFull -ParamName '-OutDir'
    Assert-SafeOutputPath -TargetPath $destFull -Label '-OutDir' -IsDirectory
    if (-not (Test-Path -LiteralPath $destFull -PathType Container)) { [void][System.IO.Directory]::CreateDirectory($destFull) }
    $absDest = (Resolve-Path -LiteralPath $destFull).Path
    $absJson = (Resolve-Path -LiteralPath $JsonFile).Path
    Assert-LocalNoUncPath -PathValue $absJson -ParamName '-SpecJson'
    $absJsonDir = Split-Path $absJson -Parent
    $allowedInputRoots = Get-AllowedCropInputRoots -JsonDir $absJsonDir -DestDir $absDest
    $spec = Get-Content -LiteralPath $absJson -Raw -Encoding UTF8 | ConvertFrom-Json

    foreach ($item in @($spec)) {
        $srcPng = Resolve-SafeCropInputFile -RawPagePath ([string]$item.page_png) -AllowedRoots $allowedInputRoots
        $outFile = Resolve-SafeCropOutFile -DestDir $absDest -OutName ([string]$item.out_name)
        $box = Resolve-CropBoxCoords -Box $item.box -OutName ([string]$item.out_name)
        $bmp = [System.Drawing.Bitmap]::FromFile($srcPng)
        $cropped = $null
        try {
            $bw = $bmp.Width
            $bh = $bmp.Height
            $x0 = [int][Math]::Max(0, [Math]::Round($box[0] * $bw))
            $y0 = [int][Math]::Max(0, [Math]::Round($box[1] * $bh))
            $x1 = [int][Math]::Min($bw, [Math]::Round($box[2] * $bw))
            $y1 = [int][Math]::Min($bh, [Math]::Round($box[3] * $bh))
            if ($x1 -le $x0 -or $y1 -le $y0) {
                throw "Invalid crop box [$($box -join ',')] for $($item.out_name)"
            }
            $rect = New-Object System.Drawing.Rectangle($x0, $y0, ($x1 - $x0), ($y1 - $y0))
            $cropped = $bmp.Clone($rect, $bmp.PixelFormat)
            if ($item.auto_trim -ne $false) {
                $cropped = Trim-WhiteMargins -Bmp $cropped
            }
            $cropped.Save($outFile, [System.Drawing.Imaging.ImageFormat]::Png)
            Write-Output ("Cropped {0} -> {1} ({2}x{3})" -f $item.out_name, $outFile, $cropped.Width, $cropped.Height)
        } finally {
            if ($cropped) { $cropped.Dispose() }
            $bmp.Dispose()
        }
    }
}

switch ($Action) {
    'RenderPages'  { Invoke-RenderPages -Pdf $PdfPath -DestDir $OutDir -RenderScale $Scale }
    'CropFromJson' { Invoke-CropFromJson -JsonFile $SpecJson -DestDir $OutDir }
}
