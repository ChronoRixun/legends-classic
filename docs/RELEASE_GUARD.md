# Guard release switch

The release default is OFF until the corrected XML1 rules pass real-controller checks.
Telekinesis and flying carry remain ON. Rebuild removes a stale GuardDecideRule when OFF.

After acceptance, the single product-default change is in `tools/xml1builder/__init__.py`:

```python
DEFAULT_GUARD_DECIDE = 'xml1'  # currently 'off'
```

This one line feeds these exact consumers (no separate values to flip):
- `tools/build_xml1.py`: parse_args fallback for an omitted --guard-decide.
- `tools/xml1builder/cli.py`: make_parser --guard-decide default and help.
- `tools/xml1builder/commands.py`: Job.guard_decide and cmd_build missing-field fallback.
- `tools/xml1builder/pipeline.py`: RealPipeline.build_args missing-field fallback.

For an acceptance build only, add `--guard-decide xml1` to the build command; no source change is needed.
Explicit `--guard-decide off` still overrides the release default. Do not edit the DLL defaults, historical
CONTENT_OPTS fallbacks, GUARD_DECIDE dictionary or existing generated INIs to change the product default.
`tools/xml1build/fix_ini.py` writes `[Game] GuardDecideRule=xml1` only when the recorded build selects xml1;
the block companion node and companion-DLL checks must remain present.

Before flipping: follow the release kit LIVE-CHECKS.md, "Real-pad check" steps 1-9: first-frame flying pickup;
ordinary/stunned/large target grabs; rapid, held, keyboard and hero-switch blocking; partial/exhausted energy;
existing saves, save/reload and explicit Guard OFF. No live check was performed by this preparation.

After flipping, update the OFF policy assertions in `tests/unit/test_moves_builder_cli.py` (DEFAULTS, missing-field
expectation, explicit-TK/carry-OFF expectation and stale-key default test), plus the default assertions in
`tests/unit/test_tk_guard.py::test_tk_guard_written_only_with_grab_carry`. If Guard becomes ON, the
`--grab-carry xml2` fallback case must explicitly request `--guard-decide off` because XML1 Guard requires
the XML1 grab lifecycle. Update Guard wording in CHANGELOG.md, README.md and the companion Fix
CHANGELOG.md, README.md, packaging/release-notes/v1.11.0.md; refresh the work-folder DISCORD-DRAFT.md and
GO-CHECKLIST.md. Keep an explicit-OFF stale-key removal case and explicit-xml1 opt-in coverage. Run identity/default
tests and all release gates again, build from owned inputs, measure the final bind manifest, then package.
No identity renumbering is authorized. Do not reuse the Guard-ON preview fingerprint or package receipt.
