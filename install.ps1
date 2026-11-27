# CrewAI Studio installer.
# Downloads the app archive (no git client), creates a virtual environment,
# installs dependencies and makes shortcuts.
#
#   powershell -ExecutionPolicy Bypass -File install.ps1
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Source C:\path\crewai.zip
#   powershell -ExecutionPolicy Bypass -File install.ps1 -InstallDir D:\Tools\CrewAI -Run
#   powershell -ExecutionPolicy Bypass -File install.ps1 -PythonExe C:\Python312\python.exe
[CmdletBinding()]
param(
    [string]$Source = "",
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "CrewAI Studio"),
    [string]$Branch = "main",
    [string]$Port = "7860",
    [string]$PythonExe = "",
    [switch]$NoShortcut,
    [switch]$NoDesktop,
    [switch]$SkipDeps,
    [switch]$Run
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$RepoZip = "https://codeload.github.com/abdyrakhman/CrewAI_GUI/zip/refs/heads/$Branch"
$SkipNames = @(".git", ".venv", "data", ".setup", "tests", "__pycache__", ".github", "scripts", ".pytest_cache")

function Write-Step([string]$Text) { Write-Host "  $Text" -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host "  OK  $Text" -ForegroundColor Green }
function Fail([string]$Text) { Write-Host "  ERROR  $Text" -ForegroundColor Red; exit 1 }

function Get-PythonVersion([string]$Exe, [string[]]$Prefix) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $Exe @Prefix -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $output) {
            return ($output | Select-Object -Last 1).Trim()
        }
    } catch {
        return ""
    } finally {
        $ErrorActionPreference = $previous
    }
    return ""
}

function Find-Python {
    $candidates = New-Object System.Collections.ArrayList
    if ($PythonExe) {
        [void]$candidates.Add(@{ Exe = $PythonExe; Prefix = @(); Label = $PythonExe })
    }
    foreach ($name in @("Python312", "Python311", "Python310")) {
        foreach ($base in @((Join-Path $env:LOCALAPPDATA "Programs\Python"), "C:\Program Files", "C:\")) {
            $path = Join-Path (Join-Path $base $name) "python.exe"
            if (Test-Path -LiteralPath $path) {
                [void]$candidates.Add(@{ Exe = $path; Prefix = @(); Label = $path })
            }
        }
    }
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher -and $launcher.Source) {
        foreach ($flag in @("-3.12", "-3.11", "-3.10", "-3")) {
            [void]$candidates.Add(@{ Exe = $launcher.Source; Prefix = @($flag); Label = "py $flag" })
        }
    }
    foreach ($name in @("python", "python3")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command -and $command.Source) {
            [void]$candidates.Add(@{ Exe = $command.Source; Prefix = @(); Label = $command.Source })
        }
    }
    foreach ($candidate in $candidates) {
        $version = Get-PythonVersion -Exe $candidate.Exe -Prefix $candidate.Prefix
        if (-not $version) { continue }
        $major, $minor = $version.Split(".")
        if ([int]$major -eq 3 -and [int]$minor -ge 10 -and [int]$minor -le 13) {
            return @{ Exe = $candidate.Exe; Version = $version }
        }
    }
    return $null
}

Write-Host ""
Write-Host "  CrewAI Studio installer" -ForegroundColor Magenta
Write-Host "  -----------------------" -ForegroundColor DarkGray

