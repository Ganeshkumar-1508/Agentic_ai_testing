"""Check each frontend page for data flow issues."""
import re
from pathlib import Path

SRC = Path(r"C:\Users\AswinPremnathChandra\Documents\testai-production\src\app\(dashboard)")
COMP = Path(r"C:\Users\AswinPremnathChandra\Documents\testai-production\src\components")

def read_file(path):
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except:
        return ""

def find_api_calls(content):
    """Find all API endpoint references in a file."""
    patterns = [
        r'api\.(?:get|post)\s*\(\s*["\']([^"\']+)["\']',
        r'fetch\s*\(\s*["\'](/api/[^"\']+)["\']',
        r'queryFn.*?api\.(?:get|post)\s*\(\s*["\']([^"\']+)["\']',
        r'"/api/([^"]+)"',
    ]
    apis = set()
    for pat in patterns:
        for m in re.finditer(pat, content):
            apis.add(m.group(1) if "(" in pat else m.group(0))
    return sorted(apis)

def check_data_flow(page_name, page_content, provider_content=""):
    """Check if data flows from API to component."""
    issues = []
    
    # Check for useQuery
    has_usequery = "useQuery" in page_content or "useQuery" in provider_content
    
    # Check for data variable usage
    has_data_var = "data" in page_content and ("data." in page_content or "{ data" in page_content)
    
    # Check for loading/error states
    has_loading = "isLoading" in page_content or "isFetching" in page_content
    has_error = "error" in page_content and ("isError" in page_content or "fetchError" in page_content)
    
    # Check for empty state
    has_empty = "EmptyState" in page_content or "no data" in page_content.lower() or "empty" in page_content.lower()
    
    if has_usequery and not has_data_var:
        issues.append("useQuery defined but data variable not used")
    if has_usequery and not has_loading:
        issues.append("no loading state")
    if has_usequery and not has_error:
        issues.append("no error state")
    
    return {
        "has_usequery": has_usequery,
        "has_data_var": has_data_var,
        "has_loading": has_loading,
        "has_error": has_error,
        "has_empty": has_empty,
        "issues": issues,
    }

# Pages to check
pages_to_check = [
    "dashboard", "jobs", "chat", "sessions", "sandbox",
    "knowledge-graph", "test-cases", "quality", "pull-requests",
    "kanban", "observability", "tools", "skills", "artifacts",
]

print("=" * 70)
print("PAGE COMPONENT DATA FLOW CHECK")
print("=" * 70)

for page_name in pages_to_check:
    page_path = SRC / page_name / "page.tsx"
    if not page_path.exists():
        print(f"\n  {page_name}: NO page.tsx found")
        continue
    
    content = read_file(page_path)
    apis = find_api_calls(content)
    flow = check_data_flow(page_name, content)
    
    # Check if page uses a provider
    providers = re.findall(r'useDashboard|useSession|useKanban|useKnowledgeGraph', content)
    
    status = "OK" if flow["has_usequery"] and flow["has_data_var"] else "ISSUE"
    details = []
    if flow["has_usequery"]:
        details.append("useQuery")
    if flow["has_data_var"]:
        details.append("data used")
    if flow["has_loading"]:
        details.append("loading")
    if flow["has_error"]:
        details.append("error")
    if flow["has_empty"]:
        details.append("empty-state")
    
    print(f"\n  {page_name}")
    print(f"    APIs: {len(apis)} endpoints")
    for a in apis[:5]:
        print(f"      -> {a}")
    if len(apis) > 5:
        print(f"      ... +{len(apis)-5} more")
    print(f"    Components: {', '.join(details)}")
    if providers:
        print(f"    Providers: {', '.join(providers)}")
    if flow["issues"]:
        for issue in flow["issues"]:
            print(f"    ISSUE: {issue}")
    if not flow["issues"]:
        print(f"    Status: ✅ OK")
