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

GitHub and Medium publications are live and verified. The Medium article was published by the user after final preview review. LinkedIn launch copy is finalized with verified live URLs; LinkedIn publication remains pending.

Verified GitHub URL:

```text
https://github.com/ferhatsli/python-vs-go-pos-benchmark
```

Verified Medium URL:

```text
https://medium.com/@ferhatsli/python-vs-go-pos-backend-benchmark-results-from-500-to-50-000-devices-c5ce0218d7dd
```

## GitHub release

- [x] Fresh sanitized public Git history created locally
- [x] Public repository name: `python-vs-go-pos-benchmark`
- [x] Description configured
- [x] Topics configured
- [x] MIT license detected on live GitHub
- [x] Social preview uploaded (1280×640)
- [x] Live README images and relative links verified through the GitHub README HTML/API surface
- [x] Live GitHub URL recorded

## Medium release

- [x] English article source prepared
- [x] Figure captions prepared in manuscript
- [x] Figure alt text prepared in manuscript
- [x] Semantic title/headings/lists/code blocks transferred to Medium draft
- [x] Five publication figures uploaded to Medium draft
- [x] Figure captions transferred to Medium draft
- [x] Story preview metadata checked (title, preview image, 7 min read)
- [x] GitHub CTA verified and linked
- [x] Final desktop article review by user
- [x] Mobile published-article check completed
- [x] User publishes Medium article
- [x] Live Medium URL recorded

## LinkedIn release

- [x] English launch-copy source prepared
- [x] HTTPS-only live-link finalizer implemented and tested
- [x] Medium URL live
- [x] GitHub URL live
- [x] Finalized launch copy uses verified HTTPS links only
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

The GitHub README HTML/API response references the committed hero, CARD, Dashboard, Worker, and architecture assets. The dedicated 1280×640 social-preview PNG was uploaded through repository Settings. The live repository `og:image` resolves to GitHub's `repository-images.githubusercontent.com` surface, confirming the custom preview is active.


### 2026-09-03 — Medium live verification

```text
Article: https://medium.com/@ferhatsli/python-vs-go-pos-backend-benchmark-results-from-500-to-50-000-devices-c5ce0218d7dd
Title: Python vs Go POS Backend Benchmark: Results from 500 to 50,000 Devices
Read time: 7 min
Publication state: LIVE
Figures verified: 5
```

The live article was checked in the authenticated Chrome session after publication. The canonical Medium URL was read from the page metadata. A mobile viewport check confirmed the article title, Worker section, and GitHub repository CTA remain present. LinkedIn launch copy was then finalized using the verified Medium and GitHub HTTPS URLs.
