<#
.SYNOPSIS
  Helper script to update traits defined by yaml files.

.DESCRIPTION
  This script will take all yaml files in client/ayon_core/pipeline/traits and
  generate python files from them. The generated files will be placed in
  client/ayon_core/pipeline/traits/generated.

  It expects openassetio-traitgen to be installed and available in the PATH.

.EXAMPLE

PS> .\.poetry\bin\poetry.exe run pwsh .\scripts\generate_traits.ps1

#>

$script_dir = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
$ayoncore_root = (Get-Item $script_dir).parent.FullName

Set-Location -Path $ayoncore_root

function Exit-WithCode($exitcode) {
   # Only exit this host process if it's a child of another PowerShell parent process...
   $parentPID = (Get-CimInstance -ClassName Win32_Process -Filter "ProcessId=$PID" | Select-Object -Property ParentProcessId).ParentProcessId
   $parentProcName = (Get-CimInstance -ClassName Win32_Process -Filter "ProcessId=$parentPID" | Select-Object -Property Name).Name
   if ('powershell.exe' -eq $parentProcName) { $host.SetShouldExit($exitcode) }

   exit $exitcode
}

function New-TemporaryDirectory {
    $parent = [System.IO.Path]::GetTempPath()
    [string] $name = [System.Guid]::NewGuid()
    New-Item -ItemType Directory -Path (Join-Path $parent $name)
}

$art = @"

                    ▄██▄
         ▄███▄ ▀██▄ ▀██▀ ▄██▀ ▄██▀▀▀██▄    ▀███▄      █▄
        ▄▄ ▀██▄  ▀██▄  ▄██▀ ██▀      ▀██▄  ▄  ▀██▄    ███
       ▄██▀  ██▄   ▀ ▄▄ ▀  ██         ▄██  ███  ▀██▄  ███
      ▄██▀    ▀██▄   ██    ▀██▄      ▄██▀  ███    ▀██ ▀█▀
     ▄██▀      ▀██▄  ▀█      ▀██▄▄▄▄██▀    █▀      ▀██▄

     ·  · - =[ by YNPUT ]:[ http://ayon.ynput.io ]= - ·  ·

"@

function Get-AsciiArt() {
    Write-Host $art -ForegroundColor DarkGreen
}

Get-AsciiArt

$temp_traits = New-TemporaryDirectory
Write-Host ">>> Generating traits ..."
Write-Host ">>> Temporary directory: $($temp_traits)"

$directoryPath = "$($ayoncore_root)\client\ayon_core\pipeline\traits"

Write-Host ">>> Cleaning generated traits ..."
try {
    Remove-Item -Recurse -Force "$($directoryPath)\generated\*"
}
catch {
    Write-Host "!!! Cannot clean generated Traits director."
    Write-Host $_.Exception.Message -Color Red
    Exit-WithCode 1
}

Get-ChildItem -Path $directoryPath -Filter "*.yml" | ForEach-Object {
    Write-Host "  - Generating from [ $($_.FullName)  ]"
    & openassetio-traitgen -o $temp_traits -g python -v $_.FullName
    $content = Get-Content $_.FullName
    Write-Output $content
}

Write-Host ">>> Moving traits to repository ..."
Move-Item -Path $temp_traits\* -Destination "$($directoryPath)\generated" -Force
# Get all subdirectories
$subDirs = Get-ChildItem -Path "$($directoryPath)\generated" -Directory
$initContent = ""
$allSubmodules = ""
# Loop through each subdirectory
foreach ($subDir in $subDirs) {
    # Extract the directory name
    $moduleName = $subDir.Name

    # Add the import statement to the content
    $initContent += "from . import $moduleName`n"
    $allSubmodules += "    $($subDir.Name),`n"
}
$initContent += "`n`n__all__ = [`n$allSubmodules]`n"

Write-Host ">>> Writing index ..."
$initContent | Out-File -FilePath "$directoryPath\generated\__init__.py" -Encoding utf8 -Force

Write-Host ">>> Traits generated."
