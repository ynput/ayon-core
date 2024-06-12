<#
.SYNOPSIS
  Helper script to run various tasks on ayon-core addon repository.

.DESCRIPTION
  This script will detect Python installation, and build OpenPype to `build`
  directory using existing virtual environment created by Poetry (or
  by running `/tools/create_venv.ps1`). It will then shuffle dependencies in
  build folder to optimize for different Python versions (2/3) in Python host.

.EXAMPLE

PS> .\tools\manage.ps1

.EXAMPLE

To create virtual environment using Poetry:
PS> .\tools\manage.ps1 create-env

.EXAMPLE

To run Ruff check:
PS> .\tools\manage.ps1 ruff-check

.LINK
https://github.com/ynput/ayon-core

#>

# Settings and gitmodule init
$CurrentDir = Get-Location
$ScriptDir = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
$RepoRoot = (Get-Item $ScriptDir).parent.FullName
& git submodule update --init --recursive
$env:PSModulePath = $env:PSModulePath + ";$($openpype_root)\tools\modules\powershell"

$FunctionName=$ARGS[0]
$Arguments=@()
if ($ARGS.Length -gt 1) {
    $Arguments = $ARGS[1..($ARGS.Length - 1)]
}

function Exit-WithCode($exitcode) {
    # Only exit this host process if it's a child of another PowerShell parent process...
    $parentPID = (Get-CimInstance -ClassName Win32_Process -Filter "ProcessId=$PID" | Select-Object -Property ParentProcessId).ParentProcessId
    $parentProcName = (Get-CimInstance -ClassName Win32_Process -Filter "ProcessId=$parentPID" | Select-Object -Property Name).Name
    if ('powershell.exe' -eq $parentProcName) { $host.SetShouldExit($exitcode) }

    exit $exitcode
}

function Test-CommandExists {
    param (
        [Parameter(Mandatory=$true)]
        [string]$command
    )

    $commandExists = $null -ne (Get-Command $command -ErrorAction SilentlyContinue)
    return $commandExists
}

