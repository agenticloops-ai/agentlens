# AgentLens

Profile AI agents by intercepting LLM API traffic through a local MITM proxy. Understand how agents work: prompts, tools, MCP, token usage, costs, and timing — all in a real-time web UI.

## Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/)
- Node.js >= 18

## Install

```bash
git clone https://github.com/agenticloops/agentlens.git
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

```
agentlens start [OPTIONS]

Options:
  --proxy-port   INT   Port for the MITM proxy          [default: 8080]
  --web-port     INT   Port for the web UI               [default: 8081]
  --host         TEXT  Host to bind to                   [default: 127.0.0.1]
  --session-name TEXT  Name for this profiling session   [default: auto-generated]
  --db-path      TEXT  Path to SQLite database           [default: ~/.agentlens/data.db]
  --open/--no-open     Open web UI in browser            [default: --open]
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

### What Gets Captured

| Provider | Hosts | Paths |
|----------|-------|-------|
| OpenAI | `api.openai.com` | `/v1/chat/completions`, `/v1/responses` |
| Anthropic | `api.anthropic.com` | `/v1/messages` |

All other HTTP traffic passes through the proxy transparently without being captured or stored.

## License

MIT
