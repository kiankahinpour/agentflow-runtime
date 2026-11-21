"""Build *on the native host* with PyInstaller; never publish binaries.

Windows -> AgentFlow.exe, macOS -> AgentFlow.app, Linux -> onedir + AppDir
and an optional AppImage when an operator-provided appimagetool is available.
CI smoke-checks outputs before uploading as draft artifacts.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ICON='''<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256"><rect width="256" height="256" rx="52" fill="#172b46"/><path d="M56 152L112 65l25 44 22-32 43 75-36 51H83Z" fill="none" stroke="#8ce4c6" stroke-width="17" stroke-linejoin="round"/><circle cx="112" cy="65" r="12" fill="#8ce4c6"/></svg>'''


def manifest(system, arch, artifact):
    from agentflow_runtime import __version__
    return {'product':'AgentFlow Runtime', 'version':__version__, 'platform':system,
            'architecture':arch, 'artifact':artifact, 'cross_compiled':False,
            'publishing':False, 'signature':'UNSIGNED',
            'certification':'UNVERIFIED until native host smoke and review'}


def build(out_dir:Path, *, appimagetool=None):
    system=platform.system()
    if system not in ('Linux','Windows','Darwin'):
        raise RuntimeError('native build unsupported on '+system)
    import PyInstaller  # noqa: F401; refuse fake or mislabelled artifacts
    out_dir=out_dir.resolve()
    out_dir.mkdir(parents=True,exist_ok=True)
    work=out_dir/'_work'
    cmd=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir',
         '--name','AgentFlow','--distpath',str(out_dir), '--workpath',str(work),
         '--specpath',str(work),'--collect-data','agentflow_runtime',
         '--collect-submodules','uvicorn','--collect-submodules','agentflow_runtime']
    if system=='Darwin':cmd.append('--windowed')
    cmd.append(str(ROOT/'tools'/'desktop_entry.py'))
    subprocess.run(cmd,check=True,cwd=ROOT)
    if system=='Windows':
        binary=out_dir/'AgentFlow'/'AgentFlow.exe'
    elif system=='Darwin':
        binary=out_dir/'AgentFlow.app'/'Contents'/'MacOS'/'AgentFlow'
    else:
        binary=out_dir/'AgentFlow'/'AgentFlow'
    if not binary.is_file():raise RuntimeError(f'PyInstaller did not produce expected binary: {binary}')
    subprocess.run([str(binary),'--check-only'],check=True,timeout=40)
    subprocess.run([str(binary),'--self-test'],check=True,timeout=90)
    result=manifest(system,platform.machine(),str(binary.relative_to(out_dir)))
    result['native_preflight']='PASSED'
    result['native_end_to_end']='PASSED'
    if system=='Linux':
        # AppDir remains useful without external network or appimagetool.
        appdir=out_dir/'AgentFlow.AppDir'
        appdir.mkdir(exist_ok=True)
        lib=appdir/'usr'/'lib'/'AgentFlow'
        shutil.copytree(out_dir/'AgentFlow',lib,dirs_exist_ok=True)
        apprun=appdir/'AppRun'
        apprun.write_text('#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\nexec "$HERE/usr/lib/AgentFlow/AgentFlow" "$@"\n')
        apprun.chmod(0o755)
        (appdir/'agentflow.desktop').write_text('[Desktop Entry]\nName=AgentFlow Runtime\nExec=AppRun\nIcon=agentflow\nType=Application\nCategories=Development;Utility;\nTerminal=true\n')
        (appdir/'agentflow.svg').write_text(ICON)
        with tarfile.open(out_dir/'AgentFlow-Linux-AppDir.tar.gz','w:gz') as archive:
            archive.add(appdir,arcname='AgentFlow.AppDir')
        if appimagetool:
            image=out_dir/'AgentFlow-Linux.AppImage'
            env={**os.environ,'ARCH':'aarch64' if platform.machine() in ('aarch64','arm64') else 'x86_64'}
            subprocess.run([str(Path(appimagetool).resolve()),str(appdir),str(image)],check=True,env=env)
            result['appimage']=str(image.name)
        else:
            result['appimage']='NOT_BUILT: provide --appimagetool with audited local executable'
    (out_dir/'native-build-report.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out-dir',default='dist-native')
    parser.add_argument('--appimagetool',help='path to operator-verified appimagetool binary (Linux)')
    a=parser.parse_args()
    print(json.dumps(build(Path(a.out_dir),appimagetool=a.appimagetool),indent=2))

if __name__=='__main__':main()
