$current_dir = Get-Location
$script_dir = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
$repo_root = (Get-Item $script_dir).parent.FullName
& git submodule update --init --recursive


function Exit-WithCode($exitcode) {
    # Only exit this host process if it's a child of another PowerShell parent process...
    $parentPID = (Get-CimInstance -ClassName Win32_Process -Filter "ProcessId=$PID" | Select-Object -Property ParentProcessId).ParentProcessId
    $parentProcName = (Get-CimInstance -ClassName Win32_Process -Filter "ProcessId=$parentPID" | Select-Object -Property Name).Name
    if ('powershell.exe' -eq $parentProcName) { $host.SetShouldExit($exitcode) }

    exit $exitcode
 }


function Install-Poetry() {
    Write-Host ">>> Installing Poetry ... "
    $python = "python"
    if (Get-Command "pyenv" -ErrorAction SilentlyContinue) {
        if (-not (Test-Path -PathType Leaf -Path "$($repo_root)\.python-version")) {
            $result = & pyenv global
            if ($result -eq "no global version configured") {
                Write-Host "!!! Using pyenv but having no local or global version of Python set." -Color Red, Yellow
                Exit-WithCode 1
            }
        }
        $python = & pyenv which python

    }

    $env:POETRY_HOME="$repo_root\.poetry"
    (Invoke-WebRequest -Uri https://install.python-poetry.org/ -UseBasicParsing).Content | & $($python) -
}

Write-Host ">>>  Reading Poetry ... " -NoNewline
if (-not (Test-Path -PathType Container -Path "$($env:POETRY_HOME)\bin")) {
    Write-Host "NOT FOUND"
    Install-Poetry
    Write-Host "INSTALLED"
} else {
    Write-Host "OK"
}

if (-not (Test-Path -PathType Leaf -Path "$($repo_root)\poetry.lock")) {
    Write-Host ">>> Installing virtual environment and creating lock."
} else {
    Write-Host ">>> Installing virtual environment from lock."
}
$startTime = [int][double]::Parse((Get-Date -UFormat %s))
& "$env:POETRY_HOME\bin\poetry" install --no-root $poetry_verbosity --ansi
if ($LASTEXITCODE -ne 0) {
    Write-Host "!!! ", "Poetry command failed."
    Set-Location -Path $current_dir
    Exit-WithCode 1
}
Write-Host ">>> Installing pre-commit hooks ..."
& "$env:POETRY_HOME\bin\poetry" run pre-commit install
if ($LASTEXITCODE -ne 0) {
    Write-Host "!!! Installation of pre-commit hooks failed."
    Set-Location -Path $current_dir
    Exit-WithCode 1
}

$endTime = [int][double]::Parse((Get-Date -UFormat %s))
Set-Location -Path $current_dir
Write-Host ">>> Done in $( $endTime - $startTime ) secs."
