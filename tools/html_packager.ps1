<#
.SYNOPSIS
    Pure Windows PowerShell 5.1 HTML Image Embedder, Reader Shell Injector, Auto-QA Gate & Headless PDF Exporter.
.DESCRIPTION
    Packages translated HTML documents into self-contained files and printable PDFs:
      -Action EmbedImages : Embed local PNG/JPG images as optimized Base64, inject outer reader shell (tools\reader_shell.html) idempotently, run HTML Auto-QA, optionally export PDF (-AlsoPdf), and optionally clean a temp directory (-CleanDir) on success
      -Action HtmlToPdf   : Convert a self-contained HTML file to clean PDF using built-in Microsoft Edge or Chrome headless
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('EmbedImages', 'HtmlToPdf')]
    [string]$Action,

    [string]$HtmlPath = '',
    [string]$OutHtmlPath = '',
    [string]$OutPdfPath = '',
    [switch]$AlsoPdf,
    [int]$JpegQuality = 90,
    [int]$MaxImageWidth = 1400,
    [string]$CleanDir = ''
)

$ErrorActionPreference = 'Stop'

function Get-OptimizedImagePayload {
    param(
        [string]$ImgPath,
        [int]$Quality = 90,
        [int]$MaxWidth = 1400
    )
    Add-Type -AssemblyName System.Drawing
    $origBytes = [System.IO.File]::ReadAllBytes($ImgPath)
    $origLen = $origBytes.Length
    $ext = [System.IO.Path]::GetExtension($ImgPath).ToLowerInvariant()
    $origMime = if ($ext -eq '.jpg' -or $ext -eq '.jpeg') { 'image/jpeg' } else { 'image/png' }

    $inMs = New-Object System.IO.MemoryStream(, $origBytes)
    $bmp = [System.Drawing.Bitmap]::FromStream($inMs)
    $workBmp = $bmp
    try {
        # Sample ~60x60 grid to detect transparency and color richness
        $colors = New-Object 'System.Collections.Generic.HashSet[int]'
        $hasAlpha = $false
        $stepX = [Math]::Max(1, [int]($bmp.Width / 60))
        $stepY = [Math]::Max(1, [int]($bmp.Height / 60))
        for ($y = 0; $y -lt $bmp.Height; $y += $stepY) {
            for ($x = 0; $x -lt $bmp.Width; $x += $stepX) {
                $c = $bmp.GetPixel($x, $y)
                if ($c.A -lt 250) { $hasAlpha = $true }
                $q = (([int]($c.R -shr 3)) -shl 10) -bor (([int]($c.G -shr 3)) -shl 5) -bor ([int]($c.B -shr 3))
                [void]$colors.Add($q)
            }
        }
        $isRichPhoto = ($colors.Count -ge 200)

        $wasResized = $false
        if ($MaxWidth -gt 0 -and $bmp.Width -gt $MaxWidth) {
            $newW = $MaxWidth
            $newH = [Math]::Max(1, [int][Math]::Round($bmp.Height * ($MaxWidth / [double]$bmp.Width)))
            $scaled = New-Object System.Drawing.Bitmap($newW, $newH)
            $g = [System.Drawing.Graphics]::FromImage($scaled)
            try {
                $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
                $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
                $g.DrawImage($bmp, 0, 0, $newW, $newH)
            } finally {
                $g.Dispose()
            }
            $workBmp = $scaled
            $wasResized = $true
        }

        # Encode candidate JPEG at requested quality (default 90%) only for rich-color opaque photos
        if ($isRichPhoto -and -not $hasAlpha) {
            $jpgCodec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq 'image/jpeg' }
            $ep = New-Object System.Drawing.Imaging.EncoderParameters(1)
            $ep.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter([System.Drawing.Imaging.Encoder]::Quality, [long]$Quality)
            $outMs = New-Object System.IO.MemoryStream
            try {
                $workBmp.Save($outMs, $jpgCodec, $ep)
                $jpgBytes = $outMs.ToArray()
                # Strict size check: never keep compressed version if larger or not meaningfully smaller than original
                if ($jpgBytes.Length -lt $origLen -and ($wasResized -or $jpgBytes.Length -le [int]($origLen * 0.85))) {
                    return @{ Bytes = $jpgBytes; Mime = 'image/jpeg'; OrigLen = $origLen }
                }
            } finally {
                $ep.Dispose()
                $outMs.Dispose()
            }
        }

        # If resized low-color diagram, keep lossless PNG only if smaller than original file
        if ($wasResized -and $origMime -eq 'image/png') {
            $outMs = New-Object System.IO.MemoryStream
            try {
                $workBmp.Save($outMs, [System.Drawing.Imaging.ImageFormat]::Png)
                $pngBytes = $outMs.ToArray()
                if ($pngBytes.Length -lt $origLen) {
                    return @{ Bytes = $pngBytes; Mime = 'image/png'; OrigLen = $origLen }
                }
            } finally {
                $outMs.Dispose()
            }
        }

        return @{ Bytes = $origBytes; Mime = $origMime; OrigLen = $origLen }
    } finally {
        if (-not [object]::ReferenceEquals($workBmp, $bmp)) { $workBmp.Dispose() }
        $bmp.Dispose()
        $inMs.Dispose()
    }
}

