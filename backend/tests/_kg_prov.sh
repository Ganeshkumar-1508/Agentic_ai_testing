for d in /app/agent_workspace/knowledge-graphs/*/; do
  name=$(basename "$d")
  echo "=== $name ==="
  cat "${d}provenance.json" 2>/dev/null
  echo
  cat "${d}metadata.json" 2>/dev/null
  echo
done
