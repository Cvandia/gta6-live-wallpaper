[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$version = '1.4.0'
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw '请先安装 uv：https://docs.astral.sh/uv/getting-started/installation/'
    }
    foreach ($requiredPath in @('uv.lock', 'src/main.py', 'assets/background.jpg', 'assets/icon.ico', 'web/index.html', 'tools/prepare_web.py', 'README.md', 'LICENSE.txt', 'Licenses')) {
        if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $requiredPath))) {
            throw "缺少项目文件：$requiredPath"
        }
    }
    $env:UV_CACHE_DIR = Join-Path $projectRoot '.uv-cache'
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $projectRoot '.pyinstaller-cache'
    uv sync --locked --group build
    if ($LASTEXITCODE -ne 0) { throw 'uv 同步依赖失败' }
    uv run --frozen --group build python tools/prepare_web.py
    if ($LASTEXITCODE -ne 0) { throw '网页素材准备失败' }

    $assetsPath = Join-Path $projectRoot 'assets'
    $sourcePath = Join-Path $projectRoot 'src'
    $distPath = Join-Path $projectRoot 'dist'
    $buildPath = Join-Path $projectRoot 'build'
    New-Item -ItemType Directory -Path $distPath, $buildPath -Force | Out-Null
    $pyInstallerArguments = @(
        'run', '--frozen', '--group', 'build', 'python', '-m', 'PyInstaller',
        '--noconfirm', '--clean', '--windowed', '--onefile',
        '--name', 'GTA6Wallpaper',
        '--icon', (Join-Path $assetsPath 'icon.ico'),
        '--add-data', ($assetsPath + ';assets'),
        '--paths', $sourcePath,
        '--distpath', $distPath,
        '--workpath', (Join-Path $buildPath 'pyinstaller'),
        '--specpath', $buildPath,
        (Join-Path $sourcePath 'main.py')
    )
    & uv @pyInstallerArguments
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 打包失败' }

    # 每次使用独立暂存目录，避免把先前构建遗留文件带进发布包。
    $stagingPath = Join-Path $buildPath ('package-' + [guid]::NewGuid().ToString('N'))
    $bundlePath = Join-Path $stagingPath 'GTA6-LiveWallpaper'
    $webPackagePath = Join-Path $bundlePath 'WallpaperEngine-Web'
    New-Item -ItemType Directory -Path $bundlePath -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $distPath 'GTA6Wallpaper.exe') -Destination $bundlePath
    Copy-Item -LiteralPath (Join-Path $projectRoot 'web') -Destination $webPackagePath -Recurse
    foreach ($documentName in @('README.md', 'RELEASE_NOTES.md', 'LICENSE.txt', 'Licenses', 'docs', 'project.json', 'preview.jpg', '创建桌面快捷方式.ps1')) {
        $documentSource = Join-Path $projectRoot $documentName
        if (Test-Path -LiteralPath $documentSource) {
            Copy-Item -LiteralPath $documentSource -Destination $bundlePath -Recurse -Force
        }
    }
    if (Test-Path -LiteralPath (Join-Path $assetsPath 'sources.json')) {
        Copy-Item -LiteralPath (Join-Path $assetsPath 'sources.json') -Destination $bundlePath
    }
    Copy-Item -LiteralPath (Join-Path $projectRoot 'LICENSE.txt') -Destination $webPackagePath -Force
    Copy-Item -LiteralPath (Join-Path $projectRoot 'Licenses') -Destination $webPackagePath -Recurse -Force
    $fullZipPath = Join-Path $distPath "GTA6-LiveWallpaper-v$version.zip"
    $webZipPath = Join-Path $distPath "GTA6-WallpaperEngine-Web-v$version.zip"
    Compress-Archive -LiteralPath $bundlePath -DestinationPath $fullZipPath -Force
    Compress-Archive -LiteralPath $webPackagePath -DestinationPath $webZipPath -Force
    Write-Host "EXE：$(Join-Path $distPath 'GTA6Wallpaper.exe')"
    Write-Host "完整包：$fullZipPath"
    Write-Host "Web 包：$webZipPath"
} finally {
    Pop-Location
}