function Invoke-HtmlQaCheck {
    param([string]$HtmlText)
    $issues = New-Object 'System.Collections.Generic.List[string]'

    $b64Count = ([regex]::Matches($HtmlText, '(?i)src\s*=\s*"data:image/(?:png|jpeg|jpg|webp);base64,')).Count
    $unembedded = ([regex]::Matches($HtmlText, '(?i)<img\b[^>]*\bsrc\s*=\s*"(?!data:|https?://)[^"]+"')).Count
    if ($unembedded -gt 0) {
        $issues.Add("Found $unembedded un-embedded local <img> src link(s).")
    }

    $missingAlt = ([regex]::Matches($HtmlText, '(?i)<img\b(?![^>]*\balt\s*=)[^>]*>')).Count
    if ($missingAlt -gt 0) {
        $issues.Add("Found $missingAlt <img> tag(s) missing alt attribute.")
    }

    # Strip <script> and <style> before checking prose/layout tags
    $domOnly = [regex]::Replace($HtmlText, '(?is)<(?:script|style)\b[^>]*>.*?</(?:script|style)>', '')

    $tableCount = ([regex]::Matches($domOnly, '(?i)<table\b')).Count
    $wrapperCount = ([regex]::Matches($domOnly, '(?i)class\s*=\s*"[^"]*\btable-wrapper\b[^"]*"')).Count
    if ($tableCount -gt $wrapperCount) {
        $issues.Add("Found $tableCount <table> element(s) but only $wrapperCount .table-wrapper container(s).")
    }

    $hasLatex = ($domOnly -match '\\\(') -or ($domOnly -match '\\\[')
    $hasMathJax = $HtmlText -match '(?i)<script\b[^>]*MathJax'
    if ($hasLatex -and -not $hasMathJax) {
        $issues.Add("Detected LaTeX math delimiters without MathJax <script> in <head>.")
    }

    $brokenAnchors = New-Object 'System.Collections.Generic.List[string]'
    foreach ($m in [regex]::Matches($domOnly, '(?i)\bhref\s*=\s*"#([^"]+)"')) {
        $anchor = $m.Groups[1].Value
        if (-not [regex]::IsMatch($domOnly, ('(?i)\bid\s*=\s*"{0}"' -f [regex]::Escape($anchor)))) {
            $brokenAnchors.Add("#$anchor")
        }
    }
    if ($brokenAnchors.Count -gt 0) {
        $issues.Add("Broken internal anchor(s): $($brokenAnchors -join ', ')")
    }

    if ($issues.Count -gt 0) {
        throw ("HTML Auto-QA FAILED:`n - " + ($issues -join "`n - "))
    }
    Write-Output ("[QA PASS] Base64 images: {0} | Tables wrapped: {1}/{2} | LaTeX/MathJax OK | Broken anchors: 0" -f $b64Count, $wrapperCount, $tableCount)
}