$work = Join-Path ([System.IO.Path]::GetTempPath()) ("crewai-install-" + [Guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $work -Force | Out-Null
$root = $null
try {
    # ------------------------------------------------------------ 1. source
    if (-not $Source) {
        $zip = Join-Path $work "crewai.zip"
        Write-Step "Downloading the app archive (no git needed)..."
        try {
            Invoke-WebRequest -Uri $RepoZip -OutFile $zip -UseBasicParsing -TimeoutSec 180
        } catch {
            Fail "Could not download $RepoZip. Check the internet connection or pass -Source."
        }
        Expand-Archive -Path $zip -DestinationPath (Join-Path $work "src") -Force
        $candidate = Get-ChildItem -Path (Join-Path $work "src") -Directory | Select-Object -First 1
        if ($candidate) { $root = $candidate.FullName }
    } elseif (Test-Path -LiteralPath $Source -PathType Container) {
        $root = (Resolve-Path -LiteralPath $Source).Path
    } elseif (Test-Path -LiteralPath $Source -PathType Leaf) {
        Write-Step "Unpacking $Source..."
        Expand-Archive -Path $Source -DestinationPath (Join-Path $work "src") -Force
        $candidate = Get-ChildItem -Path (Join-Path $work "src") -Directory | Select-Object -First 1
        if ($candidate) { $root = $candidate.FullName }
    } else {
        Fail "Source not found: $Source"
    }

    if (-not $root -or -not (Test-Path (Join-Path $root "run.py"))) {
        Fail "The archive does not look like CrewAI Studio (run.py is missing)."
    }
    Write-Ok "Source is ready"

    # ------------------------------------------------------------ 2. python
    Write-Step "Looking for Python 3.10-3.13 (3.12 recommended)..."
    $python = Find-Python
    if (-not $python) {
        Fail "Python 3.10-3.13 was not found. Install Python 3.12 (winget install Python.Python.3.12), then run again or pass -PythonExe."
    }
    if ($python.Version -ne "3.12") {
        Write-Host "  Note: Python $($python.Version) found; 3.12 is recommended." -ForegroundColor Yellow
    }
    Write-Ok "Python $($python.Version) at $($python.Exe)"

    # -------------------------------------------------------- 3. install dir
    if (-not (Test-Path -LiteralPath $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }
    $InstallDir = (Resolve-Path -LiteralPath $InstallDir).Path
    if ($InstallDir.TrimEnd("\") -eq (Resolve-Path -LiteralPath $root).Path.TrimEnd("\")) {
        Fail "InstallDir must differ from the source folder."
    }
    Write-Step "Copying files to $InstallDir..."
    $copyItems = @("app", "web", "docs", "run.py", "start.bat", "requirements.txt",
                   "install.ps1", "install.bat", "README.md", "README.en.md", "CHANGELOG.md", "LICENSE")
    foreach ($item in $copyItems) {
        $from = Join-Path $root $item
        if (Test-Path -LiteralPath $from) {
            Copy-Item -LiteralPath $from -Destination $InstallDir -Recurse -Force
        }
    }
    Write-Ok "Files copied (your data folder is kept on upgrade)"

    # --------------------------------------------------------- 4. venv + pip
    $venvDir = Join-Path $InstallDir ".venv"
    $venvPython = Join-Path $venvDir "Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Step "Creating the virtual environment..."
        $previousAction = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try { & $python.Exe -m venv $venvDir 2>$null } catch { }
        if (-not (Test-Path $venvPython)) {
            # some embedded Python builds have no ensurepip; the interpreter still works
            try { & $python.Exe -m venv --without-pip $venvDir 2>$null } catch { }
        }
        $ErrorActionPreference = $previousAction
        if (-not (Test-Path $venvPython)) { Fail "Could not create .venv." }
        Write-Ok "Virtual environment created"
    } else {
        Write-Ok "Virtual environment already exists"
    }

    $venvPip = Join-Path $venvDir "Scripts\pip.exe"
    if (-not $SkipDeps) {
        if (-not (Test-Path $venvPip)) {
            Fail "This Python has no pip/ensurepip. Install Python 3.12 from python.org and run again."
        }
        Write-Step "Installing dependencies (CrewAI, first run takes a few minutes)..."
        $previousAction = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $venvPython -m pip install --disable-pip-version-check --upgrade pip 2>$null | Out-Null
        & $venvPython -m pip install --disable-pip-version-check -r (Join-Path $InstallDir "requirements.txt")
        $pipExit = $LASTEXITCODE
        $ErrorActionPreference = $previousAction
        if ($pipExit -ne 0) { Fail "Dependency installation failed. Check the internet connection." }
        Write-Ok "Dependencies installed"
    } else {
        Write-Host "  Skipped dependency installation (-SkipDeps)." -ForegroundColor Yellow
    }

    # ----------------------------------------------------------- 5. shortcuts
    if (-not $NoShortcut) {
        $startBat = Join-Path $InstallDir "start.bat"
        $shell = New-Object -ComObject WScript.Shell
        $targets = @((Join-Path ([Environment]::GetFolderPath("Programs")) "CrewAI Studio.lnk"))
        if (-not $NoDesktop) {
            $targets += (Join-Path ([Environment]::GetFolderPath("Desktop")) "CrewAI Studio.lnk")
        }
        foreach ($link in $targets) {
            try {
                $shortcut = $shell.CreateShortcut($link)
                $shortcut.TargetPath = $startBat
                $shortcut.WorkingDirectory = $InstallDir
                $shortcut.Description = "CrewAI Studio"
                $shortcut.Save()
                Write-Ok "Shortcut: $link"
            } catch {
                Write-Host "  Could not create shortcut $link" -ForegroundColor Yellow
            }
        }
    }

    # -------------------------------------------------------------- 6. done
    $launcher = Join-Path $InstallDir "start.bat"
    Write-Host ""
    Write-Host "  CrewAI Studio is installed." -ForegroundColor Green
    Write-Host "  Folder:   $InstallDir"
    Write-Host "  Start:    $launcher"
    Write-Host "  Address:  http://127.0.0.1:$Port"
    Write-Host "  On the first start the generated admin password is printed in the console."
    Write-Host "  The app asks to change it at the first sign-in."
    Write-Host ""
    if ($Run) {
        Write-Step "Starting CrewAI Studio..."
        Start-Process -FilePath $launcher -ArgumentList @("--no-browser", "--port", $Port) -WorkingDirectory $InstallDir
    } else {
        Write-Host "  Run it later with:  $launcher"
    }
} finally {
    try { Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue } catch { }
}
