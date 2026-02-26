# AgentLens

Profile AI agents by intercepting LLM API traffic through a local MITM proxy. Understand how agents work: prompts, tools, MCP, token usage, costs, and timing — all in a real-time web UI.


![AgentLens](./docs/agentlens.gif)


## Supported Providers

| Provider | Hosts | Endpoints |
|----------|-------|-----------|
| **Anthropic** | `api.anthropic.com` | `/v1/messages` |
| **OpenAI** | `api.openai.com` | `/v1/chat/completions`, `/v1/responses` |
| **Google Gemini** | `generativelanguage.googleapis.com`, `cloudcode-pa.googleapis.com` | `:generateContent`, `:streamGenerateContent` |
| **GitHub Copilot** | `api.individual.githubcopilot.com`, `api.business.githubcopilot.com`, `api.enterprise.githubcopilot.com` | All of the above (auto-detected by host) |

All other HTTP traffic passes through the proxy transparently without being captured or stored.

Providers are auto-discovered plugins — adding a new one requires no changes to core code.

## Quickstart

```bash
# 1. Install
pip install agentlens-proxy

# 2. Start the profiler (opens web UI automatically)
agentlens start

# 3. In another terminal, run your agent through the proxy
HTTP_PROXY=http://127.0.0.1:8080 \
HTTPS_PROXY=http://127.0.0.1:8080 \
NODE_TLS_REJECT_UNAUTHORIZED=0 \
claude
```

That's it — open `http://127.0.0.1:8081` to see every LLM request in real time.

## Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/)
- Node.js >= 18

## Install

```bash
pip install agentlens-proxy
```

### From source

```bash
git clone https://github.com/agenticloops-ai/agentlens.git
cd agentlens
make install
```

## Run

```bash
# Start the proxy (port 8080) and web UI (port 8081)
agentlens start

# Or equivalently
uv run agentlens start
make dev
```

This opens the web UI at `http://127.0.0.1:8081` and starts the MITM proxy on port `8080`.

### CLI Options

#### `agentlens start`

Start the proxy and web UI.

```
agentlens start [OPTIONS]

Options:
  --proxy-port    INT   Port for the MITM proxy          [default: 8080]
  --web-port      INT   Port for the web UI               [default: 8081]
  --host          TEXT  Host to bind to                   [default: 127.0.0.1]
  --session-name  TEXT  Name for this profiling session   [default: auto-generated]
  --db-path       TEXT  Path to SQLite database           [default: ~/.agentlens/data.db]
  --open/--no-open      Open web UI in browser            [default: --open]
```

#### `agentlens wait`

Start proxy and wait for Ctrl+C, then export results. Useful for headless/scripted capture.

```
agentlens wait [OPTIONS]

Options:
  --output        TEXT  Output directory for exported files   [default: results]
  --formats       TEXT  Comma-separated export formats        [default: json,markdown,csv]
  --session-name  TEXT  Override auto-generated session name  [default: auto-generated]
  --proxy-port    INT   Port for the MITM proxy              [default: 8080]
  --web-port      INT   Port for the web UI                  [default: 8081]
  --host          TEXT  Host to bind to                      [default: 127.0.0.1]
  --db-path       TEXT  Path to SQLite database              [default: ~/.agentlens/data.db]
  --web/--no-web        Start web UI alongside proxy         [default: --web]
  --open/--no-open      Open web UI in browser               [default: --no-open]
```

Example:

```bash
# Terminal 1 — start proxy and wait
agentlens wait --output results/claude-codegen

# Terminal 2 — run your agent with proxy env vars
HTTP_PROXY=http://127.0.0.1:8080 \
HTTPS_PROXY=http://127.0.0.1:8080 \
NODE_EXTRA_CA_CERTS=~/.mitmproxy/mitmproxy-ca-cert.pem \
claude -p "refactor the auth module"

# Press Ctrl+C in Terminal 1 when done — results are exported to:
#   results/claude-codegen/2026-02-25T14-30-00/
```

#### `agentlens export`

Export a previously captured session from the database.

