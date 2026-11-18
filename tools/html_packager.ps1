<#
.SYNOPSIS
    PowerShell 5.1 & 7+ HTML Image Embedder, Reader Shell Injector, Auto-QA Gate & Headless PDF Exporter.
.DESCRIPTION
    Packages translated HTML documents into self-contained files and printable PDFs (delegates image optimization to extract_assets.exe / PyMuPDF; zero System.Drawing / Add-Type):
      -Action EmbedImages : Embed local PNG/JPG images as optimized Base64, inject outer reader shell (tools\reader_shell.html) idempotently (unless -PreserveLayout), run HTML Auto-QA, optionally export PDF (-AlsoPdf), always auto-number colliding output names (_2, _3, ...), and optionally clean a temp directory (-CleanDir) on success
      -Action HtmlToPdf   : Convert a self-contained HTML file to clean PDF using built-in Microsoft Edge or Chrome headless (always auto-numbers colliding output names)
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('EmbedImages', 'HtmlToPdf')]
    [string]$Action,

    [string]$HtmlPath = '',
    [string]$OutHtmlPath = '',
    [string]$OutPdfPath = '',
    [switch]$AlsoPdf,
    [switch]$PreserveLayout,
    [ValidateRange(1, 100)]
    [int]$JpegQuality = 90,
    [ValidateRange(0, 10000)]
    [int]$MaxImageWidth = 1400,
    [string]$CleanDir = '',
    [ValidateRange(5, 600)]
    [int]$PdfTimeoutSeconds = 60
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