function Find-HeadlessBrowser {
    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
        (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'),
        (Join-Path $env:LocalAppData 'Microsoft\Edge\Application\msedge.exe'),
        (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
        (Join-Path $env:LocalAppData 'Google\Chrome\Application\chrome.exe')
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) { return $c }
    }
    return $null
}

function Invoke-HtmlToPdf {
    param([string]$InHtml, [string]$OutPdf = '', [string]$CleanTargetDir = '')
    if (-not $InHtml -or -not (Test-Path $InHtml)) { throw "HTML file not found: $InHtml" }
    $absHtml = (Resolve-Path $InHtml).Path
    $rawPdf = if ($OutPdf) { $OutPdf } else { [System.IO.Path]::ChangeExtension($absHtml, '.pdf') }
    $destPdf = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($rawPdf)
    $parentDir = Split-Path $destPdf -Parent
    if ($parentDir -and -not (Test-Path $parentDir)) { New-Item -ItemType Directory -Path $parentDir -Force | Out-Null }

    $browser = Find-HeadlessBrowser
    if (-not $browser) {
        Write-Warning "Microsoft Edge/Chrome not found; skipped automatic PDF export for $absHtml"
        return
    }

    $tmpProfile = Join-Path $env:TEMP ("edge_pdf_" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmpProfile -Force | Out-Null
    try {
        $uri = ([System.Uri]$absHtml).AbsoluteUri
        $argList = @(
            '--headless',
            '--disable-gpu',
            '--no-pdf-header-footer',
            '--log-level=3',
            '--run-all-compositor-stages-before-draw',
            '--virtual-time-budget=4000',
            ('--user-data-dir="{0}"' -f $tmpProfile),
            ('--print-to-pdf="{0}"' -f $destPdf),
            ('"{0}"' -f $uri)
        )
        $errLog = Join-Path $tmpProfile 'edge_err.log'
        $outLog = Join-Path $tmpProfile 'edge_out.log'
        $proc = Start-Process -FilePath $browser -ArgumentList $argList -Wait -NoNewWindow -PassThru -RedirectStandardError $errLog -RedirectStandardOutput $outLog
        if (-not (Test-Path -LiteralPath $destPdf -PathType Leaf) -or (Get-Item -LiteralPath $destPdf).Length -eq 0) {
            $errDetail = ''
            foreach ($logFile in @($errLog, $outLog)) {
                if (Test-Path -LiteralPath $logFile) {
                    try {
                        $raw = ([System.IO.File]::ReadAllText($logFile, [System.Text.Encoding]::UTF8)).Trim()
                        if ($raw) {
                            if ($raw.Length -gt 600) { $raw = '...' + $raw.Substring($raw.Length - 600) }
                            $errDetail = $raw
                            break
                        }
                    } catch {}
                }
            }
            $msg = "Headless browser failed to export PDF (exit=$($proc.ExitCode)): $destPdf"
            if ($errDetail) { $msg += " | Browser log: $errDetail" }
            throw $msg
        }
        $pdfSz = (Get-Item $destPdf).Length
        Write-Output ("Exported PDF -> {0} ({1:N0} bytes)" -f $destPdf, $pdfSz)
        if ($CleanTargetDir) {
            Invoke-SafeCleanDir -TargetDir $CleanTargetDir -ProtectedPaths @($destPdf)
        }
    } finally {
        Start-Sleep -Milliseconds 200
        Remove-Item -Path $tmpProfile -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-SafeCleanDir {
    param(
        [string]$TargetDir,
        [string[]]$ProtectedPaths = @()
    )
    if (-not $TargetDir -or -not (Test-Path -LiteralPath $TargetDir -PathType Container)) { return }
    $absTarget = (Resolve-Path -LiteralPath $TargetDir).Path.TrimEnd('\', '/')
    $cwd = (Get-Location).Path.TrimEnd('\', '/')
    $root = [System.IO.Path]::GetPathRoot($absTarget).TrimEnd('\', '/')
    if ($absTarget -eq $root -or $absTarget -eq $cwd -or $cwd.StartsWith($absTarget + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean unsafe directory: $absTarget"
    }
    foreach ($p in $ProtectedPaths) {
        if (-not $p) { continue }
        $absP = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($p)
        if ($absP.Equals($absTarget, [System.StringComparison]::OrdinalIgnoreCase) -or $absP.StartsWith($absTarget + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean '$absTarget' because output file '$absP' resides inside it."
        }
    }
    Remove-Item -LiteralPath $absTarget -Recurse -Force
    Write-Output ("Cleaned temp directory -> {0}" -f $absTarget)
}

function Get-ShellSection {
    param([string]$Template, [string]$TagName)
    $m = [regex]::Match($Template, "(?is)<!--\s*${TagName}_START\s*-->(.*?)<!--\s*${TagName}_END\s*-->")
    if (-not $m.Success) {
        throw "Reader shell template missing section: $TagName"
    }
    return $m.Groups[1].Value.Trim()
}

function Invoke-InjectReaderShell {
    param([string]$HtmlText)
    $shellPath = Join-Path $PSScriptRoot 'reader_shell.html'
    if (-not (Test-Path -LiteralPath $shellPath -PathType Leaf)) {
        throw "Reader shell template not found: $shellPath"
    }
    if ($HtmlText -notmatch '(?i)</head>' -or $HtmlText -notmatch '(?i)<body\b[^>]*>' -or $HtmlText -notmatch '(?i)</body>') {
        throw "HTML must contain <head>...</head> and <body>...</body> for reader shell injection."
    }

    $tpl = [System.IO.File]::ReadAllText($shellPath, [System.Text.Encoding]::UTF8)
    $shellCss     = Get-ShellSection -Template $tpl -TagName 'SHELL_CSS'
    $shellToolbar = Get-ShellSection -Template $tpl -TagName 'SHELL_TOOLBAR'
    $shellScript  = Get-ShellSection -Template $tpl -TagName 'SHELL_SCRIPT'

    $injected = New-Object 'System.Collections.Generic.List[string]'
    $out = $HtmlText

    $hasShellCss = ($out -match '(?i)data-reader-shell\s*=\s*"1"') -or (($out -match '(?i)\.reader-toolbar\b') -and ($out -match '(?i)\.img-lightbox\b'))
    if (-not $hasShellCss) {
        $rxHead = New-Object regex('(?i)</head>')
        $out = $rxHead.Replace($out, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $shellCss + "`n" + $m.Value }, 1)
        $injected.Add('CSS')
    }

    $hasToolbar = ($out -match '(?i)data-reader-shell\s*=\s*"toolbar"') -or ($out -match '(?i)class\s*=\s*"[^"]*\b(?:rsfv-toolbar|reader-toolbar)\b')
    if (-not $hasToolbar) {
        $rxBodyOpen = New-Object regex('(?i)<body\b[^>]*>')
        $out = $rxBodyOpen.Replace($out, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $m.Value + "`n" + $shellToolbar }, 1)
        $injected.Add('Toolbar')
    }

    $hasScript = ($out -match '(?i)data-reader-shell\s*=\s*"script"') -or ($out -match '(?i)\bid\s*=\s*"(?:rsfv-img-lightbox|img-lightbox)"')
    if (-not $hasScript) {
        $rxBodyClose = New-Object regex('(?i)</body>')
        $out = $rxBodyClose.Replace($out, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $shellScript + "`n" + $m.Value }, 1)
        $injected.Add('Script')
    }

    return @{ Html = $out; Injected = @($injected) }
}

function Invoke-EmbedImages {
    param(
        [string]$InHtml,
        [string]$OutHtml,
        [string]$OutPdf = '',
        [bool]$ExportPdf = $false,
        [int]$Quality = 90,
        [int]$MaxWidth = 1400,
        [string]$CleanTargetDir = ''
    )
    if (-not $InHtml -or -not (Test-Path $InHtml)) { throw "HTML file not found: $InHtml" }
    $absHtml = (Resolve-Path $InHtml).Path
    $baseDir = Split-Path $absHtml -Parent
    $content = [System.IO.File]::ReadAllText($absHtml, [System.Text.Encoding]::UTF8)

    $stats = @{ Total = 0; Compressed = 0; OrigBytes = [long]0; FinalBytes = [long]0 }
    $pattern = '(?i)<img\b([^>]*?)\bsrc\s*=\s*"([^"]+\.(?:png|jpe?g))"([^>]*)>'
    $updated = [regex]::Replace($content, $pattern, {
        param($m)
        $rel = $m.Groups[2].Value
        if ($rel -match '^(?i)(?:data:|https?://)') { return $m.Value }
        $imgPath = [System.IO.Path]::GetFullPath((Join-Path $baseDir ($rel -replace '/', '\')))
        if (Test-Path $imgPath) {
            $res = Get-OptimizedImagePayload -ImgPath $imgPath -Quality $Quality -MaxWidth $MaxWidth
            $stats.Total++
            $stats.OrigBytes += $res.OrigLen
            $stats.FinalBytes += $res.Bytes.Length
            if ($res.Bytes.Length -lt $res.OrigLen) { $stats.Compressed++ }
            $b64 = [Convert]::ToBase64String($res.Bytes)
            return ('<img{0}src="data:{1};base64,{2}"{3}>' -f $m.Groups[1].Value, $res.Mime, $b64, $m.Groups[3].Value)
        }
        return $m.Value
    })

    $shellRes = Invoke-InjectReaderShell -HtmlText $updated
    $updated = $shellRes.Html
    Invoke-HtmlQaCheck -HtmlText $updated

    $rawDest = if ($OutHtml) { $OutHtml } else { $absHtml }
    $dest = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($rawDest)
    $destDir = Split-Path $dest -Parent
    if ($destDir -and -not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
    [System.IO.File]::WriteAllText($dest, $updated, (New-Object System.Text.UTF8Encoding($false)))
    $sz = (Get-Item $dest).Length
    if ($stats.Total -gt 0) {
        $savedKb = [Math]::Round(($stats.OrigBytes - $stats.FinalBytes) / 1024.0, 1)
        Write-Output ("Optimized {0}/{1} images (Quality={2}%, saved {3:N1} KB raw)" -f $stats.Compressed, $stats.Total, $Quality, $savedKb)
    }
    if ($shellRes.Injected.Count -gt 0) {
        Write-Output ("Injected reader shell -> {0}" -f ($shellRes.Injected -join ', '))
    } else {
        Write-Output "Reader shell already present (skipped injection)"
    }
    Write-Output ("Embedded images into HTML -> {0} ({1:N0} bytes)" -f $dest, $sz)
    $pdfProtected = ''
    if ($ExportPdf -or $OutPdf) {
        $pdfProtected = if ($OutPdf) { $OutPdf } else { [System.IO.Path]::ChangeExtension($dest, '.pdf') }
        Invoke-HtmlToPdf -InHtml $dest -OutPdf $OutPdf
    }
    if ($CleanTargetDir) {
        Invoke-SafeCleanDir -TargetDir $CleanTargetDir -ProtectedPaths @($dest, $pdfProtected)
    }
}

switch ($Action) {
    'EmbedImages' { Invoke-EmbedImages -InHtml $HtmlPath -OutHtml $OutHtmlPath -OutPdf $OutPdfPath -ExportPdf ([bool]$AlsoPdf) -Quality $JpegQuality -MaxWidth $MaxImageWidth -CleanTargetDir $CleanDir }
    'HtmlToPdf'   { Invoke-HtmlToPdf -InHtml $HtmlPath -OutPdf $OutPdfPath -CleanTargetDir $CleanDir }
}
