# Cross-platform operating guide — v1.0.0 (candidate)

AgentFlow is **Python-backed with a web dashboard**, not a signed native desktop executable. The default demo (SQLite + built-in Echo/Word Count) is designed for Windows, macOS and Linux with Python >=3.10. The launchers create a Python virtual environment in `.venv`, install optional server dependencies and start the server/worker on **127.0.0.1 only**. They do not enable untrusted adapters.

## Windows 10/11
1. Install supported Python 3.10+ and make the `py` launcher available.
2. Unzip source in a writable folder. Double-click `Start_AgentFlow_Windows.bat` (or run it in CMD).
3. Browser: `http://127.0.0.1:8787` — get the API token from `%USERPROFILE%\.agentflow_runtime\local-token` and enter it in the login form.
4. Stop with Ctrl+C in the command prompt. Run `python tools/run_platform_validation.py --with-native` from the activated venv for tests.

## macOS (Intel/Apple Silicon)
1. Install Python 3.10+ with pip and venv support; Terminal may require permission to execute unsigned `.command` scripts.
2. Run `sh Start_AgentFlow_macOS.command` from Terminal. This uses a venv and opens the dashboard in a browser.
3. Read the token in `~/.agentflow_runtime/local-token`. The server binds to loopback only.
4. Stop with Ctrl+C; run `python tools/run_platform_validation.py --with-native` inside the activated venv.

## Linux
1. Install Python 3.10+ with pip/venv packages.
2. Run `sh Start_AgentFlow_Linux.sh`. Then open localhost dashboard and read the token in `~/.agentflow_runtime/local-token`.
3. Stop with Ctrl+C; run `python tools/run_platform_validation.py --with-native` for tests.

## Platform-specific features

| Feature | Windows | macOS | Linux |
|---|---|---|---|
| SQLite queue / FastAPI / dashboard | Code included, native CI planned | Code included, native CI planned | Local tests run |
| Built-in Echo / Word Count | Supported in Python | Supported in Python | Locally tested |
| External provider subprocess | Windows Job Object code; native test required | Best-effort trusted process group, **not** full containment | Linux subreaper and optional cgroups |
| Docker sandbox | Requires Docker Desktop; not yet verified | Requires Docker Desktop; not yet verified | CLI contract tested; real engine absent locally |
| QEMU disposable guest | Not supported by this adapter yet | Optional QEMU x86 TCG; not tested | Protocol mock tested, guest boot not verified |
| PostgreSQL | psycopg backend; live DB required | psycopg backend; live DB required | Code tested, live DB required |

Do not equate a successful CI matrix or the presence of a program with security certification. Native Windows/macOS test claims require actual runner logs. The release does not package authenticated AI provider credentials.

## Audit and privacy

The local token is generated into a private file when possible (POSIX mode 600). Windows does not have POSIX permission bits: use per-user directory ACLs and do not share this token file. Database prompts/results are plaintext; secure the user directory and backup files. Shared deployments require external TLS/auth and a stronger multi-tenant threat model.
