$ErrorActionPreference = 'Stop'
$appPath = Join-Path $PSScriptRoot 'GTA6Wallpaper.exe'
if (-not (Test-Path -LiteralPath $appPath)) { throw '请先解压完整文件夹。' }
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktopPath 'GTA VI 倒计时壁纸.lnk'
$taskShell = New-Object -ComObject WScript.Shell
$shortcut = $taskShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $appPath
$shortcut.Arguments = '--preview'
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.IconLocation = "$appPath,0"
$shortcut.Description = 'GTA VI 4K 原画 · 北京时间发售倒计时'
$shortcut.Save()
Write-Host "已创建：$shortcutPath"
