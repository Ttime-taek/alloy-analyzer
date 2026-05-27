# Build frontend/dist via esbuild CLI (fallback when `vite build` crashes on this host).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Fe = Join-Path $Root "frontend"
$Eb = Join-Path $Fe "node_modules\@esbuild\win32-x64\esbuild.exe"
if (-not (Test-Path $Eb)) {
    Write-Error "esbuild.exe not found at $Eb — run scripts\fix_frontend_deps.cmd"
}
$Dist = Join-Path $Fe "dist"
$Assets = Join-Path $Dist "assets"
New-Item -ItemType Directory -Force -Path $Assets | Out-Null

Push-Location $Fe
try {
    & $Eb @(
        "src/main.jsx",
        "--bundle",
        "--minify",
        "--format=esm",
        "--platform=browser",
        "--target=es2020",
        "--jsx=automatic",
        "--loader:.jsx=jsx",
        "--loader:.css=css",
        "--outdir=dist/assets",
        "--entry-names=index-[hash]",
        "--asset-names=index-[hash]"
    )
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $js = Get-ChildItem (Join-Path $Assets "index-*.js") | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $css = Get-ChildItem (Join-Path $Assets "index-*.css") -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $js) { throw "No bundled JS in dist/assets" }

    $cssHref = if ($css) { "/assets/$($css.Name)" } else { "" }
    $html = @"
<!doctype html>
<html lang="ko">
  <head>
    <meta charset="UTF-8" />
    <title>AI 합금 분석기 (Web)</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#020617" />
    <link
      rel="stylesheet"
      href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css"
      crossorigin="anonymous"
    />
$(if ($cssHref) { "    <link rel=`"stylesheet`" crossorigin href=`"$cssHref`">" })
  </head>
  <body>
    <div id="root"></div>
    <script type="module" crossorigin src="/assets/$($js.Name)"></script>
  </body>
</html>
"@
    Set-Content -Path (Join-Path $Dist "index.html") -Value $html -Encoding UTF8

    $pub = Join-Path $Fe "public"
    if (Test-Path $pub) {
        Copy-Item -Path (Join-Path $pub "*") -Destination $Dist -Recurse -Force
    }

    # Remove stale hashed bundles from older vite/esbuild runs (keep current pair).
    Get-ChildItem $Assets -File | Where-Object {
        $_.Name -match '^index-' -and $_.Name -ne $js.Name -and (-not $css -or $_.Name -ne $css.Name)
    } | Remove-Item -Force -ErrorAction SilentlyContinue

    Write-Host "[build_frontend_esbuild] OK -> $($js.Name)$(if ($css) { ", $($css.Name)" })"
}
finally {
    Pop-Location
}
