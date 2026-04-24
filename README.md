## SigmaBat Reborn

SigmaBat Reborn generates `.bat` launchers for managed EXEs, DLLs, and shellcode, then routes execution through PowerShell. For managed EXEs it loads the assembly in memory, finds the entry point, and invokes it. For DLLs it detects whether the input is managed or native, checks that the requested symbol exists, and invokes it. For shellcode it stages the payload in the launcher environment, loads it into executable memory, and starts it in a new thread.

### Layout

- `src/` contains the generator and obfuscator
- `examples/` contains sample inputs for testing

### Features

- Handles managed EXEs
- Handles managed and native DLLs
- Supports shellcode inputs
- Invokes a symbol by name for DLLs
- Invokes the entry point for managed EXEs
- Performs symbol and entry point checks before generating the launcher
- Keeps the optional batch obfuscation step
- Supports `--no-obf` for plain launcher output
- Prints short launcher status messages for shellcode execution

### Usage

```text
python src/SigmaBat.py exe <input exe> <output bat> [--no-obf]
python src/SigmaBat.py dll <input dll> <symbol name> <output bat> [--no-obf]
python src/SigmaBat.py shellcode <input shellcode> <output bat> [--no-obf]
```

Examples:

```text
python src/SigmaBat.py exe examples/example.exe output.bat
python src/SigmaBat.py dll examples/managed_example.dll Ping output.bat
python src/SigmaBat.py dll examples/native_example.dll Ping output.bat
python src/SigmaBat.py shellcode examples/shellcode.bin output.bat
```

### Example Inputs

- `examples/example.exe` - managed EXE sample that is launched through `Assembly.EntryPoint`
- `examples/managed_example.dll` - managed DLL sample that exposes the `Ping` and `Main` methods
- `examples/native_example.dll` - native DLL sample that exposes the `Ping` export
- `examples/shellcode.bin` - minimal shellcode sample that immediately returns

### Runtime Behavior

Managed EXEs:
- Loaded in memory with `System.Reflection.Assembly.Load()`
- The launcher resolves `Assembly.EntryPoint`
- Supported entry point signatures are parameterless methods and `string[]`-style methods

Managed DLLs:
- Loaded in memory with `System.Reflection.Assembly.Load()`
- The launcher searches for a matching static method by name
- Supported signatures are parameterless methods and `string[]`-style entry methods

Native DLLs:
- Written to a temporary file for loading
- The launcher checks that the export exists with `GetProcAddress()`
- The current native path supports zero-argument exports

Shellcode:
- Loaded from a base64 blob staged in the launcher environment
- Allocated in executable memory and launched in a new thread
- Prints short status messages to the console
- Intended for shellcode byte payloads, not managed assemblies

### Workflow

1. Read the input bytes from disk.
2. Detect whether the file is a managed EXE, a managed DLL, or a native DLL.
3. Verify that the requested symbol or entry point exists before generating the launcher.
4. Embed the bytes and symbol name into the generated launcher.
5. Generate a `.bat` file that starts PowerShell.
6. Invoke the payload at runtime.
7. Optionally obfuscate the final batch file.

### Requirements

- Windows
- Python 3
- PowerShell
- A managed EXE, DLL, or shellcode blob with a compatible payload

### Notes

- If the requested function or entry point is missing, the generator stops before writing the launcher.
- `--no-obf` is useful when you want to inspect the generated batch file directly.
- The obfuscation step is cosmetic, preserves the batch structure, and does not change the execution path.
- No encoding games are required for normal use.
- Shellcode launchers print short progress messages so you can see where execution starts and ends.

### License

SigmaBat Reborn is distributed under the GPL license.

### Disclaimer

This project is provided for educational and research purposes. Use it only on software and systems you are authorized to test.

---

## Русский

### SigmaBat Reborn

