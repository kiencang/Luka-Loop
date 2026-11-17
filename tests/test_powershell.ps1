<#
.SYNOPSIS
    Zero-dependency Windows PowerShell 5.1 unit & integration test suite for luka-loop tools\.
.DESCRIPTION
    Tests tools\_path_guards.ps1, tools\extract_pdf_assets.ps1 (plus extract_assets.exe),
    tools\pdf_fallback_tools.ps1, and tools\html_packager.ps1 without requiring system Python or Pester.
#>
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$repoRoot = Split-Path $PSScriptRoot -Parent
$toolsDir = Join-Path $repoRoot 'tools'
$script:Passed = 0
$script:Failed = 0

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "Assertion failed: $Message" }
}

function Assert-Equal {
    param($Expected, $Actual, [string]$Message)
    if ($Expected -ne $Actual) {
        throw "Assertion failed ($Message): expected [$Expected], got [$Actual]"
    }
}

function Assert-Throws {
    param([scriptblock]$Action, [string]$ExpectedPattern = '', [string]$Message = 'Expected exception')
    $threw = $false
    $errMsg = ''
    try {
        & $Action
    } catch {
        $threw = $true
        $errMsg = $_.Exception.Message
    }
    if (-not $threw) { throw "Assertion failed ($Message): no exception thrown" }
    if ($ExpectedPattern -and ($errMsg -notmatch $ExpectedPattern)) {
        throw "Assertion failed ($Message): error '$errMsg' did not match '$ExpectedPattern'"
    }
}

function Invoke-TestCase {
    param([string]$Name, [scriptblock]$Body)
    try {
        & $Body
        $script:Passed++
        Write-Output ("[PASS] {0}" -f $Name)
    } catch {
        $script:Failed++
        Write-Output ("[FAIL] {0} -> {1}" -f $Name, $_.Exception.Message)
    }
}

function New-MinimalVectorPdf {
    <# Creates a valid 1-page PDF 1.4 containing a filled vector box and a Figure 1 caption (pure ASCII, no Python). #>
    param(
        [string]$OutPath,
        [string]$Caption = 'Figure 1: Sample vector diagram for testing'
    )
    $safeCap = $Caption.Replace('\', '\\').Replace('(', '\(').Replace(')', '\)')
    $streamBody = "0.2 0.4 0.8 rg 0 0 0 RG 1 w 70 590 220 140 re B`nBT /F1 12 Tf 70 565 Td ($safeCap) Tj ET`n"
    $streamBytesLen = [System.Text.Encoding]::ASCII.GetByteCount($streamBody)

    $objs = @(
        "1 0 obj`n<< /Type /Catalog /Pages 2 0 R >>`nendobj`n",
        "2 0 obj`n<< /Type /Pages /Kids [3 0 R] /Count 1 >>`nendobj`n",
        "3 0 obj`n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>`nendobj`n",
        "4 0 obj`n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>`nendobj`n",
        "5 0 obj`n<< /Length $streamBytesLen >>`nstream`n$streamBody`nendstream`nendobj`n"
    )

    $sb = New-Object System.Text.StringBuilder
    [void]$sb.Append("%PDF-1.4`n")
    $offsets = New-Object 'System.Collections.Generic.List[int]'
    foreach ($o in $objs) {
        [void]$offsets.Add([System.Text.Encoding]::ASCII.GetByteCount($sb.ToString()))
        [void]$sb.Append($o)
    }
    $xrefOffset = [System.Text.Encoding]::ASCII.GetByteCount($sb.ToString())
    [void]$sb.Append("xref`n0 $($objs.Count + 1)`n0000000000 65535 f `n")
    foreach ($off in $offsets) {
        [void]$sb.Append(("{0:D10} 00000 n `n" -f $off))
    }
    [void]$sb.Append("trailer`n<< /Size $($objs.Count + 1) /Root 1 0 R >>`nstartxref`n$xrefOffset`n%%EOF`n")
    [System.IO.File]::WriteAllText($OutPath, $sb.ToString(), [System.Text.Encoding]::ASCII)
}

function Invoke-CliPs1 {
    param([string]$ScriptPath, [string[]]$CliArgs)
    $allArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ScriptPath) + $CliArgs
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = (& powershell.exe @allArgs 2>&1 | Out-String)
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEap
    }
    return @{ ExitCode = $code; Output = $out }
}

