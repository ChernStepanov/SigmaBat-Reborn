import os
import sys
import base64
import shutil
import subprocess
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        sys.exit()

    input_file = sys.argv[1]
    if not (input_file.endswith('.bat') or input_file.endswith('.cmd')):
        sys.exit()

    certutil_path = shutil.which('certutil.exe')
    if certutil_path is None:
        print("CertUtil.exe not found.")
        input("Press Enter to continue...")
        sys.exit()

    input_path = Path(input_file)
    temp_b64 = input_path.with_suffix(input_path.suffix + ".b64")
    temp_out = input_path.with_name(f"{input_path.stem}-obf{input_path.suffix}")

    if temp_b64.exists():
        temp_b64.unlink()
    if temp_out.exists():
        temp_out.unlink()

    payload_b64 = base64.b64encode(input_path.read_bytes()).decode("ascii")
    temp_b64.write_text(payload_b64, encoding="ascii", newline="")

    try:
        subprocess.run(
            ["certutil.exe", "-f", "-decode", str(temp_b64), str(temp_out)],
            check=True,
            capture_output=True,
            text=True,
        )
        shutil.move(str(temp_out), str(input_path))
    finally:
        if temp_b64.exists():
            temp_b64.unlink()
        if temp_out.exists():
            temp_out.unlink()

if __name__ == "__main__":
    main()
