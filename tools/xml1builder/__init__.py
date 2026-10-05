"""xml1-builder - the Legends Classic builder: X-Men Legends (Xbox disc image) on the X-Men Legends II PC engine.

The standalone command-line program the Ultimate Legends launcher runs (BUILDER_DESIGN.md section 2; the launcher's
protocol reference is its tools/dev/fake_xml1_builder.py). It wraps the port's pipeline (tools/xml1build: the prepare
stages P1-P5 and the content modules) in one profile, the play build:

    python -m xml1builder info    [--iso PATH] [--xml2 DIR] [--out DIR] [--cache DIR]
    python -m xml1builder build   --iso PATH --xml2 DIR --out DIR [--movies | --no-movies] [--cache DIR] [--jobs N]
    python -m xml1builder verify  --out DIR [--iso PATH] [--xml2 DIR]
    python -m xml1builder clean   [--out DIR] [--mods] [--cache DIR] [--dry-run]
    global: --events jsonl|text, --log FILE, --quiet, --version

(from tools/, or `python tools/xml1builder ...`; frozen: xml1-builder.exe). Modules:

  cli        arguments, the command dispatch, exit codes, the top-level error handling
  commands   info / build / verify / clean (the build's stage order and its state files)
  pipeline   the adapter to tools/xml1build (prepare stages, sync, content modules, sweep, validator); the only
             module that knows the pipeline's internals. StubPipeline-style replacements drive the unit tests.
  events     the JSON-lines event stream (schema 1) / the human text, the log file
  plan       the stages, their weights (measured seconds) and the progress / ETA arithmetic
  cancel     the cancel token: a `cancel` line or EOF on stdin, Ctrl+C, a job object for the worker processes
  lock       <out>/_build/lock and <cache>/lock
  stamp      building.json, stamp.json, the state machine (absent / foreign / incomplete / stale / current)
  manifest   the sha1 manifest of the output (verify, clean)
  inputs     the disc image and the XML2 install checks
  space      the disk-space estimates
  resources  packaged data (data/*.json) and paths, frozen or from source; the research tables the frozen builder
             carries (RESEARCH_DATA) and how they are packaged without game text

Frozen (BUILDER_DESIGN.md 3.2; SPEC.md 27.13): xml1-builder.spec here, driven by tools/freeze_builder.py (kernel
check, packaged tables, PyInstaller one folder, content guard over the bundled data, the release zip and the
launcher's xml1-builder.json) and tested by tools/freeze_smoke.py; CI: .github/workflows/release.yml.
"""
VERSION = '0.1.8'                 # the builder release (semver; the launcher compares it with the release manifest)
CONTENT_VERSION = 12              # bumped only when a build's output changes (a rebuild is offered to players)
SCHEMA = 1                        # the event schema (the "v" of the hello event)
MIN_LAUNCHER = '0.0.0'            # release manifest min_launcher: no minimum until the first launcher release with the
                                  # X-Men Legends entry is tagged (then that version; tools/freeze_builder.py)
PROJECT = 'Legends Classic'
REPO = 'ChronoRixun/legends-classic'
ISSUES_URL = f'https://github.com/{REPO}/issues'
# the notice --help, --version and every log header print (LEGAL.md; two lines, plain ASCII)
DISCLAIMER = ('Unofficial fan tool; not affiliated with or endorsed by Marvel, Disney, Activision or Raven Software.',
              'Uses only copies you own: it ships no game content, uploads nothing and makes no network connections.')
# the notice --help, --version and every log header print (LEGAL.md; two lines, plain ASCII)
DISCLAIMER = ('Unofficial fan tool; not affiliated with or endorsed by Marvel, Disney, Activision or Raven Software.',
              'Uses only copies you own: it ships no game content, uploads nothing and makes no network connections.')
