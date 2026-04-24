### English

## SigmaBat Reborn

SigmaBat Reborn generates `.bat` launchers for managed .NET assemblies. The launcher starts PowerShell, loads the target assembly directly into memory, and invokes its entry point without writing the payload to disk.

### Features

- Converts a .NET assembly into a batch-based launcher
- Uses `powershell.exe` for in-memory assembly loading
- Supports automatic post-processing obfuscation
- Optional `--no-obf` flag for a plain launcher output

### Usage

```text
python SigmaBat.py <input assembly> <output bat> [--no-obf]
```

Examples:

```text
python SigmaBat.py payload.exe output.bat
python SigmaBat.py payload.exe output.bat --no-obf
```

### Workflow

1. Read the input assembly bytes from disk.
2. Base64-encode the payload and embed it in the launcher.
3. Generate a batch file that starts PowerShell with an encoded command.
4. Load the assembly in memory and invoke the entry point.
5. Optionally obfuscate the resulting batch file for presentation.

### Requirements

- Windows
- Python 3
- PowerShell
- A managed .NET assembly with a valid entry point

### Notes

- The default output includes the obfuscation step.
- Use `--no-obf` if you want to inspect the generated batch file directly.
- The launcher is intended for managed assemblies, not native executables.

### License

SigmaBat Reborn is distributed under the GPL license.

### Disclaimer

This project is provided for educational and research purposes. Use it only on software and systems you are authorized to test.

---

### Русский

## SigmaBat Reborn

SigmaBat Reborn создаёт лоадеры для управляемых .NET-сборок. Такой батник запускает PowerShell, загружает целевую сборку в память и вызывает точку входа без работы с диском.

### Возможности

- Преобразует .NET-сборку в `.bat`-лоадер
- Использует `powershell` для загрузки сборки в память
- По умолчанию играется с кодировкой выходного файла. Флаг `--no-obf` позволяет получить файл без обфускации.

### Использование

```text
python SigmaBat.py <input assembly> <output bat> [--no-obf]
```

Примеры:

```text
python SigmaBat.py payload.exe output.bat
python SigmaBat.py payload.exe output.bat --no-obf
```

### Принцип работы

1. Входная сборка преобзазуется в Base64.
2. Полезная нагрузка встраивается в лоадер.
3. Генерируется файл, запускающий PowerShell с захардкоженной командой + нагрузкой.
4. Сборка загружается в память, вызывается точка входа.
5. Если не указано обратное, ломается кодировка выходного файла.

### Требования

- Windows
- Python 3
- PowerShell
- Управляемая .NET-сборка с корректной точкой входа

### Лицензия

SigmaBat Reborn распространяется под лицензией GPL.

### Дисклеймер

Проект предоставляется в образовательных и исследовательских целях. Используйте его только там, где у вас есть разрешение на тестирование.