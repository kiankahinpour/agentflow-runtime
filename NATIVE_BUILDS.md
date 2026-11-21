# Native, unsigned desktop artifacts

AgentFlow's **desktop mode is a trusted, local-only browser dashboard** with an embedded Python runtime after bundling. It is **not** a native GUI framework and does **not** sandbox malicious agent code. No external AI provider is enabled by the desktop launcher.

## On each actual host OS

Builds must be performed on their target operating system: PyInstaller is **not a cross compiler**. Use an isolated, trusted build environment and review all dependencies before distribution.

```bash
python -m pip install -e '.[server]' 'pyinstaller>=6,<7'
python tools/build_native.py --out-dir dist-native
```

Each build executes `AgentFlow --check-only` and **end-to-end `AgentFlow --self-test`** from the generated binary. Source mode can be tested with:

```bash
python -m pip install -e '.[server]'
python -m agentflow_runtime.desktop --self-test
```

- **Windows:** `dist-native/AgentFlow/AgentFlow.exe` and its entire companion directory. A local v1.2.8 x64 build passed preflight and loopback Echo on Windows 11 Pro 25H2. The artifacts are unsigned. Other Windows releases and architectures require their own runner results.
- **macOS:** `dist-native/AgentFlow.app`; unsigned/unnotarized and Gatekeeper may block it. Test macOS Intel and Apple Silicon individually before promising support.
- **Linux:** `dist-native/AgentFlow/AgentFlow` and `AgentFlow-Linux-AppDir.tar.gz`. To create the single-file AppImage, provide an independently verified `appimagetool` binary with `--appimagetool /path/to/appimagetool`. No AppImage is produced without the tool.

`native-builds.yml` is **manual build-only CI** and uploads unsigned draft artifacts; it does not create GitHub releases or PyPI publications. For Linux AppImage building in CI, configure `AGENTFLOW_APPIMAGETOOL_URL` and `AGENTFLOW_APPIMAGETOOL_SHA256` as repository variables, pinned to a versioned official release asset. Unconfigured builds upload the Linux AppDir archive only.

Binary files can be large. Scan them, check platform-specific licenses, produce SHA-256 checksums, sign them, and arrange independent Windows/macOS/Linux host validation before distributing them publicly.

## Local operator usage

The desktop launcher displays a `127.0.0.1` URL and local token path. Open the URL in a browser and enter the bearer token stored under the user's private AgentFlow state directory. The launcher uses a separate local SQLite database; it deliberately drops any inherited PostgreSQL DSN or remote-bind settings. Exiting the launcher terminates its two managed processes. Untrusted multi-tenant execution remains disabled.
