"""xml1builder.cli - the command line (BUILDER_DESIGN.md 2.1, 2.2; the launcher's fake builder is the reference).

    xml1-builder info    [--iso PATH] [--xml2 DIR] [--out DIR] [--cache DIR]
    xml1-builder build   --iso PATH --xml2 DIR --out DIR [--movies | --no-movies] [--cache DIR]
                         [--keep-cache | --drop-cache] [--link-base] [--jobs N] [--no-ini] [--allow-unknown-exe]
    xml1-builder verify  --out DIR [--iso PATH] [--xml2 DIR] [--deep]
    xml1-builder clean   [--out DIR] [--mods] [--cache DIR] [--dry-run]
    xml1-builder --version
    global: [--events jsonl|text] [--log FILE] [--quiet]

Exit codes: 0 ok, 1 build failed (E_PIPELINE / E_VALIDATE: our bug), 2 refused (E_USAGE, E_OUT_UNSAFE,
E_OUT_FOREIGN, E_OUT_LOCKED, E_CACHE_LOCKED), 3 input not usable (E_ISO_*, E_XML2_*, E_CACHE_*), 4 E_SPACE,
5 cancelled, 6 E_IO, 70 E_INTERNAL."""
from __future__ import annotations

import argparse
import os
import sys
import traceback

from . import CONTENT_VERSION, DISCLAIMER, ISSUES_URL, PROJECT, REPO, SCHEMA, VERSION
from . import resources as R
from .errors import BuilderError, REPORT_HINT
from .events import Output, mask

COMMANDS = ('info', 'build', 'verify', 'clean')


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise BuilderError('E_USAGE', f'{message}.', 'Run xml1-builder --help for the usage.', {})


def make_parser():
    p = _Parser(prog='xml1-builder', add_help=True,
                description=f'{PROJECT}: builds X-Men Legends (from your Xbox disc image) on the X-Men Legends II PC '
                            f'engine (your install). https://github.com/{REPO}',
                epilog='Nothing is downloaded and nothing from the games is shared: the builder reads your disc image '
                       'and your X-Men Legends II install and writes the game into --out (and its cache). '
                       + ' '.join(DISCLAIMER))
    p.add_argument('--version', action='store_true', help='print the version (jsonl: hello + result)')
    p.add_argument('--events', choices=('jsonl', 'text'), default='text',
                   help='jsonl: JSON-lines events on stdout, human text on stderr (the launcher); text (default)')
    p.add_argument('--log', help='log file (default: <out>/_build/builder.log for a build)')
    p.add_argument('--quiet', action='store_true', help='no human text on the console (the log keeps it)')
    p.add_argument('command', nargs='?', choices=COMMANDS)
    p.add_argument('--iso', help='your X-Men Legends Xbox disc image (Redump .iso or XISO; read only)')
    p.add_argument('--xml2', help='your X-Men Legends II PC install (read only)')
    p.add_argument('--out', help='the folder the game is built into (empty, or one the builder made)')
    p.add_argument('--cache', help='the build cache (default %%LOCALAPPDATA%%\\xml1-builder\\cache)')
    movies = p.add_mutually_exclusive_group()
    movies.add_argument('--movies', action='store_true', help='with the movies (the default)')
    movies.add_argument('--no-movies', dest='no_movies', action='store_true', help='without the movies (-1.1 GB)')
    keep = p.add_mutually_exclusive_group()
    keep.add_argument('--keep-cache', dest='keep_cache', action='store_true', help='keep the cache (the default)')
    keep.add_argument('--drop-cache', dest='drop_cache', action='store_true',
                      help='delete this disc\'s cache after a successful build')
    p.add_argument('--link-base', dest='link_base', action='store_true', help='(not supported yet: files are copied)')
    p.add_argument('--jobs', type=int, help='worker processes for the sound stages (default: every CPU)')
    p.add_argument('--no-ini', dest='no_ini', action='store_true', help='do not merge the port\'s keys into '
                                                                         'xml2-fix.ini (they are in the stamp)')
    p.add_argument('--allow-unknown-exe', dest='allow_unknown_exe', action='store_true',
                   help='testers: build for an XMen2.exe that is not a known retail build')
    p.add_argument('--deep', action='store_true', help='verify: also check every file inside the disc image')
    p.add_argument('--mods', action='store_true', help='clean: also delete <out>\\mods')
    p.add_argument('--dry-run', dest='dry_run', action='store_true', help='clean: only count what would go')
    return p