function Invoke-BatchOptimizeImages {
    <# Validates optimization params, runs extract_assets.exe (--mode optimize-images) once for unique image paths, and returns a Data URI cache. #>
    param(
        [string[]]$ImagePaths,
        [int]$Quality = 90,
        [int]$MaxWidth = 1400
    )
    if ($Quality -lt 1 -or $Quality -gt 100) { throw "JpegQuality out of valid range (1..100): $Quality" }
    if ($MaxWidth -lt 0 -or $MaxWidth -gt 10000) { throw "MaxImageWidth out of valid range (0..10000): $MaxWidth" }

    $cache = @{}
    if (-not $ImagePaths -or $ImagePaths.Count -eq 0) {
        return $cache
    }

    $tempBase = if ($env:TEMP -and $env:TEMP.Trim()) { $env:TEMP } else { [System.IO.Path]::GetTempPath() }
    $tmpRoot = Join-Path $tempBase ("luka_opt_" + [Guid]::NewGuid().ToString("N"))
    Assert-SafeOutputPath -TargetPath $tmpRoot -Label 'TempOptimizeDir' -IsDirectory
    [void][System.IO.Directory]::CreateDirectory($tmpRoot)
    try {
        $specItems = New-Object 'System.Collections.Generic.List[object]'
        foreach ($p in $ImagePaths) {
            [void]$specItems.Add(@{ path = $p })
        }
        $specPath = Join-Path $tmpRoot 'optimize_spec.json'
        $outDir = Join-Path $tmpRoot 'out'
        $outJsonPath = Join-Path $tmpRoot 'optimize_result.json'
        $specJson = ConvertTo-Json -InputObject ([pscustomobject]@{ items = $specItems.ToArray() }) -Depth 4 -Compress
        [System.IO.File]::WriteAllText($specPath, $specJson, (New-Object System.Text.UTF8Encoding($false)))

        Invoke-ExtractAssetsExe -Arguments @(
            '--mode', 'optimize-images',
            '--spec', $specPath,
            '--out-dir', $outDir,
            '--out-json', $outJsonPath,
            '--quality', [string]$Quality,
            '--max-width', [string]$MaxWidth
        )

        if (-not (Test-Path -LiteralPath $outJsonPath -PathType Leaf)) {
            throw "Image optimizer did not produce output metadata: $outJsonPath"
        }
        $meta = [System.IO.File]::ReadAllText($outJsonPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
        $results = @($meta.results)
        if ($results.Count -ne $ImagePaths.Count) {
            throw "Image optimizer result count mismatch (expected $($ImagePaths.Count), got $($results.Count))."
        }
        for ($i = 0; $i -lt $results.Count; $i++) {
            $res = $results[$i]
            $origPath = $ImagePaths[$i]
            $bytesPath = if ($res.out_file -and ([string]$res.out_file).Trim()) { [string]$res.out_file } else { $origPath }
            $payloadBytes = [System.IO.File]::ReadAllBytes($bytesPath)
            $b64 = [Convert]::ToBase64String($payloadBytes)
            $cache[$origPath] = @{
                DataUri  = ('data:{0};base64,{1}' -f [string]$res.mime, $b64)
                OrigLen  = [long]$res.orig_len
                FinalLen = [long]$payloadBytes.Length
            }
        }
    } finally {
        Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    return $cache
}

$script:ImgTagRx = New-Object regex('(?is)<img\b((?:[^>"'']|"[^"]*"|''[^'']*'')*)>')
$script:ImgSrcRx = New-Object regex('(?is)((?:^|\s)src\s*=\s*)(?:"([^"]*)"|''([^'']*)''|([^\s"''=<>`]+))')

function Get-ImgSrcValue {
    param([System.Text.RegularExpressions.Match]$SrcMatch)
    if ($SrcMatch.Groups[2].Success) { return $SrcMatch.Groups[2].Value }
    if ($SrcMatch.Groups[3].Success) { return $SrcMatch.Groups[3].Value }
    return $SrcMatch.Groups[4].Value
}

function Invoke-HtmlQaCheck {
    param(
        [string]$HtmlText,
        [bool]$SkipTableWrapperCheck = $false
    )
    $issues = New-Object 'System.Collections.Generic.List[string]'

    if ($HtmlText -notmatch '(?i)<head\b[^>]*>' -or $HtmlText -notmatch '(?i)</head>' -or $HtmlText -notmatch '(?i)<body\b[^>]*>' -or $HtmlText -notmatch '(?i)</body>') {
        $issues.Add("HTML must contain complete <head>...</head> and <body>...</body> sections.")
    }

    # Strip <script> and <style> before checking prose/layout/img tags
    $domOnly = [regex]::Replace($HtmlText, '(?is)<(?:script|style)\b[^>]*>.*?</(?:script|style)>', '')

    $b64Count = 0
    $unembedded = 0
    $missingAlt = 0
    foreach ($imgMatch in $script:ImgTagRx.Matches($domOnly)) {
        $attrs = $imgMatch.Groups[1].Value
        if ($attrs -notmatch '(?is)(?:^|\s)alt\s*=') {
            $missingAlt++
        }
        foreach ($srcMatch in $script:ImgSrcRx.Matches($attrs)) {
            $rawSrc = Get-ImgSrcValue -SrcMatch $srcMatch
            if ($rawSrc -eq '') { continue }
            $srcVal = $rawSrc.Trim()
            if ($srcVal -match '^(?i)data:image/(?:png|jpeg|jpg|webp);base64,') {
                $b64Count++
            } elseif ($srcVal -notmatch '^(?i)(?:data:|https?://)') {
                $unembedded++
            }
        }
    }
    if ($unembedded -gt 0) {
        $issues.Add("Found $unembedded un-embedded local <img> src link(s).")
    }
    if ($missingAlt -gt 0) {
        $issues.Add("Found $missingAlt <img> tag(s) missing alt attribute.")
    }

    $tableCount = ([regex]::Matches($domOnly, '(?i)<table\b')).Count
    $wrapperCount = ([regex]::Matches($domOnly, '(?i)\bclass\s*=\s*(?:"[^"]*\btable-wrapper\b[^"]*"|''[^'']*\btable-wrapper\b[^'']*'')')).Count
    if (-not $SkipTableWrapperCheck -and $tableCount -gt $wrapperCount) {
        $issues.Add("Found $tableCount <table> element(s) but only $wrapperCount .table-wrapper container(s).")
    }

    $proseForLatex = [regex]::Replace($domOnly, '(?is)<pre\b[^>]*>.*?</pre>', '')
    $proseForLatex = [regex]::Replace($proseForLatex, '(?is)<code\b[^>]*>.*?</code>', '')
    $proseForLatex = [regex]::Replace($proseForLatex, '(?is)<textarea\b[^>]*>.*?</textarea>', '')
    $hasLatex = ($proseForLatex -match '\\\(') -or ($proseForLatex -match '\\\[')
    $hasMathJax = $HtmlText -match '(?i)<script\b[^>]*MathJax'
    if ($hasLatex -and -not $hasMathJax) {
        $issues.Add("Detected LaTeX math delimiters without MathJax <script> in <head>.")
    }

    $brokenAnchors = New-Object 'System.Collections.Generic.List[string]'
    foreach ($m in [regex]::Matches($domOnly, '(?i)\bhref\s*=\s*(?:"#([^"]+)"|''#([^'']+)'')')) {
        $anchor = if ($m.Groups[1].Success) { $m.Groups[1].Value } else { $m.Groups[2].Value }
        $esc = [regex]::Escape($anchor)
        if (-not [regex]::IsMatch($domOnly, ('(?i)\bid\s*=\s*(?:"{0}"|''{0}'')' -f $esc))) {
            $brokenAnchors.Add("#$anchor")
        }
    }
    if ($brokenAnchors.Count -gt 0) {
        $issues.Add("Broken internal anchor(s): $($brokenAnchors -join ', ')")
    }

    if ($issues.Count -gt 0) {
        throw ("HTML Auto-QA FAILED:`n - " + ($issues -join "`n - "))
    }
    $tableStatus = if ($SkipTableWrapperCheck) {
        "Tables: $tableCount (wrapper optional)"
    } else {
        "Tables wrapped: $wrapperCount/$tableCount"
    }
    Write-Output ("[QA PASS] Base64 images: {0} | {1} | LaTeX/MathJax OK | Broken anchors: 0" -f $b64Count, $tableStatus)
}

function Find-HeadlessBrowser {
    $rootsAndSubpaths = @(
        @(${env:ProgramFiles(x86)}, 'Microsoft\Edge\Application\msedge.exe'),
        @($env:ProgramFiles,        'Microsoft\Edge\Application\msedge.exe'),
        @($env:LocalAppData,        'Microsoft\Edge\Application\msedge.exe'),
        @($env:ProgramFiles,        'Google\Chrome\Application\chrome.exe'),
        @(${env:ProgramFiles(x86)}, 'Google\Chrome\Application\chrome.exe'),
        @($env:LocalAppData,        'Google\Chrome\Application\chrome.exe')
    )
    foreach ($pair in $rootsAndSubpaths) {
        $base = $pair[0]
        if (-not $base -or -not $base.Trim()) { continue }
        $candidate = Join-Path $base $pair[1]
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    return $null
}

function Get-IndexedFilePath {
    param(
        [string]$BasePath,
        [int]$Index
    )
    if ($Index -le 1) { return $BasePath }
    $dir = [System.IO.Path]::GetDirectoryName($BasePath)
    $stem = [System.IO.Path]::GetFileNameWithoutExtension($BasePath)
    $ext = [System.IO.Path]::GetExtension($BasePath)
    return (Join-Path $dir ("{0}_{1}{2}" -f $stem, $Index, $ext))
}

function Find-NextAvailableIndex {
    <# Finds the lowest >=1 suffix index where none of the candidate paths already exist. #>
    param([string[]]$CandidatePaths)
    $idx = 1
    while ($true) {
        $anyExists = $false
        foreach ($base in $CandidatePaths) {
            if (-not $base) { continue }
            $cand = Get-IndexedFilePath -BasePath $base -Index $idx
            if (Test-Path -LiteralPath $cand) {
                $anyExists = $true
                break
            }
        }
        if (-not $anyExists) { return $idx }
        $idx++
    }
}

function Invoke-HtmlToPdf {
    param(
        [string]$InHtml,
        [string]$OutPdf = '',
        [string]$CleanTargetDir = '',
        [int]$TimeoutSeconds = 60
    )
    Assert-LocalNoUncPath -PathValue $InHtml -ParamName '-HtmlPath'
    Assert-LocalNoUncPath -PathValue $OutPdf -ParamName '-OutPdfPath'
    Assert-LocalNoUncPath -PathValue $CleanTargetDir -ParamName '-CleanDir'

    if (-not $InHtml -or -not (Test-Path -LiteralPath $InHtml -PathType Leaf)) { throw "HTML file not found: $InHtml" }
    $absHtml = (Resolve-Path -LiteralPath $InHtml).Path
    Assert-LocalNoUncPath -PathValue $absHtml -ParamName '-HtmlPath'
    $rawPdf = if ($OutPdf) { $OutPdf } else { [System.IO.Path]::ChangeExtension($absHtml, '.pdf') }
    $destPdf = [System.IO.Path]::GetFullPath($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($rawPdf))
    Assert-LocalNoUncPath -PathValue $destPdf -ParamName '-OutPdfPath'
    Assert-SafeOutputPath -TargetPath $destPdf -Label '-OutPdfPath'
    $pdfIdx = Find-NextAvailableIndex -CandidatePaths @($destPdf)
    if ($pdfIdx -gt 1) {
        $destPdf = Get-IndexedFilePath -BasePath $destPdf -Index $pdfIdx
        Assert-SafeOutputPath -TargetPath $destPdf -Label '-OutPdfPath'
        Write-Output ("Output collision avoided; auto-numbered -> {0}" -f $destPdf)
    }
    $parentDir = Split-Path $destPdf -Parent
    if ($parentDir -and -not (Test-Path -LiteralPath $parentDir -PathType Container)) {
        [void][System.IO.Directory]::CreateDirectory($parentDir)
    }

    $browser = Find-HeadlessBrowser
    if (-not $browser) {
        Write-Warning "Microsoft Edge/Chrome not found; skipped automatic PDF export for $absHtml"
        return
    }

    $tempBase = if ($env:TEMP -and $env:TEMP.Trim()) { $env:TEMP } else { [System.IO.Path]::GetTempPath() }
    $tmpProfile = Join-Path $tempBase ("edge_pdf_" + [Guid]::NewGuid().ToString("N"))
    [void][System.IO.Directory]::CreateDirectory($tmpProfile)
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
        $proc = Start-Process -FilePath $browser -ArgumentList $argList -NoNewWindow -PassThru -RedirectStandardError $errLog -RedirectStandardOutput $outLog
        if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
            $pidToKill = $proc.Id
            try { cmd /c "taskkill /PID $pidToKill /T /F" 2>&1 | Out-Null } catch {}
            try { if (-not $proc.HasExited) { $proc.Kill() } } catch {}
            throw "Headless browser timed out after $TimeoutSeconds s while exporting PDF: $destPdf"
        }
        $proc.WaitForExit()
        if (-not (Test-Path -LiteralPath $destPdf -PathType Leaf) -or (Get-Item -LiteralPath $destPdf).Length -eq 0) {
            $errDetail = ''
            foreach ($logFile in @($errLog, $outLog)) {
                if (Test-Path -LiteralPath $logFile -PathType Leaf) {
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
        $pdfSz = (Get-Item -LiteralPath $destPdf).Length
        Write-Output ("Exported PDF -> {0} ({1:N0} bytes)" -f $destPdf, $pdfSz)
        if ($CleanTargetDir) {
            Invoke-SafeCleanDir -TargetDir $CleanTargetDir -ProtectedPaths @($destPdf)
        }
    } finally {
        Start-Sleep -Milliseconds 200
        Remove-Item -LiteralPath $tmpProfile -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Get-AllowedWorkRoots {
    <# Returns canonical 'work' directory roots eligible for cleanup (repo root and safe CWD). #>
    $roots = New-Object 'System.Collections.Generic.List[string]'
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)

    $repoRoot = [System.IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent)).TrimEnd('\', '/')
    if ($repoRoot -and $repoRoot -ne [System.IO.Path]::GetPathRoot($repoRoot).TrimEnd('\', '/')) {
        $repoWork = [System.IO.Path]::GetFullPath((Join-Path $repoRoot 'work')).TrimEnd('\', '/')
        if ($seen.Add($repoWork)) { [void]$roots.Add($repoWork) }
    }

    $loc = Get-Location
    if ($loc.Provider.Name -eq 'FileSystem') {
        $cwdPath = [System.IO.Path]::GetFullPath($loc.ProviderPath).TrimEnd('\', '/')
        $cwdDriveRoot = [System.IO.Path]::GetPathRoot($cwdPath).TrimEnd('\', '/')
        $blockedCwds = @(
            $env:USERPROFILE,
            $env:PUBLIC,
            $env:WINDIR,
            $env:SystemRoot,
            $env:ProgramFiles,
            ${env:ProgramFiles(x86)}
        ) | Where-Object { $_ } | ForEach-Object { [System.IO.Path]::GetFullPath($_).TrimEnd('\', '/') }

        if ($cwdPath -and -not $cwdPath.Equals($cwdDriveRoot, [System.StringComparison]::OrdinalIgnoreCase) -and ($blockedCwds -notcontains $cwdPath)) {
            $cwdWork = [System.IO.Path]::GetFullPath((Join-Path $cwdPath 'work')).TrimEnd('\', '/')
            if ($seen.Add($cwdWork)) { [void]$roots.Add($cwdWork) }
        }
    }

    return @($roots)
}

function Assert-NoReparsePointsInTree {
    <# Rejects symlinks/junctions anywhere from the allowed 'work' root down through all descendants. #>
    param(
        [string]$RootWorkDir,
        [string]$TargetDir
    )
    $rel = $TargetDir.Substring($RootWorkDir.Length).TrimStart('\', '/')
    $segments = if ($rel) { @($rel -split '[\\/]+') } else { @() }

    # Walk ancestor segments from work\ down to TargetDir so outer junctions cannot redirect deletion
    $probe = $RootWorkDir
    $probeItem = Get-Item -LiteralPath $probe -Force -ErrorAction Stop
    if (Test-IsReparsePoint -Item $probeItem) {
        throw "Refusing to clean reparse point (symlink/junction): $probe"
    }
    foreach ($seg in $segments) {
        $probe = Join-Path $probe $seg
        $probeItem = Get-Item -LiteralPath $probe -Force -ErrorAction Stop
        if (Test-IsReparsePoint -Item $probeItem) {
            throw "Refusing to clean reparse point (symlink/junction): $probe"
        }
    }

    # Breadth-first scan of descendants without descending into child junctions/symlinks
    $queue = New-Object 'System.Collections.Generic.Queue[System.IO.DirectoryInfo]'
    $queue.Enqueue((New-Object System.IO.DirectoryInfo($TargetDir)))
    while ($queue.Count -gt 0) {
        $dirInfo = $queue.Dequeue()
        if (Test-IsReparsePoint -Item $dirInfo) {
            throw "Refusing to clean directory containing symlink/junction: $($dirInfo.FullName)"
        }
        foreach ($entry in $dirInfo.GetFileSystemInfos()) {
            if (Test-IsReparsePoint -Item $entry) {
                throw "Refusing to clean entry because it is a symlink/junction: $($entry.FullName)"
            }
            if ($entry -is [System.IO.DirectoryInfo]) {
                $queue.Enqueue($entry)
            }
        }
    }
}

function Invoke-SafeCleanDir {
    param(
        [string]$TargetDir,
        [string[]]$ProtectedPaths = @()
    )
    if (-not $TargetDir -or -not $TargetDir.Trim()) { return }
    Assert-LocalNoUncPath -PathValue $TargetDir -ParamName '-CleanDir'

    [System.Management.Automation.ProviderInfo]$provider = $null
    [System.Management.Automation.PSDriveInfo]$drive = $null
    $rawResolved = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($TargetDir, [ref]$provider, [ref]$drive)
    if ($null -eq $provider -or $provider.Name -ne 'FileSystem') {
        throw "Refusing to clean non-filesystem path: $TargetDir"
    }
    $absTarget = [System.IO.Path]::GetFullPath($rawResolved).TrimEnd('\', '/')

    $matchedWorkRoot = $null
    foreach ($wRoot in (Get-AllowedWorkRoots)) {
        if ($absTarget.Equals($wRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
            $absTarget.StartsWith($wRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
            $matchedWorkRoot = $wRoot
            break
        }
    }
    if (-not $matchedWorkRoot) {
        throw "Refusing to clean unsafe directory (only 'work' or subdirectories inside 'work\' are allowed): $absTarget"
    }

    $existing = Get-Item -LiteralPath $absTarget -Force -ErrorAction SilentlyContinue
    if (-not $existing) { return }
    if (Test-IsReparsePoint -Item $existing) {
        throw "Refusing to clean reparse point (symlink/junction): $absTarget"
    }
    if (-not $existing.PSIsContainer) {
        throw "Refusing to clean non-directory path: $absTarget"
    }

    foreach ($p in $ProtectedPaths) {
        if (-not $p) { continue }
        $absP = [System.IO.Path]::GetFullPath($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($p)).TrimEnd('\', '/')
        if ($absP.Equals($absTarget, [System.StringComparison]::OrdinalIgnoreCase) -or
            $absP.StartsWith($absTarget + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean '$absTarget' because output file '$absP' resides inside it."
        }
    }

    Assert-NoReparsePointsInTree -RootWorkDir $matchedWorkRoot -TargetDir $absTarget
    $cleanErr = $null
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Remove-Item -LiteralPath $absTarget -Recurse -Force -ErrorAction Stop
            $cleanErr = $null
            break
        } catch {
            $cleanErr = $_
            if ($attempt -lt 3) { Start-Sleep -Milliseconds 400 }
        }
    }
    if (-not (Test-Path -LiteralPath $absTarget)) {
        Write-Output ("Cleaned temp directory -> {0}" -f $absTarget)
    } elseif ($cleanErr) {
        Write-Warning ("Could not fully clean temp directory (locked by sync/antivirus?): {0} ({1})" -f $absTarget, $cleanErr.Exception.Message)
    }
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

function Resolve-SafeSubImagePath {
    <# Resolves relative local <img> src strictly within $BaseDir and blocks symlinks/junctions. #>
    param(
        [string]$BaseDir,
        [string]$RelativeSrc
    )
    $trimmed = $RelativeSrc.Trim()
    if (-not $trimmed) {
        throw "Empty local image src is not allowed."
    }
    if ($trimmed.StartsWith('/') -or $trimmed.StartsWith('\') -or $trimmed.Contains(':')) {
        throw "Path traversal / unsafe image src blocked: $RelativeSrc"
    }

    $relWin = $trimmed -replace '/', '\'
    if ([System.IO.Path]::IsPathRooted($relWin)) {
        throw "Path traversal / rooted image src blocked: $RelativeSrc"
    }

    $normBase = [System.IO.Path]::GetFullPath($BaseDir).TrimEnd('\', '/')
    $normTarget = [System.IO.Path]::GetFullPath((Join-Path $normBase $relWin)).TrimEnd('\', '/')
    if (-not $normTarget.StartsWith($normBase + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path traversal blocked: image src '$RelativeSrc' escapes base directory '$normBase'"
    }

    $baseItem = Get-Item -LiteralPath $normBase -Force -ErrorAction SilentlyContinue
    if ($baseItem -and (Test-IsReparsePoint -Item $baseItem)) {
        throw "Blocked reparse point (symlink/junction) at image base directory: $normBase"
    }

    $rel = $normTarget.Substring($normBase.Length).TrimStart('\', '/')
    $probe = $normBase
    foreach ($seg in ($rel -split '[\\/]+')) {
        if (-not $seg) { continue }
        $probe = Join-Path $probe $seg
        $item = Get-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
        if (-not $item) { return $null }
        if (Test-IsReparsePoint -Item $item) {
            throw "Blocked reparse point (symlink/junction) in image path: $probe"
        }
    }

    $leaf = Get-Item -LiteralPath $normTarget -Force -ErrorAction SilentlyContinue
    if (-not $leaf) { return $null }
    if ($leaf.PSIsContainer) {
        throw "Expected image file, found directory: $normTarget"
    }
    return $normTarget
}

function Invoke-EmbedImages {
    param(
        [string]$InHtml,
        [string]$OutHtml,
        [string]$OutPdf = '',
        [bool]$ExportPdf = $false,
        [bool]$PreserveLayoutMode = $false,
        [int]$Quality = 90,
        [int]$MaxWidth = 1400,
        [string]$CleanTargetDir = '',
        [int]$TimeoutSeconds = 60
    )
    Assert-LocalNoUncPath -PathValue $InHtml -ParamName '-HtmlPath'
    Assert-LocalNoUncPath -PathValue $OutHtml -ParamName '-OutHtmlPath'
    Assert-LocalNoUncPath -PathValue $OutPdf -ParamName '-OutPdfPath'
    Assert-LocalNoUncPath -PathValue $CleanTargetDir -ParamName '-CleanDir'

    if (-not $InHtml -or -not (Test-Path -LiteralPath $InHtml -PathType Leaf)) { throw "HTML file not found: $InHtml" }
    $absHtml = (Resolve-Path -LiteralPath $InHtml).Path
    Assert-LocalNoUncPath -PathValue $absHtml -ParamName '-HtmlPath'
    $baseDir = Split-Path $absHtml -Parent
    $content = [System.IO.File]::ReadAllText($absHtml, [System.Text.Encoding]::UTF8)

    if ($Quality -lt 1 -or $Quality -gt 100) { throw "JpegQuality out of valid range (1..100): $Quality" }
    if ($MaxWidth -lt 0 -or $MaxWidth -gt 10000) { throw "MaxImageWidth out of valid range (0..10000): $MaxWidth" }

    $uniqueImgPaths = New-Object 'System.Collections.Generic.List[string]'
    $seenImgPaths = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($imgMatch in $script:ImgTagRx.Matches($content)) {
        $attrs = $imgMatch.Groups[1].Value
        foreach ($srcMatch in $script:ImgSrcRx.Matches($attrs)) {
            $rel = (Get-ImgSrcValue -SrcMatch $srcMatch).Trim()
            if (-not $rel -or $rel -match '^(?i)(?:data:|https?://)') { continue }
            if ($rel -match '(?i)\.(?:png|jpe?g)$') {
                $imgPath = Resolve-SafeSubImagePath -BaseDir $baseDir -RelativeSrc $rel
                if ($imgPath -and $seenImgPaths.Add($imgPath)) {
                    [void]$uniqueImgPaths.Add($imgPath)
                }
            }
        }
    }

    $optCache = Invoke-BatchOptimizeImages -ImagePaths @($uniqueImgPaths) -Quality $Quality -MaxWidth $MaxWidth

    $stats = @{ Total = 0; Compressed = 0; OrigBytes = [long]0; FinalBytes = [long]0 }
    $updated = $script:ImgTagRx.Replace($content, [System.Text.RegularExpressions.MatchEvaluator]{
        param($imgMatch)
        $attrs = $imgMatch.Groups[1].Value
        $newAttrs = $script:ImgSrcRx.Replace($attrs, [System.Text.RegularExpressions.MatchEvaluator]{
            param($srcMatch)
            $prefix = $srcMatch.Groups[1].Value
            $rel = (Get-ImgSrcValue -SrcMatch $srcMatch).Trim()
            if (-not $rel -or $rel -match '^(?i)(?:data:|https?://)') { return $srcMatch.Value }
            if ($rel -match '(?i)\.(?:png|jpe?g)$') {
                $imgPath = Resolve-SafeSubImagePath -BaseDir $baseDir -RelativeSrc $rel
                if ($imgPath -and $optCache.ContainsKey($imgPath)) {
                    $entry = $optCache[$imgPath]
                    $stats.Total++
                    $stats.OrigBytes += $entry.OrigLen
                    $stats.FinalBytes += $entry.FinalLen
                    if ($entry.FinalLen -lt $entry.OrigLen) { $stats.Compressed++ }
                    return ('{0}"{1}"' -f $prefix, $entry.DataUri)
                }
            }
            return $srcMatch.Value
        })
        return ('<img' + $newAttrs + '>')
    })

    $shellInjected = @()
    if (-not $PreserveLayoutMode) {
        $shellRes = Invoke-InjectReaderShell -HtmlText $updated
        $updated = $shellRes.Html
        $shellInjected = @($shellRes.Injected)
    }
    Invoke-HtmlQaCheck -HtmlText $updated -SkipTableWrapperCheck:$PreserveLayoutMode

    $hasExplicitOutHtml = [bool]($OutHtml -and $OutHtml.Trim())
    $rawDest = if ($hasExplicitOutHtml) { $OutHtml } else { $absHtml }
    $dest = [System.IO.Path]::GetFullPath($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($rawDest))
    Assert-LocalNoUncPath -PathValue $dest -ParamName '-OutHtmlPath'
    Assert-SafeOutputPath -TargetPath $dest -Label '-OutHtmlPath'

    $wantPdf = $ExportPdf -or [bool]($OutPdf -and $OutPdf.Trim())
    $hasCustomOutPdf = [bool]($OutPdf -and $OutPdf.Trim())
    $pdfProtected = ''
    if ($wantPdf) {
        $rawPdfOut = if ($hasCustomOutPdf) { $OutPdf } else { [System.IO.Path]::ChangeExtension($dest, '.pdf') }
        $pdfProtected = [System.IO.Path]::GetFullPath($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($rawPdfOut))
        Assert-LocalNoUncPath -PathValue $pdfProtected -ParamName '-OutPdfPath'
        Assert-SafeOutputPath -TargetPath $pdfProtected -Label '-OutPdfPath'
    }

    if ($hasExplicitOutHtml -and (-not $hasCustomOutPdf)) {
        $pairCandidates = if ($wantPdf) { @($dest, $pdfProtected) } else { @($dest) }
        $pairIdx = Find-NextAvailableIndex -CandidatePaths $pairCandidates
        if ($pairIdx -gt 1) {
            $dest = Get-IndexedFilePath -BasePath $dest -Index $pairIdx
            Assert-SafeOutputPath -TargetPath $dest -Label '-OutHtmlPath'
            Write-Output ("Output collision avoided; auto-numbered -> {0}" -f $dest)
            if ($wantPdf) {
                $pdfProtected = Get-IndexedFilePath -BasePath $pdfProtected -Index $pairIdx
                Assert-SafeOutputPath -TargetPath $pdfProtected -Label '-OutPdfPath'
            }
        }
    } else {
        if ($hasExplicitOutHtml) {
            $htmlIdx = Find-NextAvailableIndex -CandidatePaths @($dest)
            if ($htmlIdx -gt 1) {
                $dest = Get-IndexedFilePath -BasePath $dest -Index $htmlIdx
                Assert-SafeOutputPath -TargetPath $dest -Label '-OutHtmlPath'
                Write-Output ("Output collision avoided; auto-numbered -> {0}" -f $dest)
            }
        }
        if ($wantPdf) {
            $pdfIdx = Find-NextAvailableIndex -CandidatePaths @($pdfProtected)
            if ($pdfIdx -gt 1) {
                $pdfProtected = Get-IndexedFilePath -BasePath $pdfProtected -Index $pdfIdx
                Assert-SafeOutputPath -TargetPath $pdfProtected -Label '-OutPdfPath'
                Write-Output ("Output collision avoided; auto-numbered -> {0}" -f $pdfProtected)
            }
        }
    }

    $destDir = Split-Path $dest -Parent
    if ($destDir -and -not (Test-Path -LiteralPath $destDir -PathType Container)) {
        [void][System.IO.Directory]::CreateDirectory($destDir)
    }
    [System.IO.File]::WriteAllText($dest, $updated, (New-Object System.Text.UTF8Encoding($false)))
    $sz = (Get-Item -LiteralPath $dest).Length
    if ($stats.Total -gt 0) {
        $savedKb = [Math]::Round(($stats.OrigBytes - $stats.FinalBytes) / 1024.0, 1)
        Write-Output ("Optimized {0}/{1} images (Quality={2}%, saved {3:N1} KB raw)" -f $stats.Compressed, $stats.Total, $Quality, $savedKb)
    }
    if ($PreserveLayoutMode) {
        Write-Output "PreserveLayout mode: skipped reader shell injection"
    } elseif ($shellInjected.Count -gt 0) {
        Write-Output ("Injected reader shell -> {0}" -f ($shellInjected -join ', '))
    } else {
        Write-Output "Reader shell already present (skipped injection)"
    }
    Write-Output ("Embedded images into HTML -> {0} ({1:N0} bytes)" -f $dest, $sz)
    if ($wantPdf) {
        Invoke-HtmlToPdf -InHtml $dest -OutPdf $pdfProtected -TimeoutSeconds $TimeoutSeconds
    }
    if ($CleanTargetDir) {
        Invoke-SafeCleanDir -TargetDir $CleanTargetDir -ProtectedPaths @($dest, $pdfProtected)
    }
}

switch ($Action) {
    'EmbedImages' { Invoke-EmbedImages -InHtml $HtmlPath -OutHtml $OutHtmlPath -OutPdf $OutPdfPath -ExportPdf ([bool]$AlsoPdf) -PreserveLayoutMode ([bool]$PreserveLayout) -Quality $JpegQuality -MaxWidth $MaxImageWidth -CleanTargetDir $CleanDir -TimeoutSeconds $PdfTimeoutSeconds }
    'HtmlToPdf'   { Invoke-HtmlToPdf -InHtml $HtmlPath -OutPdf $OutPdfPath -CleanTargetDir $CleanDir -TimeoutSeconds $PdfTimeoutSeconds }
}
