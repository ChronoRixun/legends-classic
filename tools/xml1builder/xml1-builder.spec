# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec of xml1-builder.exe (BUILDER_DESIGN.md 3.2 and 3.3): one folder, console, no UPX, a Windows
version resource and an application manifest (asInvoker, long-path aware). Run it through tools/freeze_builder.py,
which checks the compiled sound kernel, writes the generated inputs and passes them in the environment:

    XML1_FREEZE_GEN     a folder holding build-info.json (the commit etc.; bundled as xml1builder/data/build-info.json)
                        and research/<rel>: the packaged research tables (freeze_builder.package_research)
    XML1_FREEZE_KERNEL  the compiled sound kernel (ima_kernel-win_amd64.dll), '' = none (the numpy path)

dist/xml1-builder/ = xml1-builder.exe + _internal/ (sys._MEIPASS, which the frozen builder reads everything from):
    xml1builder/data/          known_dumps.json, known_xml2.json, xml2_retail_files.json.gz, build-info.json
    research/<rel>             the research tables the pipeline reads (xml1builder.resources.RESEARCH_DATA, from
                               XML1_FREEZE_GEN: graph.json / zones.json without game text); $XML1_PORT_ROOT =
                               _internal, so xml1build.sources resolves research/ there
    xml1build/lib/             ima_kernel.c + the kernel DLL: adpcm_c looks next to itself and checks that the DLL
                               was built from that source (else the sound stages use numpy)
Hidden imports: every module of xml1build (the content modules are imported by name, prepare stages and the media
music check run in spawned worker processes) and xml1builder, build_xml1, xmlb - minus the self-tests and the
developer-only tools."""
import os
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

TOOLS = Path(SPECPATH).resolve().parent            # noqa: F821 - SPECPATH is set by PyInstaller (tools/xml1builder)
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))                 # the spec process (not the frozen exe) reads the package metadata
from xml1builder import PROJECT, REPO as GITHUB_REPO, VERSION  # noqa: E402
from xml1builder import resources as R  # noqa: E402

GEN = Path(os.environ['XML1_FREEZE_GEN'])
KERNEL = os.environ.get('XML1_FREEZE_KERNEL', '')
BUILD_INFO = GEN / 'build-info.json'
if not BUILD_INFO.is_file():
    raise SystemExit(f'{BUILD_INFO} is missing: run tools/freeze_builder.py')

# ------------------------------------------------------------------------------------------------ what goes in
DATA_DIR = TOOLS / 'xml1builder' / 'data'
datas = [(str(p), 'xml1builder/data') for p in sorted(DATA_DIR.iterdir())
         if p.is_file() and p.name != 'build-info.json']
datas.append((str(BUILD_INFO), 'xml1builder/data'))
for rel in R.RESEARCH_DATA:
    src = GEN / 'research' / rel
    if not src.is_file():
        raise SystemExit(f'a packaged research table is missing: {src} (run tools/freeze_builder.py)')
    datas.append((str(src), str(Path('research', rel).parent.as_posix())))
datas.append((str(TOOLS / 'xml1build' / 'lib' / 'ima_kernel.c'), 'xml1build/lib'))
binaries = [(KERNEL, 'xml1build/lib')] if KERNEL else []

DEV_ONLY = {'igb_budget', 'schema_check', 'regress_nyc1', 'devdata'}


def _shipped(name):
    leaf = name.rsplit('.', 1)[-1]
    return not leaf.endswith('_selftest') and leaf not in DEV_ONLY


hiddenimports = sorted(set(collect_submodules('xml1build', filter=_shipped)
                           + collect_submodules('xml1builder', filter=_shipped)
                           + ['build_xml1', 'xmlb']))
excludes = ['tkinter', '_tkinter', 'numpy.f2py', 'numpy.tests', 'pytest', 'PIL', 'matplotlib', 'scipy', 'IPython',
            'xml1build.igb_budget', 'xml1build.schema_check', 'xml1build.regress_nyc1']


# ------------------------------------------------------------------------------------------------ resources
def _v4(v):
    nums = [int(x) for x in re.findall(r'\d+', v)[:4]]
    return tuple(nums + [0] * (4 - len(nums)))


VERSION_INFO = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_v4(VERSION), prodvers=_v4(VERSION), mask=0x3F, flags=0x0, OS=0x40004,
                      fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[StringFileInfo([StringTable('040904B0', [
        StringStruct('CompanyName', 'Ultimate Legends community'),
        StringStruct('FileDescription', f'{PROJECT} builder'),
        StringStruct('FileVersion', VERSION),
        StringStruct('InternalName', 'xml1-builder'),
        StringStruct('LegalCopyright', 'MIT License. Contains no game data.'),
        StringStruct('OriginalFilename', 'xml1-builder.exe'),
        StringStruct('ProductName', PROJECT),
        StringStruct('ProductVersion', VERSION),
        StringStruct('Comments', f'Builds X-Men Legends from your own Xbox disc image on your own X-Men Legends II '
                                 f'install. https://github.com/{GITHUB_REPO}')])]),
          VarFileInfo([VarStruct('Translation', [0x0409, 1200])])])

MANIFEST = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="asInvoker" uiAccess="false"/>
      </requestedPrivileges>
    </security>
  </trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application>
      <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"/>
    </application>
  </compatibility>
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true</longPathAware>
    </windowsSettings>
  </application>
</assembly>
"""

# ------------------------------------------------------------------------------------------------ build
a = Analysis(  # noqa: F821
    [str(TOOLS / 'xml1builder' / '__main__.py')],
    pathex=[str(TOOLS)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,                 # keep the asserts: the pipeline checks its own outputs with them
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='xml1-builder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=VERSION_INFO,
    manifest=MANIFEST,
    uac_admin=False,
    contents_directory='_internal',
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='xml1-builder',
)
