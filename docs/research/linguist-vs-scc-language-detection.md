# GitHub Linguist vs scc: Language Detection Comparison

**Date:** 2026-06-05  
**Researched by:** Orchestrator → Ask mode (web research)

---

## 1. Comparison Table

| Criterion | GitHub Linguist | scc (Sloc, Cloc and Code) | enry (Go port of Linguist) |
|---|---|---|---|
| **Languages supported** | ~600+ (defined in `languages.yml`) | ~200+ (extension + state machine) | ~600+ (same `languages.yml` as Linguist, auto-synced) |
| **Runtime requirements** | **Ruby gem** — requires Ruby + C extensions (`charlock_holmes`, `rugged`). Heavy dependency chain. | **Single Go binary** — zero runtime dependencies. Compiles to native executable. | **Single Go binary** (CLI) or **Go library** — compiled native. Also Python/Java/Rust bindings. |
| **Speed on mid-size repo** | **Slow** — Ruby startup overhead. GitLab cited this as a "frequently mentioned scalability issue." | **Extremely fast** — processes Linux kernel (79K files, 1.38 GB) in ~1 second real time (13s user across 12 cores). | **2× faster than Linguist** — pure Go, no shell-out overhead. Uses RE2 regex engine. |
| **Output formats** | JSON, plain text with breakdown | **10+ formats**: tabular, JSON, JSON2, CSV, CSV-stream, cloc-YAML, HTML, SQL, OpenMetrics | JSON, plain text (Linguist-compatible) |
| **Installation method** | `gem install github-linguist` — requires Ruby, build-essential, cmake, pkg-config, libicu-dev, zlib1g-dev, libcurl4-openssl-dev, libssl-dev. Docker also available. | `go install`, `brew install scc`, `scoop install scc`, `choco install scc`, `winget install`, `snap install scc`, or pre-built binary download | `go get github.com/go-enry/enry`, or pre-built binary. Docker also available. |
| **Maintenance status** | **Actively maintained** — v9.5.0 (March 2026). 6,909 commits, 135 releases. 1.4k+ dependents. | **Actively maintained** — v3.8.0 beta. 1,594 commits, 8.4k stars. Adding new languages regularly (Mojo, Moonbit, Cangjie). | **Actively maintained** — daily sync with upstream Linguist via GitHub Actions. 750 commits. |
| **Framework detection** | **Yes** — detects Vue SFC, React JSX, ASP.NET, Angular, etc. via heuristics, filenames, `.gitattributes` overrides, and Bayesian classifier. | **Limited** — detects ASP.NET, Razor, Phoenix LiveView, Blade by extension, but primarily a line counter, not a framework classifier. | **Same as Linguist** — inherits all heuristics, `.gitattributes`-style overrides (for git repos), and Bayesian classifier. |

---

## 2. Answers to Specific Questions

### Q1: Can we use GitHub Linguist without Ruby?

**Not directly.** The canonical Linguist is a Ruby gem with C native extensions. Two alternatives exist:

