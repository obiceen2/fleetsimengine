# Fleet Simulation Engine

A discrete-time fleet simulation engine written in C++17. The program accepts newline-delimited JSON commands and returns JSON responses.

## Requirements

- Windows
- MinGW-w64 GCC (C++17)
- CMake 3.16 or newer
- Python 3 (for automated tests)

The JSON library is included in the project.

## 1. Build

Open **Windows Command Prompt (cmd)** in the project directory and run:

```cmd
cmake -S . -B build -G "MinGW Makefiles" -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

## 2. Run

Run the provided example:

```cmd
build\simulator.exe < examples\cargo_delivery.jsonl
```

Or start the simulator interactively:

```cmd
build\simulator.exe
```

Enter one JSON command per line. Each command produces one JSON response.

## 3. Test

Run all automated tests:

```cmd
python -m unittest discover -s tests -v
```

The tests verify vessel movement, cargo and dock operations, historical state queries, input validation, and error handling.