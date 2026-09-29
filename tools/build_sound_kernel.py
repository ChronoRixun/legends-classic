"""Build the optional compiled sound-encoder kernel (tools/xml1build/lib/ima_kernel.c) for the Python running this
script.

    python tools/build_sound_kernel.py [--out DIR] [--check] [--clean]

Output: <out>/ima_kernel-<platform>.<dll|so|dylib> (default out: build/native, gitignored; <platform> e.g. win_amd64,
win32, linux_x86_64 - the library must match the Python's bitness, so it is named after sysconfig.get_platform()).
Never commit the binary. xml1build/lib/adpcm_c.py loads it when present, checks that it was built from the current
ima_kernel.c (source sha1 compiled in) and runs a self-check; otherwise the sound stages use the numpy path. The frozen
builder ships the library next to adpcm_c (tools/freeze_builder.py).

Windows: MSVC. Uses `cl` from PATH when it targets the right architecture (a Developer Prompt, or CI after
ilammy/msvc-dev-cmd), else finds Visual Studio (Build Tools) with vswhere and runs vcvarsall.bat x64 / x86 first.
Elsewhere: $CC or cc (gcc / clang). Flags keep the IEEE double operations exactly as written (no FMA contraction:
/fp:precise without /arch:AVX2, -ffp-contract=off) - the wide beam must add and multiply like numpy does.
--check: only load the existing library and print adpcm_c's status. --clean: delete the library.
Exit code 0 = the library was built (or, with --check, found) and passed adpcm_c's self-check - the check CI runs.

CI (GitHub Actions, windows-latest has Visual Studio with the C++ tools; see research/release/BUILDER_DESIGN.md 1p):
    - uses: actions/setup-python@v5   (with: python-version = the frozen builder's Python, architecture: x64)
    - run: python -m pip install numpy==<the pinned version>
    - run: python tools/build_sound_kernel.py"""
import argparse, os, shutil, struct, subprocess, sys, tempfile

from xml1build.lib import adpcm_c  # tools/ is this script's folder, so the package imports directly

SRC = adpcm_c.SOURCE
MSVC_FLAGS = ['/nologo', '/O2', '/fp:precise', '/MT', '/LD', '/W3', '/utf-8']
CC_FLAGS = ['-O2', '-shared', '-fPIC', '-ffp-contract=off', '-fno-fast-math', '-std=c99', '-Wall']


def vswhere():
    base = os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')
    p = os.path.join(base, 'Microsoft Visual Studio', 'Installer', 'vswhere.exe')
    return p if os.path.isfile(p) else None


def find_vcvarsall():
    vw = vswhere()
    if not vw:
        return None
    try:
        out = subprocess.run([vw, '-latest', '-products', '*', '-requires',
                              'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'],
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    for line in out.splitlines():
        p = os.path.join(line.strip(), 'VC', 'Auxiliary', 'Build', 'vcvarsall.bat')
        if line.strip() and os.path.isfile(p):
            return p
    return None


def cl_on_path_arch():
    """'x64' / 'x86' / 'arm64' if a cl.exe on PATH says which target it compiles for, else None."""
    if not shutil.which('cl'):
        return None
    try:
        err = subprocess.run(['cl'], capture_output=True, text=True).stderr
    except OSError:
        return None
    for arch in ('x64', 'x86', 'ARM64'):
        if f' for {arch}' in err:
            return arch.lower()
    return None


def build_windows(out_path, sha, tmp):
    arch = {'win_amd64': 'x64', 'win32': 'x86', 'win_arm64': 'arm64'}.get(adpcm_c.platform_tag())
    if arch is None:
        raise SystemExit(f'unsupported Windows platform {adpcm_c.platform_tag()}')
    args = MSVC_FLAGS + [f'/DKERNEL_SRC={sha}', SRC, '/Fo' + os.path.join(tmp, 'ima_kernel.obj'), f'/Fe{out_path}',
                         '/link', '/NOLOGO', f'/IMPLIB:{os.path.join(tmp, "ima_kernel.lib")}']
    if cl_on_path_arch() == arch:
        print('using cl from PATH (' + arch + ')')
        return subprocess.run(['cl'] + args, cwd=tmp).returncode
    vc = find_vcvarsall()
    if not vc:
        raise SystemExit('no MSVC found: install Visual Studio Build Tools (C++ workload) or run from a Developer '
                         'Prompt; the sound stages keep working without the kernel (numpy path)')
    print(f'using {vc} {arch}')
    bat = os.path.join(tmp, 'build.bat')
    host = 'x64' if os.environ.get('PROCESSOR_ARCHITECTURE', '').upper() in ('AMD64', 'ARM64') else 'x86'
    target = arch if arch == host else f'{host}_{arch}'
    with open(bat, 'w') as fh:
        fh.write('@echo off\r\n')
        fh.write(f'set "PATH={os.path.dirname(vswhere())};%PATH%"\r\n')     # vcvarsall looks for vswhere on PATH
        fh.write(f'call "{vc}" {target} >nul || exit /b 1\r\n')
        fh.write('cl ' + ' '.join(f'"{a}"' if ' ' in a else a for a in args) + '\r\n')
    return subprocess.run(['cmd', '/d', '/c', bat], cwd=tmp).returncode


def build_posix(out_path, sha, tmp):
    cc = os.environ.get('CC') or shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
    if not cc:
        raise SystemExit('no C compiler (set CC); the sound stages keep working without the kernel (numpy path)')
    cmd = [cc] + CC_FLAGS + [f'-DKERNEL_SRC={sha}', SRC, '-o', out_path]
    print(' '.join(cmd))
    return subprocess.run(cmd, cwd=tmp).returncode


def install(staged, out_path):
    """Move the new library into place. Windows cannot replace a library that a process has loaded, but it can
    rename it: the old one becomes <name>.old (deleted now if nothing uses it, else by the next build)."""
    old = out_path + '.old'
    try:
        os.remove(old)
    except OSError:
        pass
    try:
        os.replace(staged, out_path)
    except PermissionError:
        os.replace(out_path, old)
        os.replace(staged, out_path)
        try:
            os.remove(old)
        except OSError:
            print(f'the previous library is still loaded by a process: left {old}')


def main(argv):
    ap = argparse.ArgumentParser(prog='build_sound_kernel.py')
    ap.add_argument('--out', default=adpcm_c.default_dir())
    ap.add_argument('--check', action='store_true', help='only load the existing library and report')
    ap.add_argument('--clean', action='store_true', help='delete the library')
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(line_buffering=True)          # keep our lines in order with the compiler's
    out_path = os.path.join(os.path.abspath(a.out), adpcm_c.lib_name())
    print(f'python {sys.version.split()[0]} {struct.calcsize("P") * 8}-bit, platform {adpcm_c.platform_tag()}')
    if a.clean:
        if os.path.exists(out_path):
            os.remove(out_path)
            print('deleted', out_path)
        return 0
    if not a.check:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        sha = adpcm_c.source_sha1()
        tmp = tempfile.mkdtemp(prefix='.tmp_ima_kernel_', dir=os.path.dirname(out_path))
        try:
            staged = os.path.join(tmp, adpcm_c.lib_name())
            rc = (build_windows if os.name == 'nt' else build_posix)(staged, sha, tmp)
            if rc or not os.path.isfile(staged):
                print(f'build FAILED (rc {rc})')
                return 1
            install(staged, out_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        print('built', out_path, f'(source sha1 {sha})')
    os.environ[adpcm_c.ENV] = out_path                   # check this library (even if XML1_SOUND_KERNEL=off)
    ok = adpcm_c.load()
    print('sound codec:', adpcm_c.STATUS)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
