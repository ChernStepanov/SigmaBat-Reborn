import os
import sys
import base64
import shutil


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

    temp_b64_data = "//4mY2xzDQo="
    decoded_data = base64.b64decode(temp_b64_data)

    temp_decoded_file = f"{input_file}.tmp"
    with open(temp_decoded_file, 'wb') as f:
        f.write(decoded_data)

    with open(temp_decoded_file, 'ab') as f_decoded, open(input_file, 'rb') as f_input:
        shutil.copyfileobj(f_input, f_decoded)

    shutil.move(temp_decoded_file, input_file)


if __name__ == "__main__":
    main()