```
agentlens export SESSION [OPTIONS]

Arguments:
  SESSION              Session ID or session name

Options:
  --output-dir    TEXT  Output directory                      [default: exports]
  --formats       TEXT  Comma-separated export formats        [default: json,markdown,csv]
  --db-path       TEXT  Path to SQLite database               [default: ~/.agentlens/data.db]
```

Example:

```bash
agentlens export "Session 2026-02-25 14:30" --output-dir exports/
```

## Certificate Setup

On first run, mitmproxy generates a CA certificate at `~/.mitmproxy/`. You need to either trust this certificate or disable SSL verification for your agent to work through the proxy.

### Trust the certificate system-wide (macOS)

```bash
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain \
  ~/.mitmproxy/mitmproxy-ca-cert.pem
```

### Trust the certificate system-wide (Linux)

```bash
# Debian/Ubuntu
sudo cp ~/.mitmproxy/mitmproxy-ca-cert.pem /usr/local/share/ca-certificates/mitmproxy.crt
sudo update-ca-certificates

# RHEL/Fedora
sudo cp ~/.mitmproxy/mitmproxy-ca-cert.pem /etc/pki/ca-trust/source/anchors/mitmproxy.pem
sudo update-ca-trust
```

### Per-tool certificate environment variables

Instead of trusting system-wide, you can point individual tools to the cert:

```bash
# Python (requests / urllib3)
export REQUESTS_CA_BUNDLE=~/.mitmproxy/mitmproxy-ca-cert.pem

# Python (httpx)
export SSL_CERT_FILE=~/.mitmproxy/mitmproxy-ca-cert.pem

# Node.js
export NODE_EXTRA_CA_CERTS=~/.mitmproxy/mitmproxy-ca-cert.pem

# curl
curl --cacert ~/.mitmproxy/mitmproxy-ca-cert.pem ...
```

### Skip verification entirely (not recommended for production)

```bash
# Node.js
export NODE_TLS_REJECT_UNAUTHORIZED=0

# Python
export PYTHONHTTPSVERIFY=0
```

## Usage

Start the profiler in one terminal, then launch your agent in another with proxy environment variables set. The profiler captures all LLM API traffic transparently — no code changes needed.

### Claude Code

```bash
# Terminal 1
agentlens start --session-name "claude-code-debug-session"

# Terminal 2
HTTP_PROXY=http://127.0.0.1:8080 \
HTTPS_PROXY=http://127.0.0.1:8080 \
NODE_EXTRA_CA_CERTS=~/.mitmproxy/mitmproxy-ca-cert.pem \
claude
```

Or skip cert verification:

```bash
HTTP_PROXY=http://127.0.0.1:8080 \
HTTPS_PROXY=http://127.0.0.1:8080 \
NODE_TLS_REJECT_UNAUTHORIZED=0 \
claude
```

### Codex CLI

```bash
HTTP_PROXY=http://127.0.0.1:8080 \
HTTPS_PROXY=http://127.0.0.1:8080 \
NODE_EXTRA_CA_CERTS=~/.mitmproxy/mitmproxy-ca-cert.pem \
codex
```

### OpenAI Python SDK

```bash
HTTP_PROXY=http://127.0.0.1:8080 \
HTTPS_PROXY=http://127.0.0.1:8080 \
REQUESTS_CA_BUNDLE=~/.mitmproxy/mitmproxy-ca-cert.pem \
python my_agent.py
```

### Anthropic Python SDK

```bash
HTTP_PROXY=http://127.0.0.1:8080 \
HTTPS_PROXY=http://127.0.0.1:8080 \
SSL_CERT_FILE=~/.mitmproxy/mitmproxy-ca-cert.pem \
python my_claude_agent.py
```

### LangChain / LlamaIndex / Any Python Agent

```bash
HTTP_PROXY=http://127.0.0.1:8080 \
HTTPS_PROXY=http://127.0.0.1:8080 \
REQUESTS_CA_BUNDLE=~/.mitmproxy/mitmproxy-ca-cert.pem \
SSL_CERT_FILE=~/.mitmproxy/mitmproxy-ca-cert.pem \
python my_langchain_agent.py
```

