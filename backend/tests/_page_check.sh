urls="
/
/chat
/jobs
/dashboard
/sandbox
/history
/sessions
/settings
/models
/agents
"

for p in $urls; do
  out=$(wget -qO- "http://localhost:3000$p" 2>&1)
  size=${#out}
  first200=$(echo "$out" | head -c 200)
  echo "=== $p (size=$size) ==="
  echo "$first200"
  echo
done