function Find-LocalBrowser {
    foreach ($pair in @(
        @(${env:ProgramFiles(x86)}, 'Microsoft\Edge\Application\msedge.exe'),
        @($env:ProgramFiles,        'Microsoft\Edge\Application\msedge.exe'),
        @($env:LocalAppData,        'Microsoft\Edge\Application\msedge.exe'),
        @($env:ProgramFiles,        'Google\Chrome\Application\chrome.exe'),
        @(${env:ProgramFiles(x86)}, 'Google\Chrome\Application\chrome.exe'),
        @($env:LocalAppData,        'Google\Chrome\Application\chrome.exe')
    )) {
        if ($pair[0] -and (Test-Path -LiteralPath (Join-Path $pair[0] $pair[1]) -PathType Leaf)) {
            return (Join-Path $pair[0] $pair[1])
        }
    }
    return $null
}

. (Join-Path $toolsDir '_path_guards.ps1')

$tmpRoot = Join-Path $env:TEMP ('luka_ps_suite_' + [guid]::NewGuid().ToString('N'))
[void][System.IO.Directory]::CreateDirectory($tmpRoot)

try {
    Invoke-TestCase 'AST syntax check for all tools\ and tests\ PowerShell scripts' {
        $psFiles = @(Get-ChildItem -LiteralPath $toolsDir -Filter '*.ps1' -File) + @(Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.ps1' -File)
        foreach ($f in $psFiles) {
            $tokens = $null; $errs = $null
            [void][System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$tokens, [ref]$errs)
            Assert-Equal 0 $errs.Count "Syntax errors in $($f.Name)"
        }
    }

    Invoke-TestCase 'Assert-LocalNoUncPath blocks UNC/network prefixes and allows local paths' {
        foreach ($bad in @('\\server\share\a.pdf', '//server/share/a.pdf', 'file://server/share/a.pdf', 'FileSystem::\\server\share')) {
            Assert-Throws { Assert-LocalNoUncPath -PathValue $bad -ParamName 'Test' } 'Refusing UNC' "Should block $bad"
        }
        Assert-LocalNoUncPath -PathValue 'C:\Users\Test\doc.pdf' -ParamName 'Test'
        Assert-LocalNoUncPath -PathValue 'work\assets' -ParamName 'Test'
    }

    Invoke-TestCase 'Test-IsReparsePoint and Assert-SafeOutputPath block junctions (including broken junctions)' {
        $sub = Join-Path $tmpRoot 'junc_case'
        [void][System.IO.Directory]::CreateDirectory($sub)
        $real = Join-Path $sub 'real'
        $junc = Join-Path $sub 'junc'
        [void][System.IO.Directory]::CreateDirectory($real)
        cmd /c mklink /J "`"$junc`"" "`"$real`"" | Out-Null
        try {
            $realItem = Get-Item -LiteralPath $real -Force
            $juncItem = Get-Item -LiteralPath $junc -Force
            Assert-True (-not (Test-IsReparsePoint -Item $realItem)) 'Normal folder should not be flagged'
            Assert-True (Test-IsReparsePoint -Item $juncItem) 'Active junction should be flagged'
            Assert-Throws { Assert-SafeOutputPath -TargetPath (Join-Path $junc 'out.html') -Label 'TestOut' } 'symlink/junction' 'Should block write through junction'

            Remove-Item -LiteralPath $real -Force
            $brokenItem = Get-Item -LiteralPath $junc -Force
            Assert-True (Test-IsReparsePoint -Item $brokenItem) 'Broken junction should still be flagged'
        } finally {
            if (Test-Path -LiteralPath $junc) { cmd /c rmdir "`"$junc`"" | Out-Null }
        }
    }

    Invoke-TestCase 'Test-HasCloudPlaceholderFiles detects Offline attribute without false positives' {
        Assert-True (-not (Test-HasCloudPlaceholderFiles -DirectoryPath (Join-Path $toolsDir 'extract_assets'))) 'tools\extract_assets should have 0 placeholders'
        $cdir = Join-Path $tmpRoot 'cloud_placeholder'
        [void][System.IO.Directory]::CreateDirectory($cdir)
        $cfile = Join-Path $cdir 'dummy.dll'
        [System.IO.File]::WriteAllText($cfile, 'x')
        $fi = Get-Item -LiteralPath $cfile -Force
        $fi.Attributes = $fi.Attributes -bor [System.IO.FileAttributes]::Offline
        try {
            Assert-True (Test-HasCloudPlaceholderFiles -DirectoryPath $cdir) 'Should detect Offline file attribute'
        } finally {
            $fi.Attributes = $fi.Attributes -band (-bnot [System.IO.FileAttributes]::Offline)
        }
    }

    $viDocName = "T$([char]0x00E0)i li$([char]0x1EC7)u m$([char]0x1EAB)u.pdf"
    $viAssetsSub = "Th$([char]0x01B0) m$([char]0x1EE5)c $([char]0x1EA3)nh\assets1"
    $samplePdf = Join-Path $tmpRoot $viDocName
    New-MinimalVectorPdf -OutPath $samplePdf -Caption 'Figure 1: Minimal vector box with a long enough caption to test word compaction limit'

    Invoke-TestCase 'extract_pdf_assets.ps1 handles -PdfPath, Vietnamese paths, word compaction, and size limit' {
        $extractPs1 = Join-Path $toolsDir 'extract_pdf_assets.ps1'
        $outAssets = Join-Path $tmpRoot $viAssetsSub
        $r1 = Invoke-CliPs1 $extractPs1 @('-PdfPath', $samplePdf, '-OutDir', $outAssets, '-Meta', '-MaxMetaWords', '4')
        Assert-Equal 0 $r1.ExitCode "extract_pdf_assets failed: $($r1.Output)"
        Assert-True ($r1.Output -match 'Resolved PDF ->') 'Missing Resolved PDF output'
        Assert-True ($r1.Output -match 'Extracted 1 figures') "Expected 1 figure, got: $($r1.Output)"
        Assert-True ($r1.Output -match '=== MANIFEST JSON START ===') 'Missing manifest block'
        Assert-True ($r1.Output -match '"caption":\s*"Figure 1: Minimal vector\.\.\."') "Expected 4-word truncated caption in stdout: $($r1.Output)"

        $manifestOnDisk = Get-Content (Join-Path $outAssets 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        Assert-Equal 1 $manifestOnDisk.figures.Count 'manifest figure count'
        Assert-True ($manifestOnDisk.figures[0].caption -match 'word compaction limit$') 'Full caption must remain on disk'

        $rLimit = Invoke-CliPs1 $extractPs1 @('-PdfPath', $samplePdf, '-OutDir', $outAssets, '-Meta', '-MaxMetaBytes', '40')
        Assert-Equal 0 $rLimit.ExitCode "extract_pdf_assets limit failed: $($rLimit.Output)"
        Assert-True ($rLimit.Output -match 'Manifest too large for stdout') 'Should report manifest exceeds byte limit'
    }

    Invoke-TestCase 'extract_pdf_assets.ps1 resolves -TranscriptPath by application/pdf mime_type without .pdf extension' {
        $extractPs1 = Join-Path $toolsDir 'extract_pdf_assets.ps1'
        $blobPdf = Join-Path $tmpRoot 'attachment_blob_noext'
        Copy-Item -LiteralPath $samplePdf -Destination $blobPdf -Force
        $transcript = Join-Path $tmpRoot 'transcript.jsonl'
        $uriEsc = $blobPdf.Replace('\', '\\')
        $line = '{"type":"USER_INPUT","media":[{"mime_type":"application/pdf","uri":"' + $uriEsc + '"}]}'
        [System.IO.File]::WriteAllText($transcript, $line + "`n", (New-Object System.Text.UTF8Encoding($false)))

        $outAssets = Join-Path $tmpRoot 'assets_transcript'
        $r = Invoke-CliPs1 $extractPs1 @('-TranscriptPath', $transcript, '-OutDir', $outAssets, '-Meta')
        Assert-Equal 0 $r.ExitCode "Transcript extraction failed: $($r.Output)"
        Assert-True ($r.Output -match 'Extracted 1 figures') "Expected 1 figure via transcript: $($r.Output)"
    }

    Invoke-TestCase 'pdf_fallback_tools.ps1 RenderPages, CropFromJson, non-locking overwrite, and input validation' {
        $fbPs1 = Join-Path $toolsDir 'pdf_fallback_tools.ps1'
        $fbDir = Join-Path $tmpRoot 'fallback_work'
        $pagesDir = Join-Path $fbDir 'pages'
        $cropsDir = Join-Path $fbDir 'crops'

        $rRender = Invoke-CliPs1 $fbPs1 @('-Action', 'RenderPages', '-PdfPath', $samplePdf, '-OutDir', $pagesDir, '-Scale', '1.5')
        Assert-Equal 0 $rRender.ExitCode "RenderPages failed: $($rRender.Output)"
        $page1 = Join-Path $pagesDir 'page_1.png'
        Assert-True (Test-Path -LiteralPath $page1 -PathType Leaf) 'page_1.png not rendered'

        $specOk = Join-Path $fbDir 'crop_ok.json'
        $specData = @(
            @{ page_png = $page1; box = @(0.05, 0.10, 0.60, 0.40); out_name = 'fig_trim.png'; auto_trim = $true },
            @{ page_png = $page1; box = @(0.05, 0.10, 0.60, 0.40); out_name = 'fig_raw.png'; auto_trim = $false }
        ) | ConvertTo-Json
        [System.IO.File]::WriteAllText($specOk, $specData, (New-Object System.Text.UTF8Encoding($false)))
        $rCrop = Invoke-CliPs1 $fbPs1 @('-Action', 'CropFromJson', '-SpecJson', $specOk, '-OutDir', $cropsDir)
        Assert-Equal 0 $rCrop.ExitCode "CropFromJson failed: $($rCrop.Output)"
        Assert-True (Test-Path -LiteralPath (Join-Path $cropsDir 'fig_trim.png')) 'fig_trim.png missing'
        Assert-True (Test-Path -LiteralPath (Join-Path $cropsDir 'fig_raw.png')) 'fig_raw.png missing'

        # Non-locking overwrite of source image inside cropsDir
        $specOverwrite = Join-Path $fbDir 'crop_overwrite.json'
        $ovData = @(@{ page_png = (Join-Path $cropsDir 'fig_raw.png'); box = @(0.1, 0.1, 0.9, 0.9); out_name = 'fig_raw.png'; auto_trim = $false }) | ConvertTo-Json
        [System.IO.File]::WriteAllText($specOverwrite, $ovData, (New-Object System.Text.UTF8Encoding($false)))
        $rOv = Invoke-CliPs1 $fbPs1 @('-Action', 'CropFromJson', '-SpecJson', $specOverwrite, '-OutDir', $cropsDir)
        Assert-Equal 0 $rOv.ExitCode "Non-locking crop overwrite failed: $($rOv.Output)"

        # Security/validation rejections
        foreach ($badSpec in @(
            @{ label = 'traversal out_name'; obj = @(@{ page_png = $page1; box = @(0.1, 0.1, 0.5, 0.5); out_name = '..\bad.png' }); pattern = 'Path traversal blocked' },
            @{ label = 'outside page_png'; obj = @(@{ page_png = 'C:\Windows\System32\calc.exe'; box = @(0.1, 0.1, 0.5, 0.5); out_name = 'ok.png' }); pattern = 'Path traversal blocked' },
            @{ label = 'invalid box coords'; obj = @(@{ page_png = $page1; box = @(0.6, 0.1, 0.5, 0.5); out_name = 'ok.png' }); pattern = 'Invalid crop box' }
        )) {
            $badFile = Join-Path $fbDir 'bad_crop.json'
            [System.IO.File]::WriteAllText($badFile, ($badSpec.obj | ConvertTo-Json), (New-Object System.Text.UTF8Encoding($false)))
            $rBad = Invoke-CliPs1 $fbPs1 @('-Action', 'CropFromJson', '-SpecJson', $badFile, '-OutDir', $cropsDir)
            Assert-True ($rBad.ExitCode -ne 0 -and $rBad.Output -match $badSpec.pattern) "$($badSpec.label): expected '$($badSpec.pattern)', got $($rBad.Output)"
        }
    }

    Invoke-TestCase 'html_packager.ps1 Auto-QA catches failures and passes valid HTML (single quotes + code blocks + MathJax)' {
        $packPs1 = Join-Path $toolsDir 'html_packager.ps1'
        $qaDir = Join-Path $tmpRoot 'qa_cases'
        [void][System.IO.Directory]::CreateDirectory($qaDir)

        # Create an opaque 240x160 noisy photo PNG (large lossless PNG -> compresses smaller as JPEG) & a 60x60 transparent PNG
        Add-Type -AssemblyName System.Drawing
        $photoPng = Join-Path $qaDir 'photo.png'
        $bmp = New-Object System.Drawing.Bitmap(240, 160, [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
        $bRect = New-Object System.Drawing.Rectangle(0, 0, 240, 160)
        $bData = $bmp.LockBits($bRect, [System.Drawing.Imaging.ImageLockMode]::WriteOnly, [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
        try {
            $byteCount = [Math]::Abs($bData.Stride) * 160
            $pxBytes = New-Object byte[] $byteCount
            (New-Object System.Random(42)).NextBytes($pxBytes)
            [System.Runtime.InteropServices.Marshal]::Copy($pxBytes, 0, $bData.Scan0, $byteCount)
        } finally {
            $bmp.UnlockBits($bData)
        }
        $bmp.Save($photoPng, [System.Drawing.Imaging.ImageFormat]::Png)
        $bmp.Dispose()

        $alphaPng = Join-Path $qaDir 'alpha.png'
        $abmp = New-Object System.Drawing.Bitmap(60, 60)
        $abmp.SetPixel(10, 10, [System.Drawing.Color]::FromArgb(120, 10, 20, 30))
        $abmp.Save($alphaPng, [System.Drawing.Imaging.ImageFormat]::Png)
        $abmp.Dispose()

        # Passing HTML with single quotes, <pre><code> LaTeX-like text, table-wrapper, and both images
        $goodIn = Join-Path $qaDir 'good.html'
        $goodOut = Join-Path $qaDir 'good_out.html'
        $goodHtml = @'
<!DOCTYPE html>
<html><head><title>QA</title></head>
<body>
<header><h1 id='top'>Tieu de</h1></header>
<p><a href='#top'>Dau trang</a></p>
<pre><code>grep '\(foo\|bar\)' \\[host]\share</code></pre>
<p>Inline code <code>\[0-9\]</code></p>
<div class='table-wrapper'><table><thead><tr><th>A</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table></div>
<figure><img src='photo.png' alt='Anh mau'><figcaption>Hinh 1</figcaption></figure>
<figure><img src='alpha.png' alt='Anh trong suot'><figcaption>Hinh 2</figcaption></figure>
</body></html>
'@
        [System.IO.File]::WriteAllText($goodIn, $goodHtml, (New-Object System.Text.UTF8Encoding($false)))
        $rGood = Invoke-CliPs1 $packPs1 @('-Action', 'EmbedImages', '-HtmlPath', $goodIn, '-OutHtmlPath', $goodOut, '-MaxImageWidth', '200')
        Assert-Equal 0 $rGood.ExitCode "Good HTML failed: $($rGood.Output)"
        Assert-True ($rGood.Output -match '\[QA PASS\] Base64 images: 2 \| Tables wrapped: 1/1') "Unexpected QA pass output: $($rGood.Output)"
        Assert-True ($rGood.Output -match 'Injected reader shell -> CSS, Toolbar, Script') 'Expected shell injection'
        $outText = [System.IO.File]::ReadAllText($goodOut, [System.Text.Encoding]::UTF8)
        Assert-True ($outText -match 'data:image/jpeg;base64,') 'Expected rich photo resized/compressed to JPEG'
        Assert-True ($outText -match 'data:image/png;base64,') 'Expected transparent PNG preserved as PNG'

        # Idempotent re-injection check
        $goodOut2 = Join-Path $qaDir 'good_out2.html'
        $rIdemp = Invoke-CliPs1 $packPs1 @('-Action', 'EmbedImages', '-HtmlPath', $goodOut, '-OutHtmlPath', $goodOut2)
        Assert-Equal 0 $rIdemp.ExitCode "Idempotent pack failed: $($rIdemp.Output)"
        Assert-True ($rIdemp.Output -match 'Reader shell already present \(skipped injection\)') "Expected skipped injection: $($rIdemp.Output)"

        # Real LaTeX with MathJax <script> passes
        $mathOk = Join-Path $qaDir 'math_ok.html'
        [System.IO.File]::WriteAllText($mathOk, '<!DOCTYPE html><html><head><script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script></head><body><p>Formula \(a+b\)</p></body></html>', (New-Object System.Text.UTF8Encoding($false)))
        $rMath = Invoke-CliPs1 $packPs1 @('-Action', 'EmbedImages', '-HtmlPath', $mathOk, '-OutHtmlPath', (Join-Path $qaDir 'math_out.html'))
        Assert-Equal 0 $rMath.ExitCode "MathJax HTML failed: $($rMath.Output)"

        # Negative QA cases
        foreach ($neg in @(
            @{ name = 'missing alt'; html = '<!DOCTYPE html><html><head></head><body><img src="photo.png"></body></html>'; pat = 'missing alt attribute' },
            @{ name = 'unembedded img'; html = '<!DOCTYPE html><html><head></head><body><img src="missing.png" alt="x"></body></html>'; pat = 'un-embedded local' },
            @{ name = 'unwrapped table'; html = '<!DOCTYPE html><html><head></head><body><table><tr><td>1</td></tr></table></body></html>'; pat = 'table-wrapper container' },
            @{ name = 'broken anchor'; html = '<!DOCTYPE html><html><head></head><body><a href="#nope">Link</a></body></html>'; pat = 'Broken internal anchor' },
            @{ name = 'latex no mathjax'; html = '<!DOCTYPE html><html><head></head><body><p>Value \(x\)</p></body></html>'; pat = 'Detected LaTeX math delimiters' }
        )) {
            $negFile = Join-Path $qaDir 'neg.html'
            [System.IO.File]::WriteAllText($negFile, $neg.html, (New-Object System.Text.UTF8Encoding($false)))
            $rNeg = Invoke-CliPs1 $packPs1 @('-Action', 'EmbedImages', '-HtmlPath', $negFile, '-OutHtmlPath', (Join-Path $qaDir 'neg_out.html'))
            Assert-True ($rNeg.ExitCode -ne 0 -and $rNeg.Output -match $neg.pat) "QA negative [$($neg.name)] expected '$($neg.pat)', got: $($rNeg.Output)"
        }
    }

    Invoke-TestCase 'html_packager.ps1 -CleanDir safety guards, lock resilience, and end-to-end -AlsoPdf' {
        $packPs1 = Join-Path $toolsDir 'html_packager.ps1'
        $extractPs1 = Join-Path $toolsDir 'extract_pdf_assets.ps1'
        $e2eDir = Join-Path $tmpRoot 'e2e_ws'
        $workDir = Join-Path $e2eDir 'work'
        $outDir = Join-Path $e2eDir 'output'
        [void][System.IO.Directory]::CreateDirectory($workDir)
        [void][System.IO.Directory]::CreateDirectory($outDir)

        Push-Location $e2eDir
        try {
            $r1 = Invoke-CliPs1 $extractPs1 @('-PdfPath', $samplePdf, '-OutDir', 'work\assets', '-Meta')
            Assert-Equal 0 $r1.ExitCode "E2E step 1 failed: $($r1.Output)"

            $draft = Join-Path $workDir 'draft.html'
            [System.IO.File]::WriteAllText($draft, '<!DOCTYPE html><html><head><title>E2E</title></head><body><h1>E2E</h1><figure><img src="assets/fig_p1_1.png" alt="Diagram"><figcaption>Figure 1</figcaption></figure></body></html>', (New-Object System.Text.UTF8Encoding($false)))

            # Refuses unsafe CleanDir outside work\
            $rUnsafe = Invoke-CliPs1 $packPs1 @('-Action', 'EmbedImages', '-HtmlPath', 'work\draft.html', '-OutHtmlPath', 'output\e2e_vi.html', '-CleanDir', 'output')
            Assert-True ($rUnsafe.ExitCode -ne 0 -and $rUnsafe.Output -match 'Refusing to clean unsafe directory') "Should refuse CleanDir output: $($rUnsafe.Output)"

            # Full packaging with -AlsoPdf and -CleanDir work
            $rOk = Invoke-CliPs1 $packPs1 @('-Action', 'EmbedImages', '-HtmlPath', 'work\draft.html', '-OutHtmlPath', 'output\e2e_vi.html', '-AlsoPdf', '-CleanDir', 'work')
            Assert-Equal 0 $rOk.ExitCode "E2E step 4 failed: $($rOk.Output)"
            Assert-True (Test-Path -LiteralPath (Join-Path $outDir 'e2e_vi.html') -PathType Leaf) 'e2e_vi.html missing'
            Assert-True (-not (Test-Path -LiteralPath $workDir)) 'work\ should be cleaned after success'
            if (Find-LocalBrowser) {
                Assert-True (Test-Path -LiteralPath (Join-Path $outDir 'e2e_vi.pdf') -PathType Leaf) 'e2e_vi.pdf missing despite browser installed'
            }

            # Lock resilience when work\ holds a locked file
            [void][System.IO.Directory]::CreateDirectory($workDir)
            $draft2 = Join-Path $workDir 'draft.html'
            [System.IO.File]::WriteAllText($draft2, '<!DOCTYPE html><html><head><title>Lock</title></head><body><h1>Lock</h1></body></html>', (New-Object System.Text.UTF8Encoding($false)))
            $fs = [System.IO.File]::Open((Join-Path $workDir 'locked.tmp'), [System.IO.FileMode]::Create, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
            try {
                $rLock = Invoke-CliPs1 $packPs1 @('-Action', 'EmbedImages', '-HtmlPath', 'work\draft.html', '-OutHtmlPath', 'output\lock_vi.html', '-CleanDir', 'work')
                Assert-Equal 0 $rLock.ExitCode "Locked work\ should warn rather than fail: $($rLock.Output)"
                Assert-True ($rLock.Output -match 'Could not fully clean temp directory') "Expected lock warning: $($rLock.Output)"
            } finally {
                $fs.Dispose()
            }
        } finally {
            Pop-Location
        }
    }

    Invoke-TestCase 'Committed fixtures (standard, pure scan, mixed scan) extract and fallback cleanly' {
        $fixDir = Join-Path $PSScriptRoot 'fixtures'
        $extractPs1 = Join-Path $toolsDir 'extract_pdf_assets.ps1'
        $fbPs1 = Join-Path $toolsDir 'pdf_fallback_tools.ps1'
        $fixOut = Join-Path $tmpRoot 'fix_verify'

        # 1. Standard 6-page multi-feature benchmark PDF
        $stdPdf = Join-Path $fixDir 'synthetic_urban_benchmark.pdf'
        $stdAssets = Join-Path $fixOut 'std'
        $rStd = Invoke-CliPs1 $extractPs1 @('-PdfPath', $stdPdf, '-OutDir', $stdAssets, '-Meta')
        Assert-Equal 0 $rStd.ExitCode "Standard fixture failed: $($rStd.Output)"
        $mStd = Get-Content (Join-Path $stdAssets 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        Assert-Equal 6 $mStd.total_pages 'Standard fixture page count'
        Assert-Equal 0 $mStd.scanned_pages.Count 'Standard fixture should have 0 scanned pages'
        Assert-Equal 8 $mStd.figures.Count 'Standard fixture should extract 8 figures (rejecting code box and Table 1)'
        Assert-True ($mStd.figures[0].caption -match '^Figure 1:') 'Fig 1 flowchart caption'
        Assert-True ($mStd.figures[1].caption -match '^Figure 2:') 'Fig 2 multipanel caption'
        Assert-True ($mStd.figures[2].caption -match '^Figure 3:') 'Fig 3 chalkboard caption'
        Assert-Equal $null $mStd.figures[3].caption 'Table 2 row 1 thumbnail should have null caption'
        Assert-Equal $null $mStd.figures[4].caption 'Table 2 row 2 thumbnail should have null caption'
        Assert-True ($mStd.figures[5].caption -match '^Figure 4:') 'Fig 4 vector chart caption'
        Assert-True ($mStd.figures[6].caption -match '^Fig\. S1:') 'Fig S1 supplementary caption'
        Assert-True ($mStd.figures[7].caption -match '^Fig\. S2:') 'Fig S2 rectification vector caption'

        # 2. Pure 2-page scanned PDF + RenderPages + CropFromJson auto_trim
        $scanPdf = Join-Path $fixDir 'synthetic_scanned_memo.pdf'
        $scanAssets = Join-Path $fixOut 'scan'
        $rScan = Invoke-CliPs1 $extractPs1 @('-PdfPath', $scanPdf, '-OutDir', $scanAssets, '-Meta')
        Assert-Equal 0 $rScan.ExitCode "Scan fixture failed: $($rScan.Output)"
        $mScan = Get-Content (Join-Path $scanAssets 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        Assert-Equal 2 $mScan.total_pages 'Scan fixture page count'
        Assert-Equal 2 $mScan.scanned_pages.Count 'Scan fixture should detect 2 scanned pages'
        Assert-Equal 0 $mScan.figures.Count 'Pure scan should yield 0 direct figures'

        $scanPages = Join-Path $fixOut 'scan_pages'
        $rFb = Invoke-CliPs1 $fbPs1 @('-Action', 'RenderPages', '-PdfPath', $scanPdf, '-OutDir', $scanPages, '-Scale', '1.5')
        Assert-Equal 0 $rFb.ExitCode "RenderPages on scan fixture failed: $($rFb.Output)"
        $p2Png = Join-Path $scanPages 'page_2.png'
        Assert-True (Test-Path -LiteralPath $p2Png -PathType Leaf) 'Scan page_2.png missing'

        $cropSpec = Join-Path $fixOut 'scan_crop.json'
        $cropData = @(@{ page_png = $p2Png; box = @(0.14, 0.16, 0.86, 0.54); out_name = 'corgi_trim.png'; auto_trim = $true }) | ConvertTo-Json
        [System.IO.File]::WriteAllText($cropSpec, $cropData, (New-Object System.Text.UTF8Encoding($false)))
        $rCrop = Invoke-CliPs1 $fbPs1 @('-Action', 'CropFromJson', '-SpecJson', $cropSpec, '-OutDir', $scanAssets)
        Assert-Equal 0 $rCrop.ExitCode "CropFromJson on scan fixture failed: $($rCrop.Output)"
        Assert-True (Test-Path -LiteralPath (Join-Path $scanAssets 'corgi_trim.png') -PathType Leaf) 'Trimmed scan figure missing'

        # 3. Mixed 3-page PDF (electronic p1 & p3, scanned p2)
        $mixPdf = Join-Path $fixDir 'synthetic_mixed_scan_report.pdf'
        $mixAssets = Join-Path $fixOut 'mix'
        $rMix = Invoke-CliPs1 $extractPs1 @('-PdfPath', $mixPdf, '-OutDir', $mixAssets, '-Meta')
        Assert-Equal 0 $rMix.ExitCode "Mixed fixture failed: $($rMix.Output)"
        $mMix = Get-Content (Join-Path $mixAssets 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        Assert-Equal 3 $mMix.total_pages 'Mixed fixture page count'
        Assert-Equal 1 $mMix.scanned_pages.Count 'Mixed fixture should flag 1 scanned page'
        Assert-Equal 2 $mMix.scanned_pages[0] 'Mixed fixture scanned page should be page 2'
        Assert-Equal 2 $mMix.figures.Count 'Mixed fixture should extract 2 digital figures (p1 & p3)'
        Assert-True ($mMix.figures[0].caption -match '^Figure 1:') 'Mixed p1 caption'
        Assert-True ($mMix.figures[1].caption -match '^Figure 3:') 'Mixed p3 caption'

        # Selective -Pages rendering on mixed PDF (render only scanned page 2, and bracketed [1, 3])
        $mixPagesScanOnly = Join-Path $fixOut 'mix_scan_only'
        $rMixP2 = Invoke-CliPs1 $fbPs1 @('-Action', 'RenderPages', '-PdfPath', $mixPdf, '-OutDir', $mixPagesScanOnly, '-Pages', '2', '-Scale', '1.2')
        Assert-Equal 0 $rMixP2.ExitCode "RenderPages -Pages 2 failed: $($rMixP2.Output)"
        Assert-True (Test-Path -LiteralPath (Join-Path $mixPagesScanOnly 'page_2.png') -PathType Leaf) 'page_2.png should be rendered'
        Assert-True (-not (Test-Path -LiteralPath (Join-Path $mixPagesScanOnly 'page_1.png'))) 'page_1.png should NOT be rendered'
        Assert-True (-not (Test-Path -LiteralPath (Join-Path $mixPagesScanOnly 'page_3.png'))) 'page_3.png should NOT be rendered'

        $mixPagesBrackets = Join-Path $fixOut 'mix_p1_p3'
        $rMixP13 = Invoke-CliPs1 $fbPs1 @('-Action', 'RenderPages', '-PdfPath', $mixPdf, '-OutDir', $mixPagesBrackets, '-Pages', '[1, 3]', '-Scale', '1.2')
        Assert-Equal 0 $rMixP13.ExitCode "RenderPages -Pages [1, 3] failed: $($rMixP13.Output)"
        Assert-True (Test-Path -LiteralPath (Join-Path $mixPagesBrackets 'page_1.png') -PathType Leaf) 'page_1.png missing'
        Assert-True (-not (Test-Path -LiteralPath (Join-Path $mixPagesBrackets 'page_2.png'))) 'page_2.png should NOT be rendered'
        Assert-True (Test-Path -LiteralPath (Join-Path $mixPagesBrackets 'page_3.png') -PathType Leaf) 'page_3.png missing'

        foreach ($badPages in @('0', '99', '3-1', 'abc')) {
            $rBadPg = Invoke-CliPs1 $fbPs1 @('-Action', 'RenderPages', '-PdfPath', $mixPdf, '-OutDir', $mixPagesScanOnly, '-Pages', $badPages)
            Assert-True ($rBadPg.ExitCode -ne 0) "Invalid -Pages '$badPages' should fail"
        }
    }
} finally {
    Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Output ("=== PowerShell Suite Summary: {0} passed, {1} failed ===" -f $script:Passed, $script:Failed)
if ($script:Failed -gt 0) { exit 1 }
