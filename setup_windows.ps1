[CmdletBinding()]
param(
    [switch]$Yes,
    [switch]$Offline,
    [switch]$UseManagedRuntime,
    [switch]$PrepareOnly,
    [string]$Python,
    [string]$ArtifactDir
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
Set-StrictMode -Version Latest
$AdventureRoot = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$AdventureOwner = '{"format":"ultra-project-setup-owned","version":1}'
$AdventureBootstrapLock = $null

function Assert-AdventurePath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $prefix = $AdventureRoot + '\'
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Setup refused a location outside this project.'
    }
    $current = $AdventureRoot
    foreach ($part in $full.Substring($prefix.Length).Split('\')) {
        $current = Join-Path $current $part
        if (Test-Path -LiteralPath $current) {
            $attributes = [IO.File]::GetAttributes($current)
            if (($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Setup found a linked environment folder. Extract the project into an ordinary folder.'
            }
        }
    }
    return $full
}

function New-AdventureOwnedFolder([string]$Name) {
    $path = Assert-AdventurePath (Join-Path $AdventureRoot $Name)
    $marker = Join-Path $path 'owner.json'
    if (Test-Path -LiteralPath $path) {
        if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
            throw 'Setup found an existing folder it does not own. Ask your instructor to check the project.'
        }
        $record = [IO.File]::ReadAllText($marker) | ConvertFrom-Json
        if ($record.format -ne 'ultra-project-setup-owned' -or $record.version -ne 1) {
            throw 'Setup will not replace an unrecognized setup folder.'
        }
    } else {
        [IO.Directory]::CreateDirectory($path) | Out-Null
        [IO.File]::WriteAllText($marker, $AdventureOwner, (New-Object Text.UTF8Encoding($false)))
    }
    return $path
}

