# Agentic CI/CD Workflow Automation

This repository now includes ten GitHub Actions workflows aligned to platform enablement goals.

## Workflow map

| Goal | Workflow file | Key automation |
|---|---|---|
| Security | `.github/workflows/security.yml` | Dependency review, secret scanning, CodeQL SAST, scheduled remediation PRs |
| Performance | `.github/workflows/performance.yml` | API latency budgets, frontend bundle budgets, Lighthouse quality gate |
| Data quality | `.github/workflows/data-quality.yml` | Migration dry-runs, schema drift checks, importer idempotency checks |
| Release | `.github/workflows/release.yml` | Semantic release drafting, release notes, canary/rollback dispatch hooks |
| Feature flags | `.github/workflows/feature-flags.yml` | Flag manifest validation, workflow-dispatch kill-switch PR creation |
| Observability | `.github/workflows/observability.yml` | Auto incident-context issue on upstream workflow failures |
| Environment previews | `.github/workflows/environment-preview.yml` | PR preview artifact build/upload + teardown hook |
| Knowledge | `.github/workflows/knowledge.yml` | Code-to-doc sync guard + ADR reminder comment |
| Cost | `.github/workflows/cost.yml` | PR cost heuristics from file/LOC deltas + threshold gating |
| Reliability | `.github/workflows/reliability.yml` | Scheduled smoke runs and flaky-test detection/routing |

## Supporting CI scripts

- `scripts/ci/check_api_latency.py`
- `scripts/ci/check_frontend_bundle_size.py`
- `scripts/ci/verify_import_idempotency.py`
- `scripts/ci/validate_feature_flags.py`
- `.config/feature-flags.yaml`
- `.github/lighthouserc.json`
- `.github/adr-template.md`
- `.github/release-drafter.yml`

## Required repository setup

1. Add labels used by automation: `incident`, `observability`, `reliability`, `flaky-test`.
2. Confirm `GITHUB_TOKEN` has workflow-default write permissions for PR comments/issues.
3. If you wire canary/rollback to production deploy commands, add required cloud credentials as repository or environment secrets.
4. If you already use external feature-flag providers, replace `.config/feature-flags.yaml` updates with provider API calls in the `kill-switch-pr` job.

## Notes

- The canary/rollback job is intentionally a safe placeholder until environment-specific deployment commands are added.
- The cost workflow uses repository-native heuristics (change-size based) so it works before cloud billing integrations are available.
- Preview environment workflow currently publishes build artifacts; deploy/teardown steps should be connected to your preview host.
