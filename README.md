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
- Prints short launcher status messages and exit codes

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
- The launcher prints runtime status and final exit code

Managed DLLs:
- Loaded in memory with `System.Reflection.Assembly.Load()`
- The launcher searches for a matching static method by name
- Supported signatures are parameterless methods and `string[]`-style entry methods
- The launcher prints runtime status and final exit code

Native DLLs:
- Loaded in memory without temporary DLL files
- The launcher checks that the export exists before generation
- The runtime path maps the DLL image, resolves imports, applies relocations, and invokes the export
- The current native path supports zero-argument exports
- The launcher prints runtime status and final exit code

Shellcode:
- Loaded from a base64 blob staged in the launcher itself
- Allocated in executable memory and launched in a new thread
- Prints short status messages to the console
- Intended for shellcode byte payloads, not managed assemblies

### Workflow

1. Read the input bytes from disk.
2. Detect whether the file is a managed EXE, a managed DLL, or a native DLL.
3. Verify that the requested symbol or entry point exists before generating the launcher.
4. Embed payload data and parameters into the generated launcher.
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
- Launchers print short runtime progress messages and final exit code.

### License

SigmaBat Reborn is distributed under the GPL license.

### Disclaimer

This project is provided for educational and research purposes. Use it only on software and systems you are authorized to test.

---

## Русский

### SigmaBat Reborn

SigmaBat Reborn создаёт лоадеры в `.bat` для управляемых сборок .NET, любого вида DLL и машинного кода, а затем передаёт выполнение в PowerShell. Для сборок последовательно происходят загрузка в память, поиск точки входа и переход к ней. Для DLL определяется, является ли файл управляемым или нативным, проверяется наличие указанной функции, затем она вызывается. Для машинного кода полезная нагрузка собирается в самом лоадере, размещается в исполняемой памяти и запускается в отдельном потоке.

### Структура

- `src/` содержит генератор и обфускатор
- `examples/` содержит примеры входных файлов для проверки

### Возможности

- Поддерживает управляемые EXE
- Поддерживает управляемые и нативные DLL
- Поддерживает машинный код
- Вызывает символ по имени для DLL
- Вызывает точку входа для EXE
- Проверяет наличие символа и точки входа до генерации лоадера
- Сохраняет необязательную обфускацию
- Поддерживает `--no-obf` для вывода без обфускации
- Выводит короткие сообщения о ходе выполнения и итоговый код завершения

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

- `examples/example.exe` - пример управляемого EXE, который запускается через `Assembly.EntryPoint`
- `examples/managed_example.dll` - управляемая DLL, которая экспортирует методы `Ping` и `Main`
- `examples/native_example.dll` - нативная DLL, экспортирующая `Ping`
- `examples/shellcode.bin` - минимальный пример машинного кода, который сразу завершает выполнение

### Поведение во время работы

Управляемые EXE-сборки .NET:
- Загружается в память через `System.Reflection.Assembly.Load()`
- Лоадер получает `Assembly.EntryPoint`
- Поддерживаются точки входа без параметров и методы со `string[]`
- Лоадер выводит сообщения о ходе выполнения и итоговый код завершения

Управляемые DLL:
- Загружается в память через `System.Reflection.Assembly.Load()`
- Лоадер ищет подходящий статический метод по имени
- Поддерживаются методы без параметров и методы со `string[]`
- Лоадер выводит сообщения о ходе выполнения и итоговый код завершения

Нативные DLL:
- Загружается в память без временных файлов DLL
- Лоадер проверяет наличие экспорта до генерации
- Во время выполнения образ DLL отображается в память, разрешаются импорты, применяются релокации и вызывается экспорт
- Текущий способ поддерживает экспорты без аргументов
- Лоадер выводит сообщения о ходе выполнения и итоговый код завершения

Машинный код:
- Загружается из base64-блока, встроенного в лоадер
- Выделяется исполняемая память, затем стартует отдельный поток
- Выводит короткие статусные сообщения в консоль

### Принцип работы

1. Считать байты входного файла с диска.
2. Определить, является ли это управляемым EXE, управляемой DLL, нативной DLL или машинным кодом.
3. Проверить наличие нужного символа или точки входа до генерации лоадера.
4. Встроить полезную нагрузку и параметры в генерируемый лоадер.
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
- Лоадеры выводят короткие сообщения о ходе запуска и итоговый код завершения.

### Лицензия

SigmaBat Reborn распространяется по лицензии GPL.

### Дисклеймер

Проект предоставляется в образовательных и исследовательских целях. Используйте его только на тех системах и в тех средах, где у вас есть разрешение на тестирование. Идея репозитория заключается в демонстрации расширения функционала служебных скриптов, придерживаясь концепции "диск - это лава". Автор не несёт ответственности за ваши действия.
