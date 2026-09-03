# Publication Release Checklist

## Local public-repository gates

- [x] Public audit PASS
- [x] Historical frozen source/evidence explanation present
- [x] Workload contracts 8/8 PASS
- [x] README local image/link validation PASS
- [x] Publication asset validation PASS
- [x] Public claim validation PASS
- [x] Clean-clone static verification PASS
- [x] Clean-clone Python D1 smoke PASS
- [x] Clean-clone Go D1 smoke PASS
- [x] Public reproduction boundary PASS
- [x] Clean clone remained Git-clean after generated results
- [x] Fresh sanitized one-commit public Git history built and re-verified locally

### Local verification evidence — 2026-09-03

Source branch tested: `feat/publication-package`.

A clean clone was created in a temporary Linux directory. WSL could not use Git's local hardlink optimization across the mounted Windows filesystem and the temporary Linux filesystem, so the clean-clone gate used `git clone --no-hardlinks --branch feat/publication-package ...`. This changes only clone transport, not repository content.

Static clean-clone checks:

```text
PASS: public repository text audit
PASS: workload contracts validated 8/8
PASS: publication assets validated
PASS: public benchmark claims validated
PASS: public reproduction boundary verified
```

Self-contained runtime smoke checks, with no private source repository dependency:

```text
PASS: python D1 smoke measured-1
PASS: public reproduction boundary verified
PASS: go D1 smoke measured-1
PASS: public reproduction boundary verified
```

Both smoke trials retained empty invariant-failure output and generated `trial.json` evidence under the ignored `results/public-repro/` path. The clean clone remained Git-clean after the run.

An environmental issue was encountered before the successful run: stale benchmark-only Compose projects had exhausted Docker's predefined subnet pool. With no active benchmark matrix/scenario process, only obsolete benchmark Compose projects from earlier Track A verification runs were removed. Unrelated project networks were not modified.

A sanitized public snapshot was then created from the audited tree with a fresh Git repository and a single initial commit. On that fresh-history repository:

```text
PASS: public repository text audit
PASS: public reproduction boundary verified
PASS: workload contracts validated 8/8
PASS: publication assets validated
PASS: public benchmark claims validated
98 passed, 1 skipped
Git history: 1 commit
Git status: clean
```

The old benchmark development history is therefore not required for the public release.

## External publication status

GitHub publication is live and verified. Medium and LinkedIn remain pending because they require an authenticated browser publishing flow and must use verified live URLs rather than guessed links.

Verified GitHub URL:

```text
https://github.com/ferhatsli/python-vs-go-pos-benchmark
```

## GitHub release

- [x] Fresh sanitized public Git history created locally
- [x] Public repository name: `python-vs-go-pos-benchmark`
- [x] Description configured
- [x] Topics configured
- [x] MIT license detected on live GitHub
- [ ] Social preview uploaded (1280×640)
- [x] Live README images and relative links verified through the GitHub README HTML/API surface
- [x] Live GitHub URL recorded

## Medium release

- [x] English article source prepared
- [x] Figure captions prepared in manuscript
- [x] Figure alt text prepared in manuscript
- [ ] Semantic title/subtitle/headings/code blocks transferred to Medium
- [ ] Desktop preview checked
- [ ] Mobile preview checked
- [ ] GitHub CTA verified
- [ ] Live Medium URL recorded

## LinkedIn release

- [x] English launch-copy source prepared
- [x] HTTPS-only live-link finalizer implemented and tested
- [ ] Medium URL live
- [ ] GitHub URL live
- [ ] Finalized launch copy uses verified HTTPS links only
- [ ] Mobile line breaks checked
- [ ] Published post links verified

## Verification log

### 2026-09-03 — GitHub live verification

```text
Repository: https://github.com/ferhatsli/python-vs-go-pos-benchmark
Visibility: PUBLIC
Default branch: main
License: MIT
Topics: backend, benchmark, fastapi, go, k6, performance, pos, postgresql, python
```

The GitHub README HTML/API response references the committed hero, CARD, Dashboard, Worker, and architecture assets. The dedicated 1280×640 social-preview PNG is committed at `assets/hero/github-social-preview.png`; uploading it in repository Settings remains the only incomplete GitHub presentation step.