function Write-Info {
    <#
    .SYNOPSIS
        Write-Info function to write information messages.

        It uses Write-Color if that is available, otherwise falls back to Write-Host.

    #>
    [CmdletBinding()]
    param (
        [alias ('T')] [String[]]$Text,
        [alias ('C', 'ForegroundColor', 'FGC')] [ConsoleColor[]]$Color = [ConsoleColor]::White,
        [alias ('B', 'BGC')] [ConsoleColor[]]$BackGroundColor = $null,
        [alias ('Indent')][int] $StartTab = 0,
        [int] $LinesBefore = 0,
        [int] $LinesAfter = 0,
        [int] $StartSpaces = 0,
        [alias ('L')] [string] $LogFile = '',
        [Alias('DateFormat', 'TimeFormat')][string] $DateTimeFormat = 'yyyy-MM-dd HH:mm:ss',
        [alias ('LogTimeStamp')][bool] $LogTime = $true,
        [int] $LogRetry = 2,
        [ValidateSet('unknown', 'string', 'unicode', 'bigendianunicode', 'utf8', 'utf7', 'utf32', 'ascii', 'default', 'oem')][string]$Encoding = 'Unicode',
        [switch] $ShowTime,
        [switch] $NoNewLine
    )
    if (Test-CommandExists "Write-Color") {
        Write-Color -Text $Text -Color $Color -BackGroundColor $BackGroundColor -StartTab $StartTab -LinesBefore $LinesBefore -LinesAfter $LinesAfter -StartSpaces $StartSpaces -LogFile $LogFile -DateTimeFormat $DateTimeFormat -LogTime $LogTime -LogRetry $LogRetry -Encoding $Encoding -ShowTime $ShowTime -NoNewLine $NoNewLine
    } else {
        $message = $Text -join ' '
        if ($NoNewLine)
        {
            Write-Host $message -NoNewline
        }
        else
        {
            Write-Host $message
        }
    }
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

function Write-AsciiArt() {
    Write-Host $art -ForegroundColor DarkGreen
}

function Show-PSWarning() {
    if ($PSVersionTable.PSVersion.Major -lt 7) {
        Write-Info -Text "!!! ", "You are using old version of PowerShell - ",  "$($PSVersionTable.PSVersion.Major).$($PSVersionTable.PSVersion.Minor)" -Color Red, Yellow, White
        Write-Info -Text "    Please update to at least 7.0 - ", "https://github.com/PowerShell/PowerShell/releases" -Color Yellow, White
        Exit-WithCode 1
    }
}

function Install-Poetry() {
    Write-Info -Text ">>> ", "Installing Poetry ... " -Color Green, Gray
    $python = "python"
    if (Get-Command "pyenv" -ErrorAction SilentlyContinue) {
        if (-not (Test-Path -PathType Leaf -Path "$($RepoRoot)\.python-version")) {
            $result = & pyenv global
            if ($result -eq "no global version configured") {
                Write-Info "!!! Using pyenv but having no local or global version of Python set." -Color Red, Yellow
                Exit-WithCode 1
            }
        }
        $python = & pyenv which python

    }

    $env:POETRY_HOME="$RepoRoot\.poetry"
    (Invoke-WebRequest -Uri https://install.python-poetry.org/ -UseBasicParsing).Content | & $($python) -
}

function Set-Cwd() {
    Set-Location -Path $RepoRoot
}

function Restore-Cwd() {
    $tmp_current_dir = Get-Location
    if ("$tmp_current_dir" -ne "$CurrentDir") {
        Write-Info -Text ">>> ", "Restoring current directory" -Color Green, Gray
        Set-Location -Path $CurrentDir
    }
}

function Initialize-Environment {
    Write-Info -Text ">>> ", "Reading Poetry ... " -Color Green, Gray -NoNewline
    if (-not(Test-Path -PathType Container -Path "$( $env:POETRY_HOME )\bin"))
    {
        Write-Info -Text "NOT FOUND" -Color Yellow
        Install-Poetry
        Write-Info -Text "INSTALLED" -Color Cyan
    }
    else
    {
        Write-Info -Text "OK" -Color Green
    }

    if (-not(Test-Path -PathType Leaf -Path "$( $repo_root )\poetry.lock"))
    {
        Write-Info -Text ">>> ", "Installing virtual environment and creating lock." -Color Green, Gray
    }
    else
    {
        Write-Info -Text ">>> ", "Installing virtual environment from lock." -Color Green, Gray
    }
    $startTime = [int][double]::Parse((Get-Date -UFormat %s))
    & "$env:POETRY_HOME\bin\poetry" config virtualenvs.in-project true --local
    & "$env:POETRY_HOME\bin\poetry" config virtualenvs.create true --local
    & "$env:POETRY_HOME\bin\poetry" install --no-root $poetry_verbosity --ansi
    if ($LASTEXITCODE -ne 0)
    {
        Write-Info -Text "!!! ", "Poetry command failed." -Color Red, Yellow
        Restore-Cwd
        Exit-WithCode 1
    }
    if (Test-Path -PathType Container -Path "$( $repo_root )\.git")
    {
        Write-Info -Text ">>> ", "Installing pre-commit hooks ..." -Color Green, White
        & "$env:POETRY_HOME\bin\poetry" run pre-commit install
        if ($LASTEXITCODE -ne 0)
        {
            Write-Info -Text "!!! ", "Installation of pre-commit hooks failed." -Color Red, Yellow
        }
    }
    $endTime = [int][double]::Parse((Get-Date -UFormat %s))
    Restore-Cwd
    try
    {
        if (Test-CommandExists "New-BurntToastNotification")
        {
            $app_logo = "$repo_root\tools\icons\ayon.ico"
            New-BurntToastNotification -AppLogo "$app_logo" -Text "AYON", "Virtual environment created.", "All done in $( $endTime - $startTime ) secs."
        }
    }
    catch {}
    Write-Info -Text ">>> ", "Virtual environment created." -Color Green, White
}

function Invoke-Ruff {
    param (
        [switch] $Fix
    )
    $Poetry = "$RepoRoot\.poetry\bin\poetry.exe"
    $RuffArgs = @( "run", "ruff", "check" )
    if ($Fix) {
        $RuffArgs += "--fix"
    }
    & $Poetry $RuffArgs
}

function Invoke-Codespell {
    param (
        [switch] $Fix
    )
    $Poetry = "$RepoRoot\.poetry\bin\poetry.exe"
    $CodespellArgs = @( "run", "codespell" )
    if ($Fix) {
        $CodespellArgs += "--fix"
    }
    & $Poetry $CodespellArgs
}

function Write-Help {
    <#
    .SYNOPSIS
        Write-Help function to write help messages.
    #>
    Write-Host ""
    Write-Host "AYON Addon management script"
    Write-Host ""
    Write-Info -Text "Usage: ", "./manage.ps1 ", "[command]" -Color Gray, White, Cyan
    Write-Host ""
    Write-Host "Commands:"
    Write-Info -Text "  create-env                    ", "Install Poetry and update venv by lock file" -Color White, Cyan
    Write-Info -Text "  ruff-check                    ", "Run Ruff check for the repository" -Color White, Cyan
    Write-Info -Text "  ruff-fix                      ", "Run Ruff fix for the repository" -Color White, Cyan
    Write-Info -Text "  codespell                     ", "Run codespell check for the repository" -Color White, Cyan
    Write-Host ""
}

function Resolve-Function {
    if ($null -eq $FunctionName) {
        Write-Help
        return
    }
    $FunctionName = $FunctionName.ToLower() -replace "\W"
    if ($FunctionName -eq "createenv") {
        Set-Cwd
        Initialize-Environment
    } elseif ($FunctionName -eq "ruffcheck") {
        Set-Cwd
        Invoke-Ruff
    } elseif ($FunctionName -eq "rufffix") {
        Set-Cwd
        Invoke-Ruff -Fix
    } elseif ($FunctionName -eq "codespell") {
        Set-Cwd
        Invoke-CodeSpell
    } else {
        Write-Host "Unknown function ""$FunctionName"""
        Write-Help
    }
}

# -----------------------------------------------------

Show-PSWarning
Write-AsciiArt

Resolve-Function
