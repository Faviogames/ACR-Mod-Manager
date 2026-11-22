$ErrorActionPreference = 'Stop'
$managerRoot = $PSScriptRoot
$release = Get-Content -LiteralPath (Join-Path $managerRoot 'app_release.json') -Raw | ConvertFrom-Json
$appVersion = $release.version
if ($appVersion -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid release version' }
dotnet publish (Join-Path $managerRoot 'desktop/ContentManager.csproj') -c Release -r win-x64 --self-contained true "-p:Version=$appVersion" -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:DebugType=None --configfile (Join-Path $managerRoot 'desktop/NuGet.Config') -o (Join-Path $managerRoot 'desktop-next')
if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed' }
& (Join-Path $managerRoot 'python/python.exe') (Join-Path $managerRoot 'build_payload.py')
if ($LASTEXITCODE -ne 0) { throw 'Payload build failed' }
dotnet publish (Join-Path $managerRoot 'installer/Installer.csproj') -c Release -r win-x64 --self-contained true "-p:Version=$appVersion" -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:DebugType=None --configfile (Join-Path $managerRoot 'desktop/NuGet.Config') -o (Join-Path $managerRoot 'dist/setup')
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
$installerPath = Join-Path $managerRoot 'dist/ACR-Mod-Manager-Setup.exe'
Copy-Item -LiteralPath (Join-Path $managerRoot 'dist/setup/ACR-Mod-Manager-Setup.exe') -Destination $installerPath -Force
$installerHash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
"$installerHash  ACR-Mod-Manager-Setup.exe" | Set-Content -LiteralPath (Join-Path $managerRoot 'dist/SHA256SUMS.txt') -Encoding ascii
Write-Output "Built ACR Mod Manager $appVersion : $installerHash"
