import argparse
from pathlib import Path

from build import (
    build_dll_launcher,
    build_managed_exe_launcher,
    build_shellcode_launcher,
)


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
            raise SystemExit(1)

        if input_path.suffix.lower() != ".exe":
            print(f"Unsupported input type: {input_path}")
            raise SystemExit(1)

        build_managed_exe_launcher(input_path, output_path, args.no_obf)
        return

    if args.command == "dll":
        input_path = Path(args.input_dll)
        output_path = Path(args.output_bat)

        if not input_path.is_file():
            print(f"File not found: {input_path}")
            raise SystemExit(1)

        if input_path.suffix.lower() != ".dll":
            print(f"Unsupported input type: {input_path}")
            raise SystemExit(1)

        build_dll_launcher(input_path, args.symbol_name, output_path, args.no_obf)
        return

    if args.command == "shellcode":
        input_path = Path(args.input_shellcode)
        output_path = Path(args.output_bat)

        if not input_path.is_file():
            print(f"File not found: {input_path}")
            raise SystemExit(1)

        build_shellcode_launcher(input_path, output_path, args.no_obf)
        return


if __name__ == "__main__":
    main()