SigmaBat Reborn создаёт лоадеры в `.bat` для управляемых сборок .NET, любого вида DLL и шеллкода, а затем передаёт выполнение в PowerShell. Для сборок последовательно происходят загрузка в память, поиск точки входа и переход к ней. Для DLL определяется, является ли файл управляемым или нативным, проверяется наличие указанной при сборке функции, затем она вызывается. Для шеллкода полезная нагрузка временно собирается в переменной окружения лоадера, помещается в исполняемую память и запускается в отдельном потоке.

### Структура

- `src/` содержит генератор и обфускатор
- `examples/` содержит примеры входных файлов для проверки

### Возможности

- Поддерживает управляемые EXE
- Поддерживает DLL
- Поддерживает шеллкод
- Вызывает символ по имени для DLL
- Вызывает точку входа для EXE
- Проверяет наличие символа и entry point до генерации лоадера
- Сохраняет необязательную обфускацию
- Поддерживает `--no-obf` для вывода без обфускации
- Выводит короткие статусные сообщения для шеллкода

### Использование

```text
python src/SigmaBat.py exe <input exe> <output bat> [--no-obf]
python src/SigmaBat.py dll <input dll> <symbol name> <output bat> [--no-obf]
python src/SigmaBat.py shellcode <input shellcode> <output bat> [--no-obf]
```

Примеры:

```text
python src/SigmaBat.py exe examples/example.exe output.bat
python src/SigmaBat.py dll examples/managed_example.dll Ping output.bat
python src/SigmaBat.py dll examples/native_example.dll Ping output.bat
python src/SigmaBat.py shellcode examples/shellcode.bin output.bat
```

### Примеры входов

- `examples/example.exe` - managed EXE-пример, который запускается через `Assembly.EntryPoint`
- `examples/managed_example.dll` - managed DLL-пример, который экспортирует методы `Ping` и `Main`
- `examples/native_example.dll` - native DLL-пример, который экспортирует `Ping`
- `examples/shellcode.bin` - минимальный шеллкод-пример, который сразу завершает выполнение

### Поведение во время работы

Управляемые EXE-сборки .NET:
- Загружается в память через `System.Reflection.Assembly.Load()`
- Лоадер получает `Assembly.EntryPoint`
- Поддерживаются entry point без параметров и методы со `string[]`

Управляемые DLL:
- Загружается в память через `System.Reflection.Assembly.Load()`
- Лоадер ищет подходящий static-метод по имени
- Поддерживаются методы без параметров и entry-style методы с `string[]`

Нативные DLL:
- Временно сохраняется на диск для загрузки
- Лоадер проверяет наличие экспорта через `GetProcAddress()`
- Текущий native-путь поддерживает exports без аргументов

Шеллкод:
- Временно собранного в переменной окружения лоадера
- Выделяется исполняемая память, стартует отдельный поток
- Выводит короткие статусные сообщения в консоль

### Принцип работы

1. Считать байты входного файла с диска.
2. Определить, является ли это упрввляемым EXE или DLL, нативной DLL или шеллкодом.
3. Проверить наличие нужного символа или точки входа до генерации лоадера.
4. Встроить байты и имя символа в генерируемый лоадер.
5. Сформировать `.bat`, обращающийся к PowerShell.
6. Вызвать полезную нагрузку во время выполнения.
7. Применить обфускацию, если не указано обратное.

### Требования

- Windows
- Python 3
- PowerShell
- Совместимая полезная нагрузка

### Примечания

- Если функция или точка входа отсутствуют, генератор остановится до записи лоадера.
- `--no-obf` удобно использовать, когда нужен читаемый `.bat`.
- Обфускация носит косметический характер, сохраняет структуру батника и не меняет путь выполнения.
- Для обычной работы без игр с кодировкой ничего дополнительного делать не нужно.
- Shellcode-лоадер выводит короткие сообщения о ходе запуска, чтобы было видно начало и завершение выполнения, а также полученный код.

### Лицензия

SigmaBat Reborn распространяется по лицензии GPL.

### Дисклеймер

Проект предоставляется в образовательных и исследовательских целях. Используйте его только на тех системах и в тех средах, где у вас есть разрешение на тестирование.