function Open-AdventureLock([string]$Name) {
    $path = Assert-AdventurePath (Join-Path $AdventureRoot ('.setup\' + $Name))
    try { return [IO.File]::Open($path, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None) }
    catch { throw 'Adventure or setup is already using this project. Close the other window, then retry.' }
}

function Quote-AdventureArgument([string]$Value) {
    $quoted = [regex]::Replace($Value, '(\*)"', '$1$1\"')
    $quoted = [regex]::Replace($quoted, '(\+)$', '$1$1')
    return '"' + $quoted + '"'
}

function Invoke-AdventureProcess([string]$Executable, [string[]]$Arguments, [int]$Seconds = 180) {
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $Executable
    $info.Arguments = (($Arguments | ForEach-Object { Quote-AdventureArgument $_ }) -join ' ')
    $info.WorkingDirectory = $AdventureRoot
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.EnvironmentVariables['PYTHONDONTWRITEBYTECODE'] = '1'
    $info.EnvironmentVariables['PYTHONUTF8'] = '1'
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    try {
        if (-not $process.Start()) { throw 'A required setup tool could not start.' }
        $output = $process.StandardOutput.ReadToEndAsync()
        $errors = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($Seconds * 1000)) {
            $ownedId = $process.Id
            & "$env:SystemRoot\System32\taskkill.exe" /PID $ownedId /T /F 2>$null | Out-Null
            $process.WaitForExit(5000) | Out-Null
            throw 'A setup tool took too long. Close other setup processes and retry.'
        }
        $stdout = $output.GetAwaiter().GetResult()
        $stderr = $errors.GetAwaiter().GetResult()
        if ($stdout.Length + $stderr.Length -gt 262144) { throw 'A setup tool returned too much output.' }
        return [pscustomobject]@{Code=$process.ExitCode; Output=$stdout; Error=$stderr}
    } finally { $process.Dispose() }
}

$AdventureProbe = @"
import json,sys,platform,struct,ctypes,tkinter
print(json.dumps(dict(version=platform.python_version(),implementation=platform.python_implementation(),bits=struct.calcsize('P')*8,platform=sys.platform,tk_import=tkinter.TkVersion,elevated=bool(ctypes.windll.shell32.IsUserAnAdmin()))))
"@

function Test-AdventurePython([string]$Executable) {
    if (-not $Executable -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    if ($Executable -match '\\Microsoft\\WindowsApps\\python(?:3)?\.exe$') { return $false }
    try {
        $result = Invoke-AdventureProcess $Executable @('-I','-B','-c',$AdventureProbe) 20
        if ($result.Code -ne 0) { return $false }
        $identity = $result.Output | ConvertFrom-Json
        return ($identity.version -eq '3.12.14' -and $identity.implementation -eq 'CPython' -and
            $identity.bits -eq 64 -and $identity.platform -eq 'win32' -and $identity.tk_import -eq 8.6 -and
            $identity.elevated -eq $false)
    } catch { return $false }
}

function Test-AdventureArtifact([string]$Path, $Spec) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    if ((Get-Item -LiteralPath $Path).Length -ne $Spec.bytes) { return $false }
    $stream = [IO.File]::OpenRead($Path)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $hash = ([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $hasher.Dispose() }
    return $hash -eq $Spec.sha256
}

function Get-AdventureArtifact($Spec) {
    $downloads = Assert-AdventurePath (Join-Path $AdventureRoot '.setup\downloads')
    [IO.Directory]::CreateDirectory($downloads) | Out-Null
    $target = Assert-AdventurePath (Join-Path $downloads $Spec.filename)
    if (Test-Path -LiteralPath $target) {
        if (Test-AdventureArtifact $target $Spec) { return $target }
        $rejected = Assert-AdventurePath ($target + '.rejected-' + [guid]::NewGuid().ToString('N'))
        Move-Item -LiteralPath $target -Destination $rejected
        throw 'A cached download failed its integrity check. Setup kept it aside; retry to download a verified copy.'
    }
    $supplied = if ($ArtifactDir) { Join-Path $ArtifactDir $Spec.filename } else { $null }
    if ($supplied -and (Test-Path -LiteralPath $supplied) -and -not (Test-AdventureArtifact $supplied $Spec)) {
        throw 'The supplied setup file does not match the approved download. Ask your instructor for the correct file.'
    }
    if ($Offline -and (-not $supplied -or -not (Test-Path -LiteralPath $supplied -PathType Leaf))) {
        throw 'The required setup file is not available offline. Connect to the internet and retry, or ask your instructor for a recovery option.'
    }
    $partial = Assert-AdventurePath ($target + '.partial-' + [guid]::NewGuid().ToString('N'))
    try {
        if ($supplied -and (Test-Path -LiteralPath $supplied -PathType Leaf)) {
            [IO.File]::Copy($supplied, $partial, $false)
        } else {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            # A bounded streaming request avoids Windows PowerShell progress-host stalls.
            $request = [Net.HttpWebRequest]::Create($Spec.url)
            $request.Timeout = 20000
            $request.ReadWriteTimeout = 10000
            $response = $null
            $inputStream = $null
            $outputStream = $null
            try {
                $watch = [Diagnostics.Stopwatch]::StartNew()
                $response = $request.GetResponse()
                $inputStream = $response.GetResponseStream()
                $outputStream = [IO.File]::Open($partial, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
                $buffer = New-Object byte[] 65536
                $total = 0L
                while (($count = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                    $total += $count
                    if ($total -gt $Spec.bytes -or $watch.Elapsed.TotalSeconds -gt 90) {
                        throw 'The download exceeded its expected size or time limit. Retry setup.'
                    }
                    $outputStream.Write($buffer, 0, $count)
                }
            } finally {
                if ($null -ne $outputStream) { $outputStream.Dispose() }
                if ($null -ne $inputStream) { $inputStream.Dispose() }
                if ($null -ne $response) { $response.Dispose() }
                $request.Abort()
            }
        }
        if (-not (Test-AdventureArtifact $partial $Spec)) { throw 'A download failed its integrity check. Nothing from that download was installed.' }
        Move-Item -LiteralPath $partial -Destination $target
        return $target
    } finally {
        if (Test-Path -LiteralPath $partial) {
            $safe = Assert-AdventurePath $partial
            Remove-Item -LiteralPath $safe -Force
        }
    }
}

function Get-AdventureManagedRuntime($Spec) {
    $runtimeRoot = New-AdventureOwnedFolder '.runtime'
    $target = Assert-AdventurePath (Join-Path $runtimeRoot $Spec.directory)
    $executable = Join-Path $target 'python.exe'
    if (Test-Path -LiteralPath $target) {
        $marker = Join-Path $target '.ultra-runtime-owner.json'
        if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) { throw 'Setup will not replace an unrecognized runtime folder.' }
        $owner = [IO.File]::ReadAllText($marker) | ConvertFrom-Json
        if ($owner.sha256 -ne $Spec.sha256 -or $owner.format -ne 'ultra-project-runtime-owned') { throw 'The local runtime ownership record is not recognized.' }
        if (Test-AdventurePython $executable) { return $executable }
        $backup = Assert-AdventurePath ($target + '.previous-' + [guid]::NewGuid().ToString('N'))
        Move-Item -LiteralPath (Assert-AdventurePath $target) -Destination $backup
    }
    $archive = Get-AdventureArtifact $Spec
    $tar = (Get-Command tar.exe -ErrorAction Stop).Source
    $relativeArchive = $archive.Substring($AdventureRoot.Length + 1)
    $listing = Invoke-AdventureProcess $tar @('-tzf',$relativeArchive) 90
    if ($listing.Code -ne 0) { throw 'The verified runtime archive could not be read. Retry setup.' }
    $seen = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($member in $listing.Output.Split("`n")) {
        $name = $member.TrimEnd("`r",'/')
        if (-not $name) { continue }
        if (($name -ne 'python' -and -not $name.StartsWith('python/')) -or
            $name -match '(^/|:|\\|(^|/)\.\.(/|$))' -or -not $seen.Add($name)) {
            throw 'The runtime archive contains an unsafe or duplicate path.'
        }
    }
    if ($seen.Count -ne 3378) { throw 'The runtime archive has an unexpected file inventory.' }
    $staging = Assert-AdventurePath (Join-Path $runtimeRoot ('partial-' + [guid]::NewGuid().ToString('N')))
    [IO.Directory]::CreateDirectory($staging) | Out-Null
    try {
        $relativeStaging = $staging.Substring($AdventureRoot.Length + 1)
        $extraction = Invoke-AdventureProcess $tar @('-xzf',$relativeArchive,'-C',$relativeStaging) 90
        if ($extraction.Code -ne 0) { throw 'The verified runtime could not be extracted. Check free space and project permissions.' }
        $prepared = Assert-AdventurePath (Join-Path $staging 'python')
        if (-not (Test-AdventurePython (Join-Path $prepared 'python.exe'))) { throw 'The downloaded runtime did not pass its version, architecture and Tk-import checks.' }
        $ownership = @{format='ultra-project-runtime-owned';version=1;sha256=$Spec.sha256} | ConvertTo-Json -Compress
        [IO.File]::WriteAllText((Join-Path $prepared '.ultra-runtime-owner.json'), $ownership, (New-Object Text.UTF8Encoding($false)))
        Move-Item -LiteralPath (Assert-AdventurePath $prepared) -Destination (Assert-AdventurePath $target)
    } finally {
        if (Test-Path -LiteralPath $staging) {
            $safe = Assert-AdventurePath $staging
            Remove-Item -LiteralPath $safe -Recurse -Force
        }
    }
    return $executable
}

try {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Close setup and reopen it normally, without Run as administrator. No student code will be run elevated.'
    }
    $lockPath = Join-Path $AdventureRoot 'runtime-lock.json'
    $lock = [IO.File]::ReadAllText($lockPath) | ConvertFrom-Json
    if ($lock.format -ne 'ultra-project-runtime-lock' -or $lock.version -ne 1 -or $lock.python -ne '3.12.14' -or
        $lock.pillow_version -ne '12.3.0' -or $lock.platform -ne 'win_amd64' -or
        $lock.runtime.filename -ne 'cpython-3.12.14+20260814-x86_64-pc-windows-msvc-install_only.tar.gz' -or
        $lock.runtime.bytes -ne 46097715 -or $lock.runtime.sha256 -ne '7330282b47cd43a66b702d39078d2e5a88e580cee351d82f95045f21f5ee042a' -or
        $lock.runtime.url -ne 'https://github.com/astral-sh/python-build-standalone/releases/download/20260814/cpython-3.12.14%2B20260814-x86_64-pc-windows-msvc-install_only.tar.gz' -or
        $lock.runtime.directory -ne 'cpython-3.12.14-windows-x64' -or
        $lock.pillow.filename -ne 'pillow-12.3.0-cp312-cp312-win_amd64.whl' -or
        $lock.pillow.bytes -ne 7227137 -or $lock.pillow.sha256 -ne 'a2b55dd6b2a4c4b7d87ffa56bdb33fdc5fdb9a462173861a7bc097f17d91cb09' -or
        $lock.pillow.url -ne 'https://files.pythonhosted.org/packages/45/89/da2f7971a317f83d807fdd4065c0af40208e59e692cc43d315a71a0e96d1/pillow-12.3.0-cp312-cp312-win_amd64.whl') {
        throw 'Setup refuses an unknown download or missing integrity information. Extract the original setup files.'
    }
    Write-Host 'Adventure setup: CPython 3.12.14 for Windows x64 and Pillow 12.3.0.'
    Write-Host ('Project: ' + $AdventureRoot)
    Write-Host 'Setup prepares .venv here. If needed, it downloads the approved 46,097,715-byte Astral runtime into .runtime and the 7,227,137-byte Pillow wheel from PyPI.'
    Write-Host 'Publisher notices stay with the runtime. Student code and practice history are kept.'
    if (-not $Yes -and (Read-Host 'Continue? [Y/N]') -notin @('Y','y','YES','yes')) { exit 0 }
    New-AdventureOwnedFolder '.setup' | Out-Null
    $AdventureBootstrapLock = Open-AdventureLock 'bootstrap.lock'
    foreach ($name in @('setup.lock','workbench.lock')) { $check = Open-AdventureLock $name; $check.Dispose() }
    $selected = $null
    if ($Python) {
        if (-not (Test-AdventurePython $Python)) { throw 'The selected Python is not CPython 3.12.14 Windows x64 with Tk. Retry setup without the Python option to use the approved managed runtime.' }
        $selected = [IO.Path]::GetFullPath($Python)
    } elseif (-not $UseManagedRuntime) {
        $local = Join-Path $AdventureRoot ('.runtime\' + $lock.runtime.directory + '\python.exe')
        $candidates = @($local)
        $pathPython = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($pathPython) { $candidates += $pathPython.Source }
        $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($launcher) {
            try {
                $listed = Invoke-AdventureProcess $launcher.Source @('-0p') 20
                if ($listed.Code -eq 0) {
                    foreach ($line in $listed.Output.Split("`n")) {
                        if ($line -match '([A-Za-z]:\\.+python(?:w)?\.exe)\s*$') { $candidates += $matches[1].Trim() }
                    }
                }
            } catch { }
        }
        foreach ($candidate in ($candidates | Select-Object -Unique)) {
            if (Test-AdventurePython $candidate) { $selected = $candidate; break }
        }
    }
    if (-not $selected) {
        Write-Host 'Preparing the approved project-local runtime...'
        $selected = Get-AdventureManagedRuntime $lock.runtime
    }
    Write-Host 'Preparing the project environment and checking dependencies...'
    $arguments = @('-X','utf8','-B',(Join-Path $AdventureRoot 'setup_project.py'))
    if ($Offline) { $arguments += '--offline' }
    if ($ArtifactDir) { $arguments += @('--artifact-dir',[IO.Path]::GetFullPath($ArtifactDir)) }
    if ($PrepareOnly) { $arguments += '--prepare-only' }
    $AdventureBootstrapLock.Dispose()
    $AdventureBootstrapLock = $null
    $result = Invoke-AdventureProcess $selected $arguments 240
    if ($result.Output) { Write-Host $result.Output.TrimEnd() }
    if ($result.Error) { Write-Host $result.Error.TrimEnd() }
    exit $result.Code
} catch {
    Write-Host ('Setup did not finish: ' + $_.Exception.Message)
    Write-Host 'Keep your student files and saved runs. Check the connection and folder permissions, then retry SETUP.cmd.'
    exit 2
} finally {
    if ($null -ne $AdventureBootstrapLock) { $AdventureBootstrapLock.Dispose() }
}
