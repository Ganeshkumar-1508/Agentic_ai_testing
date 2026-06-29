<!--
name: 'Tool Description: Bash (sandbox — tmpdir)'
description: Use $TMPDIR for temporary files in sandbox mode
ccVersion: 2.1.154
-->
For temporary files, always use the `$TMPDIR` environment variable. TMPDIR is set to the same sandbox-writable directory for both sandboxed and unsandboxed commands. Do NOT use `/tmp` directly - use `$TMPDIR` instead.
