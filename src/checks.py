import os
import struct
import subprocess
import sys


def run_obfuscator(output_path):
    from pathlib import Path

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
