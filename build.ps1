# Builds the plugin and deploys the whole mod folder into the game's BepInEx/plugins.
#
#   pwsh -File build.ps1              # build + package into ./dist
#   pwsh -File build.ps1 -Deploy      # build + copy straight into the game
#   pwsh -File build.ps1 -RebuildAssets   # regenerate models + icons + embeds first
#
# The asset pipeline is verified as part of the build, from both ends. The single worst
# failure this project has had is assets/ being regenerated while src/EmbeddedAssets.g.cs
# was not, which silently ships the previous models because the runtime prefers the
# embedded copy. The mirror trap is models/*.3mf being edited without -RebuildAssets,
# which leaves the whole assets/ folder stale. `-RebuildAssets` regenerates and embeds;
# a plain build refuses to proceed if either the embedded copy or the built .psmesh
# files have drifted.
#
#   pwsh -File build.ps1 -SkipAssetCheck  # bypass the check (rarely wanted)

param(
    [switch]$Deploy,
    [switch]$RebuildAssets,
    [switch]$SkipAssetCheck,
    [string]$GameRoot = "D:\SteamLibrary\steamapps\common\PEAK",
    [string]$Python = "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$name = "PlushieSwap"

function Invoke-Python([string]$script) {
    Write-Host "    python $script" -ForegroundColor DarkGray
    & $Python (Join-Path $root $script)
    if ($LASTEXITCODE -ne 0) { throw "python $script failed" }
}

# The DLL carries the SourceLink commit hash in InformationalVersion, so the deployed
# binary is never byte-identical to a build from another commit. That makes a bare
# SHA-256 useless for "which commit is deployed?", so the commit, timestamp and the
# DLL's own version string are recorded next to it as well.
#
# The commit alone is still misleading on its own: `git rev-parse HEAD` reports the last
# commit even when the working tree has uncommitted edits, so a build from a dirty tree
# would claim to be that commit while containing code that is not in it. A deployed DLL
# was audited back to a commit whose source tree did not even contain the patches it
# carried, which is exactly this failure. The tree is therefore checked, and a dirty
# build is recorded as `<sha>-dirty` with an explicit `dirty:` line.
function Get-BuildInfo([string]$dllPath) {
    $commit = "unknown"
    $dirty = $false
    try {
        $head = & git -C $root rev-parse --short HEAD 2>$null
        if ($LASTEXITCODE -eq 0 -and $head) { $commit = ($head | Select-Object -First 1).Trim() }
    } catch { }
    if ($commit -ne "unknown") {
        try {
            $status = & git -C $root status --porcelain 2>$null
            if ($LASTEXITCODE -eq 0 -and $status) { $dirty = $true }
        } catch { }
        if ($dirty) { $commit = "$commit-dirty" }
    }
    $version = "unknown"
    try {
        $version = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($dllPath).ProductVersion
    } catch { }
    return [pscustomobject]@{
        Commit     = $commit
        Dirty      = $dirty
        Version    = $version
        Sha256     = (Get-FileHash $dllPath -Algorithm SHA256).Hash
        BuiltAtUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    }
}

function Write-BuildInfoFile([string]$dir, $info) {
    $path = Join-Path $dir "buildinfo.txt"
    @(
        "commit:     $($info.Commit)"
        "dirty:      $($info.Dirty.ToString().ToLowerInvariant())"
        "version:    $($info.Version)"
        "sha256:     $($info.Sha256)"
        "built_utc:  $($info.BuiltAtUtc)"
    ) | Set-Content -LiteralPath $path -Encoding ascii
    Write-Host "    wrote $path" -ForegroundColor DarkGray
    Get-Content -LiteralPath $path | ForEach-Object { Write-Host "      $_" -ForegroundColor DarkGray }
    if ($info.Dirty) {
        Write-Host "    note: the working tree had uncommitted changes, so this DLL does" -ForegroundColor Yellow
        Write-Host "          not correspond to any single commit (recorded as -dirty)." -ForegroundColor Yellow
    }
}

if ($RebuildAssets) {
    Write-Host "=== [0/4] Rebuilding models, icons and embeds ===" -ForegroundColor Cyan
    Invoke-Python "tools\build_meshes.py"
    Invoke-Python "tools\build_icons.py"
    Invoke-Python "tools\embed_assets.py"
}

if (-not $SkipAssetCheck) {
    Write-Host "=== [1/4] Verifying assets against the source models ===" -ForegroundColor Cyan
    # verify_assets.py exits non-zero when a source 3MF changed without -RebuildAssets,
    # which is the "silently ships the previous model" trap from the other side: a plain
    # build never runs the Python pipeline.
    $out = & $Python (Join-Path $root "tools\verify_assets.py") 2>&1
    $out | ForEach-Object { Write-Host "    $_" }
    if ($LASTEXITCODE -ne 0 -or ($out -join "`n") -notmatch "ALL SOURCE MODELS MATCH THE BUILT ASSETS") {
        throw "assets/ is stale or does not match models/. Run build.ps1 -RebuildAssets."
    }

    Write-Host "=== [1/4] Verifying embedded assets match assets/ ===" -ForegroundColor Cyan
    # verify_embedded.py exits non-zero and prints MISMATCH! when a model on disk is
    # newer than the embedded copy, which is exactly the silent-stale-DLL trap.
    $out = & $Python (Join-Path $root "tools\verify_embedded.py") 2>&1
    $out | ForEach-Object { Write-Host "    $_" }
    if ($LASTEXITCODE -ne 0 -or ($out -join "`n") -notmatch "ALL EMBEDDED ASSETS VERIFIED") {
        throw "Embedded assets are out of sync with assets/. Run build.ps1 -RebuildAssets."
    }
} else {
    Write-Host "=== [1/4] Asset check SKIPPED ===" -ForegroundColor Yellow
}

Write-Host "=== [2/4] Building $name.dll ===" -ForegroundColor Cyan
& dotnet build (Join-Path $root "$name.csproj") -c Release -v minimal --nologo
if ($LASTEXITCODE -ne 0) { throw "build failed" }

$dll = Join-Path $root "bin\Release\$name.dll"
if (-not (Test-Path $dll)) { throw "missing $dll" }

Write-Host "=== [3/4] Assembling dist\$name ===" -ForegroundColor Cyan
$dist = Join-Path $root "dist\$name"
if (Test-Path (Join-Path $root "dist")) { Remove-Item (Join-Path $root "dist") -Recurse -Force }
New-Item -ItemType Directory -Path $dist -Force | Out-Null

# The model, shading and icon files are embedded in the DLL, so the mod ships as a
# single self-contained file. Dropping a same-named file next to the DLL overrides
# the embedded copy, which is how a custom model can be used without rebuilding.
Copy-Item $dll $dist

# Which commit, at what time, with which hash: the deployed folder can now be audited
# without guessing at blob timestamps.
$buildInfo = Get-BuildInfo $dll
Write-BuildInfoFile $dist $buildInfo

Get-ChildItem $dist -Recurse -File | Measure-Object -Property Length -Sum |
    ForEach-Object { Write-Host ("    {0} files, {1:N1} MB" -f $_.Count, ($_.Sum / 1MB)) }

if ($Deploy) {
    Write-Host "=== [4/4] Deploying to $GameRoot ===" -ForegroundColor Cyan
    $plugins = Join-Path $GameRoot "BepInEx\plugins"
    if (-not (Test-Path $plugins)) { throw "not a BepInEx game folder: $plugins" }
    $target = Join-Path $plugins $name
    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    Copy-Item $dist $target -Recurse

    # Prove the deployed copy is the one just built, not a stale leftover.
    $deployed = Join-Path $target "$name.dll"
    $a = $buildInfo.Sha256
    $b = (Get-FileHash $deployed -Algorithm SHA256).Hash
    if ($a -ne $b) { throw "deployed DLL hash does not match the built DLL" }
    Write-Host "    deployed to $target (sha256 $($a.Substring(0,16))..., commit $($buildInfo.Commit))" -ForegroundColor Green
} else {
    Write-Host "=== [4/4] Skipped deploy (pass -Deploy to copy into the game) ===" -ForegroundColor Yellow
}

Write-Host "Done." -ForegroundColor Green
