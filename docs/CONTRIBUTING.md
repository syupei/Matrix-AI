# Maintenance

Edit only src/. Keep role entrypoints below 5000 characters and common rules in collaboration/. Version is package.json.

Use tools/production.py --build-dir build to run mechanism checks. For release, run evals/run.py with previous and candidate source using the same fixtures and host; review actual outputs against evals/cases/suite.json. Publication requires --publish --evidence path/to/comparison.json --notes path/to/notes.md. Missing, stale or regressing evidence blocks release. Raw model logs are local evidence and are not part of the consumer package.

New behavioral rules need a demonstrated failure and a passing correction; an unobserved recommendation remains a proposal. Periodically audit rules without evidence, retaining explicit user constraints and professional invariants. Changes to those constraints need their original owner.

Generated runtime package includes skills, common rules, shared standards and tools, installer and usage instructions. It excludes maintainer tests, reports, business fixtures and personal state. Stage validation checks records, not identity or professional quality. UI/device suitability needs visual/interactive tests beyond text probes.

From v0.16, release manifests and Git tags preserve source revisions; no new complete directories are added to packages/. Historical snapshots stay immutable. `tools/release.py verify` checks historical manifests and tagged canonical source. Generated build/ and dist/ are local artifacts.
