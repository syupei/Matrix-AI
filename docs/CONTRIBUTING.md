# Maintenance

Edit only `src/`. The version is in `package.json`. Keep role entry points (`SKILL.md`) at or below 3500 characters, common rules in `collaboration/`, and on-demand material behind each role's `GUIDANCE-INDEX.md`.

Consumer text must be host-neutral and publishable: no host or model names, no local absolute paths, no internal project names, no build history or decision IDs. `tools/production.py` enforces these checks (the quoted capability-model source text is exempt), together with link, size and privacy checks.

Build and run all mechanism tests:

```sh
python3 tools/production.py --build-dir build
```

Before a release, run the behavior suite on the previous release and on the candidate with the same fixtures and the same runner, then review every criterion against the actual replies and traces:

```sh
python3 evals/run.py --runner claude --source packages/<previous-release> --output eval-results/<previous>
python3 evals/run.py --runner claude --source build/<candidate> --output eval-results/<candidate>
```

`--runner codex` uses the Codex CLI instead; baseline and candidate must use the same runner. Write the comparison JSON described in `evals/README.md`, then publish:

```sh
python3 tools/production.py --build-dir build --publish --evidence eval-results/comparison.json --notes <release-notes.md>
```

Missing, stale or regressing evidence blocks the release. Raw model logs stay local and are not part of the consumer package.

New behavioral rules need a demonstrated failure and a passing correction; an unobserved recommendation remains a proposal. Periodically audit rules without evidence, keeping explicit user constraints and professional invariants. Text probes do not certify visual quality, spatial layout, device behavior or native confirmation controls.

The consumer package contains skills, common rules and tools, the installer, `START.md` and `BEHAVIOR-CHECKS.md`. It excludes maintainer tests, evaluation reports, business fixtures and personal state. Release manifests and Git tags preserve source revisions; historical snapshots under `packages/` stay immutable. `tools/release.py verify` checks historical manifests and tagged canonical sources.