### Node.js Agents (Vercel AI SDK, etc.)

```bash
HTTP_PROXY=http://127.0.0.1:8080 \
HTTPS_PROXY=http://127.0.0.1:8080 \
NODE_EXTRA_CA_CERTS=~/.mitmproxy/mitmproxy-ca-cert.pem \
node my_agent.js
```

### curl (Quick Test)

```bash
curl https://api.anthropic.com/v1/messages \
  -x http://127.0.0.1:8080 \
  --cacert ~/.mitmproxy/mitmproxy-ca-cert.pem \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-haiku-4",
    "max_tokens": 128,
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Advanced: tmux single-command workflow

Use tmux to run the proxy and your agent side-by-side in a single session. When the agent exits, the proxy is automatically stopped and results are exported.

```bash
# 1. Start proxy in a detached tmux session
tmux new-session -d -s agentlens \
  'agentlens wait --output results/my-run --no-open'

# 2. Split a pane that runs the agent, then sends Ctrl+C to the proxy on exit
tmux split-window -h -t agentlens \
  'sleep 2 && \
   HTTP_PROXY=http://127.0.0.1:8080 \
   HTTPS_PROXY=http://127.0.0.1:8080 \
   NODE_EXTRA_CA_CERTS=~/.mitmproxy/mitmproxy-ca-cert.pem \
   SSL_CERT_FILE=~/.mitmproxy/mitmproxy-ca-cert.pem \
   REQUESTS_CA_BUNDLE=~/.mitmproxy/mitmproxy-ca-cert.pem \
   claude -p "refactor the auth module"; \
   tmux send-keys -t agentlens:0.0 C-c'

# 3. Attach to watch it live
tmux attach -t agentlens
```

What happens:
- **Left pane** — `agentlens wait` starts the proxy and web UI, waits for Ctrl+C
- **Right pane** — waits 2s for the proxy to be ready, then runs your agent with all proxy/cert env vars
- When the agent finishes, `tmux send-keys C-c` signals the proxy to stop and export results
- Results are written to `results/my-run/<timestamp>/`

To also open the web UI while capturing:

```bash
tmux new-session -d -s agentlens \
  'agentlens wait --output results/my-run --open'
```

You can swap `claude -p "..."` for any command — `python my_agent.py`, `codex`, `node agent.js`, etc.

### Reusable shell function

Add this to your `.bashrc` / `.zshrc` for a one-liner:

```bash
lens-run() {
  local output="results" session_name=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -o) output="$2"; shift 2 ;;
      -s) session_name="$2"; shift 2 ;;
      --) shift; break ;;
      *)  break ;;
    esac
  done
  if [[ $# -eq 0 ]]; then
    echo "Usage: lens-run [-o DIR] [-s NAME] -- COMMAND [ARGS...]" >&2
    return 1
  fi

  local wait_cmd="agentlens wait --output ${output} --no-open"
  [[ -n "$session_name" ]] && wait_cmd+=" --session-name ${session_name}"

  local proxy="http://127.0.0.1:8080"
  local ca="${HOME}/.mitmproxy/mitmproxy-ca-cert.pem"

  tmux kill-session -t agentlens 2>/dev/null || true
  tmux new-session -d -s agentlens "$wait_cmd"
  tmux split-window -h -t agentlens \
    "sleep 2 && \
     HTTP_PROXY=${proxy} HTTPS_PROXY=${proxy} \
     NODE_EXTRA_CA_CERTS=${ca} SSL_CERT_FILE=${ca} \
     REQUESTS_CA_BUNDLE=${ca} CURL_CA_BUNDLE=${ca} \
     $*; \
     tmux send-keys -t agentlens:0.0 C-c"
  tmux select-pane -t agentlens:0.1
  tmux attach -t agentlens
}
```

Then:

```bash
lens-run -- claude -p "refactor the auth module"
lens-run -o results/my-test -s my-test -- python my_agent.py
```

## License

MIT
