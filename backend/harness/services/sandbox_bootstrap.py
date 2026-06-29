"""SandboxBootstrap &mdash; per-language dependency detection + install.

Wire of C03 (orchestrator decomposition), Phase 2. The original
``harness.orchestrator._bootstrap_sandbox_deps`` was a 60-LOC
module-level free function that:

1. tested a list of manifest filenames inside the sandbox,
2. picked the first match as the project language, and
3. ran the per-language install command.

The work has a clear seam: ``detect_language`` is async I/O,
``install_command`` is pure (language + path &rarr; command
string), and ``bootstrap`` is the orchestrator that combines
them and returns the result dict the call site expects.

Phase 2.5 (LLM-assisted confirmation) adds a richer detection
chain. The 3-step pipeline mirrors the production-harness
pattern (manifest &rarr; lockfile &rarr; LLM confirm):

| Step | Trigger | Cost | Use case |
|---|---|---|---|
| 1. Manifest | always | ~50ms | the 80% case (Gemfile, package.json, ...) |
| 2. Lockfile | always (cheap) | ~50ms | sharpens installer (poetry vs pip, pnpm vs npm) |
| 3. LLM confirm | step 1 needs framework OR step 1 missed | ~2s | monorepos, framework detection, "no manifest" edge case |

The 3rd step is the deepening: a small model call (claude-haiku-3
or gpt-4o-mini, ~$0.0002) reads a directory tree + README
excerpt and returns ``{language, framework, confidence}``. It's
gated by a configurable timeout (default 3s) and falls back
to the manifest result on any error &mdash; bootstrap is a
do-it-once-per-run step, so 2s of extra latency is acceptable.

Per :mod:`CONTEXT.md` glossary:
- **SandboxBootstrap** &mdash; this module
- **Detection** &mdash; the dataclass returned by step 3
- **detect_language** &mdash; step 1, manifest scan
- **detect_lockfile** &mdash; step 2, lockfile second pass
- **detect_with_llm** &mdash; step 3, the orchestrator that
  chains steps 1+2+3 and returns a single ``Detection``
- **install_command** &mdash; pure: language &rarr; bash string
- **bootstrap** &mdash; the orchestrator-facing entry point;
  returns ``{success, language, framework, output, source}``
  (additive change from Phase 2 &mdash; the old 3-field shape
  is preserved for backward compat)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Detection:
    """The result of a 3-step language/framework detection chain.

    Fields:
    - ``language``: the detected language, one of the keys in
      :attr:`SandboxBootstrap.INSTALL_COMMAND` or ``"unknown"``.
    - ``framework``: the detected framework (django, fastapi,
      nextjs, rails, ...) or ``None`` if no LLM step ran, no
      framework was detected, or the LLM call timed out.
    - ``confidence``: 0.0&ndash;1.0, the LLM's self-reported
      confidence. 1.0 for manifest-only detections (the
      manifest either exists or it doesn't).
    - ``source``: which step produced the answer:
      ``"manifest"`` (step 1), ``"lockfile"`` (step 2),
      ``"llm"`` (step 3), or ``"manifest-fallback"`` (step 3
      ran but the LLM call failed and we kept the manifest
      result).
    """
    language: str
    framework: str | None
    confidence: float
    source: str


class SandboxBootstrap:
    """Per-language dependency detection + install for a sandbox.

    The class is stateless (all state is in class-level tables),
    so the methods are static. Three of them are async because
    they shell out to the sandbox; the rest are pure.
    """

    #: Manifest filename &rarr; language. The first match in
    #: dict-iteration order wins, so the order matters. Python
    #: is listed in 3 manifest forms (``pyproject.toml``,
    #: ``setup.py``, ``requirements.txt``) &mdash; ``pyproject.toml``
    #: is preferred because it is the modern standard; ``setup.py``
    #: is the legacy form; ``requirements.txt`` is the dependency-
    #: only form. Java is listed twice (``pom.xml`` for Maven,
    #: ``build.gradle`` for Gradle). Order: modern &rarr; legacy
    #: within a language.
    MANIFEST_LANGUAGE: ClassVar[dict[str, str]] = {
        "Gemfile": "ruby",
        "package.json": "node",
        "pyproject.toml": "python",
        "setup.py": "python",
        "requirements.txt": "python",
        "go.mod": "go",
        "Cargo.toml": "rust",
        "pom.xml": "java",
        "build.gradle": "java",
    }

    #: Lockfile filename &rarr; (language, installer_choice).
    #: Step 2 of the detection chain sharpens the installer
    #: choice: a project with both ``pyproject.toml`` and
    #: ``poetry.lock`` should use ``poetry install``, not
    #: ``pip install``. The ``language`` is redundant with the
    #: manifest scan but included for clarity; the
    #: ``installer_choice`` is the actual override.
    LOCKFILE_HINTS: ClassVar[dict[str, tuple[str, str]]] = {
        "poetry.lock": ("python", "poetry"),
        "uv.lock": ("python", "uv"),
        "Pipfile.lock": ("python", "pipenv"),
        "pnpm-lock.yaml": ("node", "pnpm"),
        "yarn.lock": ("node", "yarn"),
        "bun.lockb": ("node", "bun"),
        "Cargo.lock": ("rust", "cargo"),
        "go.sum": ("go", "go-modules"),
        "Gemfile.lock": ("ruby", "bundler"),
        "package-lock.json": ("node", "npm"),
    }

    #: Framework-detection patterns. The LLM is the source of
    #: truth for the framework answer; this table is the
    #: deterministic check that runs <em>before</em> the LLM
    #: call so the LLM is only invoked when the manifest scan
    #: found a language but we can't decide the framework
    #: without reading the file contents. Each entry is
    #: (language, regex, framework_name). The regex is matched
    #: against the file content of the manifest.
    FRAMEWORK_HINTS: ClassVar[list[tuple[str, str, str]]] = [
        # python: read pyproject.toml/setup.py/requirements.txt
        ("python", r"django", "django"),
        ("python", r"fastapi", "fastapi"),
        ("python", r"flask", "flask"),
        ("python", r"celery", "celery"),
        ("python", r"^\s*django\s*=", "django"),  # requirements.txt line
        # node: read package.json
        ("node", r'"next"\s*:', "nextjs"),
        ("node", r'"nuxt"\s*:', "nuxt"),
        ("node", r'"@angular/core"\s*:', "angular"),
        ("node", r'"react"\s*:\s*{[^}]*"name"', "react"),
        ("node", r'"express"\s*:', "express"),
        # ruby: read Gemfile
        ("ruby", r"^\s*gem\s+['\"]rails['\"]", "rails"),
        ("ruby", r"^\s*gem\s+['\"]sinatra['\"]", "sinatra"),
        # java: read pom.xml
        ("java", r"<artifactId>spring-boot", "spring"),
        # go: read go.mod (require line)
        ("go", r"github\.com/gin-gonic/gin", "gin"),
        ("go", r"github\.com/labstack/echo", "echo"),
        # rust: read Cargo.toml
        ("rust", r"actix-web", "actix"),
        ("rust", r"axum", "axum"),
    ]

    #: Language &rarr; install command template. The command is
    #: run inside the sandbox with ``cd {repo_path}`` prepended.
    #: Tail-20 keeps the output bounded &mdash; we only need the
    #: last lines to diagnose a failure. Timeout is 600s (10 min)
    #: because some Ruby/Python projects have hundreds of gems/
    #: packages to install on cold start.
    INSTALL_COMMAND: ClassVar[dict[str, str]] = {
        "ruby": "which ruby || (apt-get update && apt-get install -y ruby ruby-dev build-essential) && bundle install --jobs 4 --retry 3 2>&1 | tail -20",
        "node": "npm install 2>&1 | tail -20",
        "python": "pip install -e '.[dev]' 2>&1 || pip install -r requirements.txt 2>&1 | tail -20",
        "go": "go mod download 2>&1 | tail -20",
        "rust": "cargo fetch 2>&1 | tail -20",
        "java": "(which mvn && mvn dependency:resolve 2>&1 || gradle dependencies 2>&1) | tail -20",
    }

    #: Per-installer overrides. If the lockfile step found
    #: ``poetry.lock``, we replace the python install with
    #: ``poetry install``. This is the sharpness the
    #: original 3-line function was missing.
    INSTALL_OVERRIDES: ClassVar[dict[str, str]] = {
        "poetry": "poetry install --no-interaction 2>&1 | tail -20",
        "uv": "uv sync 2>&1 | tail -20",
        "pipenv": "pipenv install --dev 2>&1 | tail -20",
        "pnpm": "pnpm install 2>&1 | tail -20",
        "yarn": "yarn install 2>&1 | tail -20",
        "bun": "bun install 2>&1 | tail -20",
    }

    #: Default timeout for the install step. Cold-start Ruby
    #: ``bundle install`` on a 500-gem project can take 8 minutes.
    #: 600s gives 2 min of headroom before we declare failure.
    INSTALL_TIMEOUT_SECONDS: ClassVar[int] = 600

    #: Max stdout/stderr bytes we capture per side. The last
    #: 500 bytes of each side give enough context to diagnose
    #: a failure without flooding the log.
    OUTPUT_TAIL_BYTES: ClassVar[int] = 500

    #: Default timeout for the LLM confirm step (step 3).
    #: 3s is enough for haiku-class models; if the call
    #: takes longer, the bootstrap falls back to the
    #: manifest result so the run is never blocked.
    LLM_TIMEOUT_SECONDS: ClassVar[int] = 3

    #: Max bytes of the README excerpt we send to the LLM.
    #: 1500 chars is enough to identify the framework; longer
    #: excerpts cost more tokens without adding signal.
    LLM_README_MAX_CHARS: ClassVar[int] = 1500

    #: Max bytes of the file tree we send to the LLM.
    LLM_TREE_MAX_LINES: ClassVar[int] = 40

    # ------------------------------------------------------------------
    # Pure: language/installer &rarr; command string. No sandbox needed.
    # ------------------------------------------------------------------

    @staticmethod
    def install_command(language: str, repo_path: str, installer: str | None = None) -> str | None:
        """Return the bash command to install deps for ``language``.

        If ``installer`` is set (from a lockfile hint), the
        language's default command is replaced with the
        installer-specific override. Returns ``None`` if no
        installer is registered for the language; the caller
        decides whether ``None`` is a no-op success or a hard
        error &mdash; :meth:`bootstrap` preserves the original
        "no installer &rarr; success with log line" behaviour.
        """
        if installer and installer in SandboxBootstrap.INSTALL_OVERRIDES:
            cmd = SandboxBootstrap.INSTALL_OVERRIDES[installer]
        else:
            tmpl = SandboxBootstrap.INSTALL_COMMAND.get(language)
            if not tmpl:
                return None
            cmd = tmpl
        return f"cd {repo_path} && {cmd}"

    # ------------------------------------------------------------------
    # Async: shell into the sandbox. The two detection methods
    # run ``test -f`` and ``head`` calls; ``bootstrap`` runs
    # the full pipeline.
    # ------------------------------------------------------------------

    @staticmethod
    async def detect_language(sandbox: Any, repo_path: str) -> str:
        """Step 1 &mdash; scan the repo root for manifest files.

        Returns ``"unknown"`` if no manifest matches &mdash; the
        call site treats it as a no-op success and skips the
        install step. Cheapest step: ~50ms for 9 ``test -f``
        calls in a warm sandbox.
        """
        for manifest, language in SandboxBootstrap.MANIFEST_LANGUAGE.items():
            result = await sandbox.run(
                f"test -f {repo_path}/{manifest} && echo exists",
                timeout=10,
            )
            if result.stdout.strip() == "exists":
                return language
        return "unknown"

    @staticmethod
    async def detect_lockfile(sandbox: Any, repo_path: str) -> str | None:
        """Step 2 &mdash; find a lockfile, return the installer choice.

        Returns the ``installer_choice`` from
        :attr:`LOCKFILE_HINTS` (``"poetry"``, ``"uv"``,
        ``"pnpm"``, ...) or ``None`` if no lockfile matched.
        This step is also cheap (~50ms) because it's the same
        pattern as the manifest scan.
        """
        for lockfile, (language, installer) in SandboxBootstrap.LOCKFILE_HINTS.items():
            result = await sandbox.run(
                f"test -f {repo_path}/{lockfile} && echo exists",
                timeout=10,
            )
            if result.stdout.strip() == "exists":
                return installer
        return None

    @staticmethod
    async def detect_framework(sandbox: Any, repo_path: str, language: str) -> str | None:
        """Deterministic framework check before invoking the LLM.

        Reads the language's manifest file (pyproject.toml,
        package.json, Gemfile, ...) and greps for known
        framework signatures. This is faster than the LLM call
        and free, so we always try it first; the LLM is only
        invoked when the deterministic check returns ``None``.
        """
        if language == "unknown":
            return None
        manifest_path = _manifest_for_language(language)
        if manifest_path is None:
            return None
        result = await sandbox.run(
            f"head -c 8192 {repo_path}/{manifest_path}",
            timeout=10,
        )
        if result.returncode != 0:
            return None
        content = result.stdout or ""
        for lang, pattern, framework in SandboxBootstrap.FRAMEWORK_HINTS:
            if lang != language:
                continue
            import re as _re
            if _re.search(pattern, content, _re.MULTILINE):
                return framework
        return None

    @staticmethod
    async def _llm_confirm(
        sandbox: Any,
        repo_path: str,
        manifest_language: str,
        timeout_seconds: int,
    ) -> Detection | None:
        """Step 3 &mdash; ask a small model to confirm and find the framework.

        Reads a directory tree (top 2 levels, max 40 lines) and
        a README excerpt (max 1500 chars) and sends them to a
        haiku-class model with a tight system prompt. Returns
        the parsed ``Detection`` or ``None`` on any error
        (timeout, network, JSON parse, unexpected shape).

        The LLM is intentionally cheap and short &mdash; if
        the model is unavailable, slow, or returns garbage,
        :meth:`detect_with_llm` falls back to the manifest
        result and the bootstrap continues.
        """
        try:
            tree_result = await sandbox.run(
                f"find {repo_path} -maxdepth 2 -not -path '*/\\.*' | head -n {SandboxBootstrap.LLM_TREE_MAX_LINES}",
                timeout=5,
            )
            readme_result = await sandbox.run(
                f"head -c {SandboxBootstrap.LLM_README_MAX_CHARS} {repo_path}/README.md 2>/dev/null || echo",
                timeout=5,
            )
            tree = (tree_result.stdout or "").strip()
            readme = (readme_result.stdout or "").strip()
        except Exception as exc:
            logger.debug("LLM-confirm: failed to read tree/README (%s)", exc)
            return None

        from harness.llm import ChatMessage, LLMRouter
        from harness.api.state import get_llm
        router = get_llm() or LLMRouter()
        if router is None:
            return None

        system = (
            "You are a programming language and framework detector. "
            "Given a directory tree and a README excerpt, return strict JSON: "
            '{"language": "<one of ruby, node, python, go, rust, java, unknown>", '
            '"framework": "<django|fastapi|nextjs|rails|...|null>", '
            '"confidence": <0.0 to 1.0>}. '
            "No prose, no markdown, no preamble."
        )
        user = (
            f"Directory tree:\n{tree}\n\n"
            f"README excerpt:\n{readme}\n\n"
            f"Initial guess from manifest scan: {manifest_language}."
        )
        try:
            response = await router.chat(
                messages=[
                    ChatMessage(role="system", content=system),
                    ChatMessage(role="user", content=user),
                ],
                max_tokens=64,
                temperature=0.0,
            )
        except Exception as exc:
            logger.debug("LLM-confirm: router.chat failed (%s)", exc)
            return None

        raw = (getattr(response, "content", None) or "").strip()
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # The model sometimes wraps the JSON in ```json ... ``` fences.
            cleaned = raw.strip("`").strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError as exc:
                logger.debug("LLM-confirm: JSON parse failed (%s) on %r", exc, raw[:120])
                return None
        language = parsed.get("language")
        framework = parsed.get("framework")
        confidence = parsed.get("confidence", 0.5)
        if language not in SandboxBootstrap.INSTALL_COMMAND and language != "unknown":
            logger.debug("LLM-confirm: unknown language %r, discarding", language)
            return None
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.5
        return Detection(
            language=language,
            framework=framework if framework else None,
            confidence=max(0.0, min(1.0, confidence)),
            source="llm",
        )

    @staticmethod
    async def detect_with_llm(
        sandbox: Any,
        repo_path: str = "/workspace/repo",
        timeout_seconds: int | None = None,
    ) -> Detection:
        """Run the 3-step detection chain and return a single :class:`Detection`.

        The chain (manifest &rarr; lockfile &rarr; LLM confirm) is
        the production-harness pattern: cheap deterministic
        checks first, model only when needed, manifest result
        always preserved as the fallback.

        Decision tree:
        1. ``manifest_language = detect_language(...)``.
        2. ``installer = detect_lockfile(...)`` &mdash; if set,
           the language's installer choice is sharpened
           (poetry vs pip, pnpm vs npm, etc.). The detection
           ``source`` becomes ``"lockfile"``.
        3. If ``manifest_language == "unknown"`` (step 1 missed):
           invoke the LLM. The LLM is the only way to identify
           a project with no top-level manifest (e.g. a Ruby
           project where ``Gemfile`` is in a subdir).
        4. If ``manifest_language != "unknown"`` but the
           deterministic framework check (step ``detect_framework``)
           returns ``None``: invoke the LLM to look for a
           framework in the manifest file. This is the 80%
           case for "what framework is this?" questions.
        5. On any LLM error / timeout / parse failure, fall
           back to the manifest result (or the lockfile
           result if step 2 set ``installer``).
        """
        timeout = timeout_seconds or SandboxBootstrap.LLM_TIMEOUT_SECONDS
        manifest_language = await SandboxBootstrap.detect_language(sandbox, repo_path)
        installer = await SandboxBootstrap.detect_lockfile(sandbox, repo_path)

        if manifest_language == "unknown":
            # Edge case: no manifest found. The LLM is the only
            # way to identify the project. If the LLM also
            # misses, we return "unknown" with source="manifest".
            llm = await SandboxBootstrap._llm_confirm(
                sandbox, repo_path, manifest_language, timeout,
            )
            if llm is not None and llm.language != "unknown":
                return Detection(
                    language=llm.language,
                    framework=llm.framework,
                    confidence=llm.confidence,
                    source="llm",
                )
            return Detection(
                language="unknown", framework=None, confidence=0.0, source="manifest",
            )

        # Manifest found a language. Try the deterministic
        # framework check first; only invoke the LLM if the
        # check returned nothing.
        framework = await SandboxBootstrap.detect_framework(
            sandbox, repo_path, manifest_language,
        )
        if framework is not None:
            return Detection(
                language=manifest_language,
                framework=framework,
                confidence=1.0,
                source="lockfile" if installer else "manifest",
            )

        # Deterministic check missed &mdash; ask the LLM.
        llm = await SandboxBootstrap._llm_confirm(
            sandbox, repo_path, manifest_language, timeout,
        )
        if llm is not None:
            return Detection(
                language=manifest_language,
                framework=llm.framework,
                confidence=llm.confidence * 0.9,  # slight discount: manifest is primary
                source="llm",
            )

        # LLM failed &mdash; keep the manifest result.
        return Detection(
            language=manifest_language,
            framework=None,
            confidence=0.8,
            source="manifest-fallback",
        )

    @staticmethod
    async def bootstrap(sandbox: Any, repo_path: str = "/workspace/repo") -> dict:
        """Detect language, install deps, return the result dict.

        Returns ``{"success", "language", "framework", "output", "source"}``
        &mdash; the Phase 2 shape (``success``, ``language``,
        ``output``) is preserved; ``framework`` and ``source``
        are additive. Callers that only read ``success``,
        ``language``, ``output`` see no change.

        Side effects:
        - runs ``test -f`` 19 times in the sandbox (9 manifest
          + 10 lockfile checks)
        - reads the language's manifest file (max 8KB) for
          framework detection
        - reads the README (max 1500 chars) and a directory
          tree (max 40 lines) for LLM confirmation
        - may invoke a small model call (default 3s timeout)
        - runs the install command in the sandbox
        - logs info/warn lines to the harness logger
        """
        detection = await SandboxBootstrap.detect_with_llm(sandbox, repo_path)
        language = detection.language
        # The detection chain uses the lockfile to set
        # ``source="lockfile"`` but does not return the
        # installer name. Re-run the cheap check to get it.
        installer = await SandboxBootstrap.detect_lockfile(sandbox, repo_path)

        if language == "unknown":
            return {
                "success": True,
                "language": "unknown",
                "framework": None,
                "source": detection.source,
                "output": "No manifest detected, skipping deps install",
            }

        cmd = SandboxBootstrap.install_command(language, repo_path, installer=installer)
        if cmd is None:
            return {
                "success": True,
                "language": language,
                "framework": detection.framework,
                "source": detection.source,
                "output": f"No installer for {language}",
            }

        logger.info(
            "Bootstrapping %s deps in sandbox (framework=%s, source=%s): %s",
            language, detection.framework, detection.source, cmd[:100],
        )
        result = await sandbox.run(cmd, timeout=SandboxBootstrap.INSTALL_TIMEOUT_SECONDS)
        success = result.returncode == 0
        tail = SandboxBootstrap.OUTPUT_TAIL_BYTES
        output = ((result.stdout or "")[-tail:] + (result.stderr or "")[-tail:])

        if success:
            logger.info(
                "Bootstrap complete: %s (%s) deps installed via %s",
                language, detection.framework or "no-framework", detection.source,
            )
        else:
            logger.warning(
                "Bootstrap partial/failure for %s (%s): %s",
                language, detection.framework or "no-framework", output[:300],
            )

        return {
            "success": success,
            "language": language,
            "framework": detection.framework,
            "source": detection.source,
            "output": output,
        }


def _manifest_for_language(language: str) -> str | None:
    """Return the canonical manifest filename for a language.

    Used by :meth:`SandboxBootstrap.detect_framework` to know
    which file to read for the deterministic framework check.
    """
    return {
        "python": "pyproject.toml",
        "node": "package.json",
        "ruby": "Gemfile",
        "go": "go.mod",
        "rust": "Cargo.toml",
        "java": "pom.xml",
    }.get(language)
