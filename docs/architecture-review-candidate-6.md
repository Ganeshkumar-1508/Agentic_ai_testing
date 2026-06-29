# Candidate 6: Consolidate 5 integration mechanisms into a unified connector/adapter surface

**Strength**: Worth exploring | **Category**: module organization / interface consolidation

---

## Research sources (10)

### Agent harness integration patterns

1. **OpenAI Agents SDK — Connector Registry** — Single registry for all external service integrations. One place to configure, one auth model, one discovery mechanism. https://openai.com/index/introducing-agentkit/

2. **Pantheon / r3moteBee agent-harness** — Uses **MCP** as universal connector mechanism. "Compliant Model Context Protocol (MCP) client supporting API keys and OAuth 2.1. Map different models to distinct roles." One protocol for all external service access — Slack, GitHub, databases all go through MCP. https://github.com/r3moteBee/pantheon

3. **OpenClaw — Integrated runtime surface** — "Model discovery, tool wiring, prompt assembly, session management, and channel delivery share one integrated runtime surface." Channel delivery is one module in an integrated runtime, not 5 separate mechanisms. https://docs.openclaw.ai/concepts/agent

4. **Awesome Harness Engineering — MCP section** — MCP listed as the emerging standard for "giving agents structured, controlled access to tools and data sources." 1,000+ live connectors on MCP.so marketplace. The industry is converging on MCP as the universal integration protocol. https://github.com/Jiaaqiliu/Awesome-Harness-Engineering

5. **OpenClaw** — "Model discovery, tool wiring, prompt assembly, session management, and channel delivery share one integrated runtime surface." All integrations go through one runtime, not separate channels/webhooks/delivery. https://docs.openclaw.ai/concepts/agent

6. **CodeRabbit — Agent for Slack** — Single integration point for Slack. One "Agent for Slack" surface, not separate channels + webhooks + delivery + CI + integrations modules.

7. **Hermes Agent API Server** — Single endpoint surface: `POST /v1/chat/completions`, `POST /v1/runs`, `GET /v1/runs/{id}/events`. All external integrations go through MCP connectors or the API — no separate channels/webhooks/delivery modules. https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration

8. **htek.dev — All Agent Harnesses Compared** — Every major harness (Copilot, Codex, Claude Code, Cursor) uses either MCP or a Connector Registry for external integrations. None has separate channels + webhooks + CI + delivery + integrations modules. https://htek.dev/articles/all-agent-harnesses-live-comparison

9. **Codebase audit — 5 integration mechanisms, Slack×3** (see below)

10. **CONTEXT.md — MCP** — "MCP servers in `<cwd>/.testai/mcp.json`" listed as a first-class harness primitive. The harness already has MCP — but the integration modules don't use it.

---

## Codebase evidence

### 5 integration mechanisms, same problem

| Module | What | Slack? | Frontend page | Base class |
|---|---|---|---|---|
| `channels/` | IM channels (Slack) | ✅ SlackChannel (202 lines) | `/channels` | `Channel` (ABC) |
| `webhooks/` | GitHub PR webhooks | ❌ | WebhookConfig (settings) | None |
| `ci/` | Git providers (61 symbols) | ❌ | CICDSetup (settings) | None |
| `integrations/` | Pipeline result posting | ✅ `post_slack_message` (132 lines) | IntegrationSettings | None |
| `delivery/` | Notification delivery | ✅ SlackAdapter (via registry) | None | `BaseAdapter` (ABC) |

### Slack appears 3 times, with 3 different APIs

| File | Purpose | Auth | API |
|---|---|---|---|
| `channels/slack.py` | Real-time IM (inbound + outbound) | Socket Mode tokens | `Channel.start()`, `.stop()`, `.send()` |
| `integrations/slack.py` | Post run results to Slack channel | Bot token from `integration_configs` table | `post_slack_message()`, `post_run_result_to_slack()` |
| `delivery/adapters/slack.py` | Outbound notification via router | DB-based config | `BaseAdapter.send()` via `DeliveryRouter` |

Three different Slack modules, three different auth mechanisms, three different APIs, three different config stores — all in the same codebase.

### The pattern duplication

Each integration mechanism reinvents:

| Concern | channels/ | webhooks/ | ci/ | integrations/ | delivery/ |
|---|---|---|---|---|---|
| Config model | Dict-based | None | GitProvider config | DB table | AdapterConfig Pydantic |
| Auth | Connection token | GitHub secret | OAuth/SSH | Bot token | Platform config row |
| Error handling | Per-channel | Per-hook | Per-provider | try/except | BaseAdapter.on_error |
| Discovery | Import-time | None | None | None | ADAPTER_REGISTRY dict |
| Testing | Mock channel | Mock webhook | Mock provider | Mock HTTP | Mock adapter |

### The contraction

Unify behind the harness's existing **MCP** mechanism (CONTEXT.md: "MCP servers in `<cwd>/.testai/mcp.json`"). The `mcp/` sub-package already has a client, config manager, OAuth manager, server, and server_mcp. Slack, GitHub, email, Teams, Telegram all become MCP server definitions — one config file, one auth model, one discovery mechanism.

Or, if MCP is too heavy for simple notifications, unify behind `delivery/`'s adapter registry pattern (which already has a clean `BaseAdapter` + `ADAPTER_REGISTRY` + lazy construction). Fold `channels/`, `integrations/`, and `delivery/` into one `connectors/` sub-package.