def _pre_jsonl(argv) -> bool:
    """--events jsonl, found before argparse runs (so a usage error is reported as events too)."""
    for i, arg in enumerate(argv):
        if arg == '--events' and i + 1 < len(argv):
            return argv[i + 1] == 'jsonl'
        if arg == '--events=jsonl':
            return True
    return False


def _hello(output, v):
    output.event('hello', v=SCHEMA, builder=v['version'], content_version=v['content_version'], commit=v['commit'],
                 pid=os.getpid(), project=PROJECT)


def main(argv=None, *, pipeline_factory=None, stdin=None, fd_redirect=True, exit_fn=None) -> int:
    R.setup()
    from .cancel import CancelToken, own_job_object, watch_stdin
    from . import commands as CMD

    argv = list(sys.argv[1:] if argv is None else argv)
    jsonl = _pre_jsonl(argv)
    v = CMD.version_info()
    try:
        a = make_parser().parse_args(argv)
    except SystemExit as e:                                   # --help
        return 0 if not e.code else 2
    except BuilderError as e:
        output = Output(jsonl)
        _hello(output, v)
        output.event('error', stage='probe', code=e.code, msg=e.msg, hint=e.hint, detail=e.detail)
        output.event('result', ok=False, exit=e.exit_code)
        if not jsonl:
            sys.stderr.write(make_parser().format_usage())
        return e.exit_code
    output = Output(a.events == 'jsonl', a.quiet, a.log)
    if a.version:
        if output.jsonl:
            _hello(output, v)
            output.event('result', ok=True, exit=0, version=v['version'], content_version=v['content_version'],
                         project=PROJECT, repo=f'https://github.com/{REPO}')
        else:
            print(f'xml1-builder {v["version"]} ({PROJECT}; content {v["content_version"]}, commit {v["commit"]}) - '
                  f'https://github.com/{REPO}')
            print('\n'.join(DISCLAIMER))
        return 0
    _hello(output, v)
    if not a.command:
        output.event('error', stage='probe', code='E_USAGE', msg='No command given (info, build, verify or clean).',
                     hint='Run xml1-builder --help for the usage.', detail={})
        output.event('result', ok=False, exit=2)
        return 2
    output.capture_stdout(fd_redirect=fd_redirect)
    kwargs = {} if exit_fn is None else {'exit_fn': exit_fn}
    cancel = CancelToken(**kwargs)
    if output.jsonl:
        watch_stdin(cancel, stdin, log=output.human)
    if pipeline_factory is None:
        from .pipeline import RealPipeline
        pipeline_factory = RealPipeline
    CMD.log_header(output, a.command, [mask(x) for x in argv])
    if a.command == 'build':
        own_job_object(output.human)
    try:
        R.check_root()                                        # frozen: the data comes from the bundle only
        if a.command == 'info':
            return CMD.cmd_info(a, output, pipeline_factory)
        if a.command == 'build':
            return CMD.cmd_build(a, output, cancel, pipeline_factory)
        if a.command == 'verify':
            if not a.out:
                raise BuilderError('E_USAGE', 'verify needs --out.', '', {})
            return CMD.cmd_verify(a, output, cancel, pipeline_factory)
        return CMD.cmd_clean(a, output, cancel)
    except BaseException as exc:  # noqa: BLE001 - every way out reports a result
        if CMD.is_cancel(exc):
            output.human('cancelled')
            output.event('result', ok=False, exit=5, cancelled=True)
            return 5
        err = CMD.failure(exc, 'probe')
        if err.code == 'E_INTERNAL':
            output.human(traceback.format_exc())
            err.hint = err.hint or REPORT_HINT
        output.event('error', stage=err.stage or 'probe', code=err.code, msg=err.msg, hint=err.hint,
                     detail=err.detail)
        output.event('result', ok=False, exit=err.exit_code)
        return err.exit_code
    finally:
        cancel.finished()
        output.close()


def run():
    """the console entry point (python -m xml1builder, the frozen exe)."""
    import multiprocessing
    multiprocessing.freeze_support()
    code = main()
    try:
        sys.stdout.flush()
    except (OSError, ValueError):
        pass
    sys.exit(code)


__all__ = ['main', 'run', 'make_parser', 'ISSUES_URL', 'VERSION', 'CONTENT_VERSION']