- **Docker** — `docker run --rm -v $(pwd):$(pwd) -t ghcr.io/github-linguist/linguist:latest`
- **enry (Go port)** — A pure Go port that auto-syncs with upstream Linguist, produces Linguist-compatible output, and is **2× faster**. GitLab is actively replacing their Ruby Linguist with go-enry (see GitLab issue #8526).

The only caveat is RE2 regex limitations (no lookahead/lookbehind from Oniguruma), affecting ~6 edge-case heuristics. Oniguruma can optionally be enabled via build tags.

### Q2: Is scc more practical (single binary, no runtime deps)?

**Yes, for code counting.** scc is strictly a **code counter** (SLOC, complexity, COCOMO, LOCOMO), not a language classifier:

**Advantages:** Zero dependencies, 10× faster than Linguist, rich output (complexity estimates, cost estimation, duplicate detection, git timeline reports), works on any directory (no `.git` required).

**Limitations:** Supports fewer languages (~200 vs ~600+), detection is extension + state-machine based (no multi-strategy pipeline), no framework detection, no `.gitattributes` support.

### Q3: What does GitHub itself use?

**GitHub uses Linguist.** It is the canonical source for:
- Repository language bar
- Language breakdown graphs in Insights
- Syntax highlighting decisions
- Binary/vendored/generated file classification

**GitLab** uses go-enry (the Go port) after replacing their Ruby Linguist due to scalability issues.

### Q4: Accuracy differences for edge cases

| Edge Case | Linguist | enry | scc |
|---|---|---|---|
| **ASP.NET** (`.aspx`, `.ascx`) | ✅ Detected | ✅ Same | ✅ Detected by extension |
| **Vue SFC** (`.vue`) | ✅ Detected | ✅ Same | ❌ Not in scc language list |
| **React JSX** | ✅ Detected | ✅ Same | ✅ Detected as JSX |
| **Razor** (`.cshtml`) | ✅ Detected | ✅ Same | ✅ Detected as Razor |
| **Ambiguous `.h`** (C vs C++ Header) | ✅ Content heuristics | ✅ Same (minor RE2 diff) | ⚠️ Lists both separately, may misclassify |
| **Shebang scripts** (no extension) | ✅ Shebang parsing | ✅ Same | ⚠️ Limited |
| **Vim/Emacs modeline** | ✅ Detected | ✅ Same | ❌ Not supported |
| **`.gitattributes` overrides** | ✅ Full support | ❌ Not yet (issue #18) | ❌ Not supported |
| **Generated/minified files** | ✅ Detects/excludes | ✅ Same | ✅ Has `--gen` / `--min-gen` flags |

**enry is ~99% accurate vs Linguist.** Divergences are due to RE2 lookahead limitations and missing `.gitattributes` support.

---

## 3. Recommendations

### By Use Case

| Use Case | Recommended Tool | Why |
|---|---|---|
| **CI/CD language detection** | **enry** | Single binary, no Ruby, Linguist-compatible, 2× faster, actively synced |
| **GitHub-matching results** | **Linguist** (Docker) | 100% accuracy guarantee if you need exact GitHub match |
| **Local dev / DevOps** | **scc** | Instant startup, rich formats, complexity/cost metrics, no deps |
| **Large-scale analysis** | **scc** | 79K files in 1 second, linear scaling, proven on 40TB datasets |
| **Language detection accuracy** | **enry** (near-identical to Linguist) | Used by GitLab in production, 99%+ accuracy match |
| **SLOC counting + metrics** | **scc** | CLOC-compatible with extra features (complexity, COCOMO, LOCOMO) |

### Summary Decision Matrix

```
                  ┌───────────────────────────────────────────────────────────┐
                  │           What do you need?                              │
                  ├─────────────┬──────────────┬──────────────┬──────────────┤
                  │  GitHub-    │  Fast SLOC   │  Speed +     │  "I just want │
                  │  matching   │  counting +  │  language    │  the lang"   │
                  │  language   │  complexity  │  detection   │  (API/lib)   │
                  │  detection  │  + cost      │              │              │
                  ├─────────────┼──────────────┼──────────────┼──────────────┤
                  │  Linguist   │     scc      │    enry      │  enry (Go)   │
                  │  (or enry   │              │              │  or          │
                  │   Docker)   │              │              │  enry-py     │
                  └─────────────┴──────────────┴──────────────┴──────────────┘
```

### Bottom Line

- **scc** and **enry** are **complementary, not competitive**. Use both for different purposes:
  - **enry** — if you need to match what GitHub shows on repo pages (language classification)
  - **scc** — if you need fast code metrics, SLOC counting, complexity estimates, and cost projections
  
- If you currently have a Ruby dependency, consider **enry** as a drop-in replacement that eliminates the Ruby runtime requirement while preserving ~99% of Linguist's accuracy.
- If you're building a tech-stack detection feature for a tool like TestAI, **enry** is the right choice for language detection, while **scc** is the right choice for code volume/complexity metrics.

---

## 4. Key References

- GitHub Linguist: https://github.com/github-linguist/linguist
- scc: https://github.com/boyter/scc
- enry (Go port): https://github.com/go-enry/go-enry
- GitLab migration to go-enry: https://gitlab.com/groups/gitlab-org/-/work_items/8526
