# Get all "use client" files from src/app and src/components
$appFiles = Get-ChildItem -Recurse -File -Path "C:\Users\AswinPremnathChandra\Documents\testai-production\src\app" | 
  Where-Object { $_.Extension -in '.tsx','.ts' } | 
  Where-Object { Select-String -Path $_.FullName -Pattern '"use client"' -Quiet } | 
  ForEach-Object { $_.FullName }

$compFiles = Get-ChildItem -Recurse -File -Path "C:\Users\AswinPremnathChandra\Documents\testai-production\src\components" | 
  Where-Object { $_.Extension -in '.tsx','.ts' } | 
  Where-Object { Select-String -Path $_.FullName -Pattern '"use client"' -Quiet } | 
  ForEach-Object { $_.FullName }

$allFiles = $appFiles + $compFiles | Sort-Object -Unique

$results = @()

foreach ($file in $allFiles) {
  if (-not (Test-Path $file)) { continue }
  $content = Get-Content -Path $file -Raw
  $lines = $content -split "`n"
  
  $issues = @()
  $hasFragileImport = $false
  $hasEarlyReturn = $false
  $hasConditionalHooks = $false
  
  # Check for next/dist imports
  if ($content -match 'from\s+["'']next/dist/') {
    $hasFragileImport = $true
    $issues += "Imports from next/dist/ (internal Next.js module that could break)"
  }
  
  # Find all hook call lines
  $hookLines = New-Object System.Collections.ArrayList
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '\b(useState|useEffect|useContext|useReducer|useCallback|useMemo|useRef|useLayoutEffect|useDeferredValue|useTransition|useId|useSyncExternalStore|useInsertionEffect|useQuery|useMutation|useQueryClient|useRouter)\s*\(') {
      [void]$hookLines.Add($i)
    }
  }
  
  if ($hookLines.Count -gt 0) {
    $firstHookLine = $hookLines[0]
    
    # Track function entry points (where braces open for component/hook functions)
    $functionDepths = New-Object System.Collections.ArrayList
    $depth = 0
    
    for ($i = 0; $i -lt $lines.Count; $i++) {
      $line = $lines[$i]
      
      # Detect function-like starts that could contain hooks
      $trimmed = $line.Trim()
      
      # Track braces
      $openCount = 0
      $closeCount = 0
      foreach ($ch in $line.ToCharArray()) {
        if ($ch -eq '{') { $openCount++ }
        if ($ch -eq '}') { $closeCount++ }
      }
      
      # If depth is 0 and we see a function/const with '=>' opening brace or just a '{' on a function line
      if ($depth -eq 0 -and $openCount -gt 0) {
        if ($trimmed -match '^(export\s+)?(default\s+)?function\s+' -or 
            $trimmed -match '=>\s*\{' -or 
            $trimmed -match '\bconst\s+\w+\s*=\s*\(' -or
            $trimmed -match '^\s*\{' -and $i -gt 0 -and ($lines[$i-1].Trim().EndsWith('=>') -or $lines[$i-1].Trim().EndsWith(')'))) {
          [void]$functionDepths.Add(@{startLine=$i; entryDepth=$depth+1})
        }
      }
      
      # Check for return statements at depth 1 (inside the component function body)
      foreach ($fd in $functionDepths) {
        $fdDepth = $fd.entryDepth
        # We're analyzing return statements in function body
      }
      
      $depth += $openCount
      $depth -= $closeCount
    }
    
    # Find return statements before first hook that are at the same depth level
    # Actually simpler: find the function body that contains the first hook,
    # then check for returns in that body before the hook
    
    # Track brace depth and look for function entries
    $searching = $true
    $depth = 0
    $fnEntryDepth = -1
    $fnEntryLine = -1
    
    for ($i = 0; $i -le $firstHookLine -and $i -lt $lines.Count; $i++) {
      $line = $lines[$i]
      
      # Count braces
      foreach ($ch in $line.ToCharArray()) {
        if ($ch -eq '{') { 
          $depth++
          # If this opens a new function body
          if ($depth -eq 1 -or ($fnEntryDepth -lt 0 -and $depth -ge 0)) {
            $prevLine = if ($i -gt 0) { $lines[$i-1].Trim() } else { "" }
            $currLine = $lines[$i].Trim()
            # Check if this brace belongs to a function/component
            if ($currLine -match '^\s*\{' -and $prevLine -match '(=>|\breturn\s*\(?|\)\s*(:\s*\w+)?\s*=>)$') {
              $fnEntryDepth = $depth
              $fnEntryLine = $i
            } elseif ($currLine -match '^(export\s+)?(default\s+)?function\s+\w+\s*\(.*\)\s*\{') {
              $fnEntryDepth = $depth
              $fnEntryLine = $i
            } elseif ($currLine -match '^(export\s+)?(default\s+)?const\s+\w+\s*=\s*\(.*\)\s*:\s*.+=>\s*\{') {
              $fnEntryDepth = $depth
              $fnEntryLine = $i
            }
          }
        }
        if ($ch -eq '}') { $depth-- }
      }
    }
    
    # Now scan for returns between function entry + 1 and first hook
    if ($fnEntryLine -ge 0) {
      $scanStart = $fnEntryLine + 1
      for ($i = $scanStart; $i -lt $firstHookLine; $i++) {
        $trimmed = $lines[$i].Trim()
        if ($trimmed -match '^return\s+' -or $trimmed -eq 'return;') {
          $hasEarlyReturn = $true
          $issues += "Early return at line $($i+1) before hook calls (would cause React error #300)"
        }
      }
    }
    
    # Simpler heuristic: scan between function declarations and first hook for return statements
    for ($i = 0; $i -lt $firstHookLine; $i++) {
      $trimmed = $lines[$i].Trim()
      # Only count returns that are inside a function body (depth >= 1)
      # and not inside nested braces that close before the first hook
    }
    
    # Alternative simpler approach: just find lines where return appears before any hook
    # within a reasonable window (not in imports, not in type defs)
    $importsEnded = $false
    $inTypeDef = $false
    for ($i = 0; $i -lt $firstHookLine; $i++) {
      $trimmed = $lines[$i].Trim()
      
      # Skip blank lines and comments
      if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith('//') -or $trimmed.StartsWith('/*')) { continue }
      
      # Once we're past imports, look for return statements
      if ($trimmed.StartsWith('import ')) { continue }
      if ($trimmed.StartsWith('"use client"') -or $trimmed.StartsWith("'use client'")) { continue }
      if ($trimmed.StartsWith('export type') -or $trimmed.StartsWith('type ') -or $trimmed.StartsWith('interface ')) { 
        $inTypeDef = $true
        continue 
      }
      if ($inTypeDef -and ($trimmed -eq '}' -or $trimmed.EndsWith('}'))) { 
        $inTypeDef = $false
        continue 
      }
      if ($trimmed.StartsWith('export {')) { continue }
      if ($trimmed.StartsWith('}')) { continue }
      
      # Now we're in component code
      # Check for return before hook
      if ($trimmed -match '^return\s+' -or $trimmed -eq 'return;' -or $trimmed.StartsWith('return (')) {
        $hasEarlyReturn = $true
        $issues += "Early return at line $($i+1) before hook calls (would cause React error #300)"
      }
    }
    
    # Check for conditional hooks
    for ($i = 0; $i -lt $lines.Count; $i++) {
      $line = $lines[$i]
      $trimmed = $line.Trim()
      
      # Hook directly inside if/else condition line
      if (($trimmed -match '\b(if|else if|else)\s*\(' -or $trimmed -match '\belse\s*\{') -and
          $trimmed -match '\b(useState|useEffect|useContext|useReducer|useCallback|useMemo|useRef|useLayoutEffect|useDeferredValue|useTransition|useId|useSyncExternalStore|useInsertionEffect|useQuery|useMutation|useQueryClient|useRouter)\s*\(') {
        $hasConditionalHooks = $true
        if (-not ($issues -contains "Hook called inside conditional block at line $($i+1)")) {
          $issues += "Hook called inside conditional block at line $($i+1)"
        }
      }
      
      # Hook inside ternary (contains both ? and hook on same line, not in a string)
      if ($trimmed -match '\?\s*.*\b(useState|useEffect|useContext|useReducer|useCallback|useMemo|useRef|useLayoutEffect|useDeferredValue|useTransition|useId|useSyncExternalStore|useInsertionEffect|useQuery|useMutation|useQueryClient|useRouter)\s*\(') {
        $hasConditionalHooks = $true
        if (-not ($issues -contains "Hook called inside ternary condition at line $($i+1)")) {
          $issues += "Hook called inside ternary condition at line $($i+1)"
        }
      }
      
      # Hook after && short-circuit
      if ($trimmed -match '\&\&\s*\b(useState|useEffect|useContext|useReducer|useCallback|useMemo|useRef|useLayoutEffect|useDeferredValue|useTransition|useId|useSyncExternalStore|useInsertionEffect|useQuery|useMutation|useQueryClient|useRouter)\s*\(') {
        $hasConditionalHooks = $true
        if (-not ($issues -contains "Hook called after && (short-circuit conditional) at line $($i+1)")) {
          $issues += "Hook called after && (short-circuit conditional) at line $($i+1)"
        }
      }
      
      # Hook inside catch block
      if ($trimmed -match '\bcatch\s*\(' -and $trimmed -match '\b(useState|useEffect|useContext|useReducer|useCallback|useMemo|useRef|useLayoutEffect|useDeferredValue|useTransition|useId|useSyncExternalStore|useInsertionEffect|useQuery|useMutation|useQueryClient|useRouter)\s*\(') {
        $hasConditionalHooks = $true
        if (-not ($issues -contains "Hook called inside catch block at line $($i+1)")) {
          $issues += "Hook called inside catch block at line $($i+1)"
        }
      }
    }
    
    # Check for hooks inside callback/hook bodies that are conditional
    # Look for if blocks wrapping hooks
    $braceDepth = 0
    $inConditionalBlock = @()  # stack of conditional block depths
    
    for ($i = 0; $i -lt $lines.Count; $i++) {
      $trimmed = $lines[$i].Trim()
      
      # Track if/else entries
      if ($trimmed -match '\bif\s*\(') {
        $inConditionalBlock += @{type='if'; depth=$braceDepth; line=$i}
      }
      
      # Process braces
      foreach ($ch in $lines[$i].ToCharArray()) {
        if ($ch -eq '{') { $braceDepth++ }
        if ($ch -eq '}') { 
          $braceDepth--
          # Pop any conditional blocks that close at this depth
          while ($inConditionalBlock.Count -gt 0 -and $inConditionalBlock[-1].depth -ge $braceDepth) {
            [void]$inConditionalBlock.Pop()
          }
        }
      }
      
      # Check if hook is on a line inside a conditional block
      if ($inConditionalBlock.Count -gt 0 -and 
          $trimmed -match '\b(useState|useEffect|useContext|useReducer|useCallback|useMemo|useRef|useLayoutEffect|useDeferredValue|useTransition|useId|useSyncExternalStore|useInsertionEffect|useQuery|useMutation|useQueryClient|useRouter)\s*\(' -and
          -not $trimmed.StartsWith('//') -and
          -not ($trimmed -match '^\s*\*')) {
        $hasConditionalHooks = $true
        $closestConditional = $inConditionalBlock[-1]
        $issueStr = "Hook called inside if block (conditional) at line $($i+1), if opened at line $($closestConditional.line+1)"
        if (-not ($issues -contains $issueStr)) {
          $issues += $issueStr
        }
      }
    }
  }
  
  $isClean = ($issues.Count -eq 0)
  
  $results += [PSCustomObject]@{
    file = $file
    issues = $issues
    has_fragile_import = $hasFragileImport
    has_early_return_before_hooks = $hasEarlyReturn
    has_conditional_hooks = $hasConditionalHooks
    is_clean = $isClean
  }
}

$results | ConvertTo-Json -Depth 3
