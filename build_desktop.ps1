param([Parameter(Mandatory=$true)][string]$PythonArchive)
$ErrorActionPreference = 'Stop'
$managerRoot = $PSScriptRoot
dotnet publish (Join-Path $managerRoot 'desktop/ContentManager.csproj') -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:DebugType=None --configfile (Join-Path $managerRoot 'desktop/NuGet.Config') -o (Join-Path $managerRoot 'desktop-bin')
if ($LASTEXITCODE -ne 0) { throw 'La ventana no se pudo compilar' }
Expand-Archive -LiteralPath $PythonArchive -DestinationPath (Join-Path $managerRoot 'python') -Force
@('python314.zip','.','..','import site') | Set-Content -LiteralPath (Join-Path $managerRoot 'python/python314._pth') -Encoding ascii
Write-Output 'Gestor compilado. retoc, UaTool y el mapa compatible deben estar en bin/.'
