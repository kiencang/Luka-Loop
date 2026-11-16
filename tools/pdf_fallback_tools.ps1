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
    [double]$Scale = 2.5,
    [string]$SpecJson = ''
)

$ErrorActionPreference = 'Stop'

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
    if (-not $Pdf -or -not (Test-Path $Pdf)) { throw "PDF not found: $Pdf" }
    $absPdf = (Resolve-Path $Pdf).Path
    if (-not (Test-Path $DestDir)) { New-Item -ItemType Directory -Path $DestDir -Force | Out-Null }
    $absDest = (Resolve-Path $DestDir).Path

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

function Invoke-CropFromJson {
    param([string]$JsonFile, [string]$DestDir)
    if (-not $JsonFile -or -not (Test-Path $JsonFile)) { throw "Spec JSON not found: $JsonFile" }
    Add-Type -AssemblyName System.Drawing
    if (-not (Test-Path $DestDir)) { New-Item -ItemType Directory -Path $DestDir -Force | Out-Null }
    $absDest = (Resolve-Path $DestDir).Path
    $spec = Get-Content -Path $JsonFile -Raw -Encoding UTF8 | ConvertFrom-Json

    foreach ($item in @($spec)) {
        if (-not $item.page_png -or -not (Test-Path $item.page_png)) {
            throw "Source page PNG not found: $($item.page_png)"
        }
        $srcPng = (Resolve-Path $item.page_png).Path
        $bmp = [System.Drawing.Bitmap]::FromFile($srcPng)
        $cropped = $null
        try {
            $bw = $bmp.Width
            $bh = $bmp.Height
            $x0 = [int][Math]::Max(0, [Math]::Round($item.box[0] * $bw))
            $y0 = [int][Math]::Max(0, [Math]::Round($item.box[1] * $bh))
            $x1 = [int][Math]::Min($bw, [Math]::Round($item.box[2] * $bw))
            $y1 = [int][Math]::Min($bh, [Math]::Round($item.box[3] * $bh))
            if ($x1 -le $x0 -or $y1 -le $y0) {
                throw "Invalid crop box [$($item.box -join ',')] for $($item.out_name)"
            }
            $rect = New-Object System.Drawing.Rectangle($x0, $y0, ($x1 - $x0), ($y1 - $y0))
            $cropped = $bmp.Clone($rect, $bmp.PixelFormat)
            if ($item.auto_trim -ne $false) {
                $cropped = Trim-WhiteMargins -Bmp $cropped
            }
            $outFile = Join-Path $absDest $item.out_name
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
