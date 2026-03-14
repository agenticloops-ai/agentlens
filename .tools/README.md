# alens

Tmux launcher that starts AgentLens in one pane and your agent in another, with proxy env vars automatically injected so all LLM API traffic is captured.

## Prerequisites

- [mitmproxy](https://mitmproxy.org/) CA certificate installed (`~/.mitmproxy/mitmproxy-ca-cert.pem`)
- `tmux` installed
- `uv` installed with AgentLens available

## Usage

```
./alens [OPTIONS] -- COMMAND [ARGS...]
```

| Flag | Description |
|------|-------------|
| `-o DIR` | Output directory (default: `results`) |
| `-s NAME` | Session name override |
| `-l LABEL` | Label for the capture session |
| `-T HOST` | Transparent capture targeting HOST (requires sudo, repeatable) |
| `-S` | Enable macOS system proxy (for GUI apps that ignore env vars) |
| `-E` | Inject `--proxy-server` flag for Electron apps |
| `-H HOST` | Override proxy host (default: auto-detected IP) |
| `-P PORT` | Override proxy port (default: `8080`) |

## Examples

### Claude Code (CLI)

```bash
./alens -- claude -p "refactor the auth module"
```

### Claude Code (interactive session)

```bash
./alens -s my-session -- claude
```

### Claude Desktop (Electron)

```bash
./alens -E -- /Applications/Claude.app/Contents/MacOS/Claude
```

### Cursor (Electron)

```bash
./alens -E -- /Applications/Cursor.app/Contents/MacOS/Cursor
```

### Windsurf (Electron)

```bash
./alens -E -- /Applications/Windsurf.app/Contents/MacOS/Electron
```

### CoWork VM (transparent capture)

CoWork runs inside a VM and ignores proxy env vars. Use `-T` to intercept traffic at the network level via `pf` rules (will prompt for sudo):

```bash
./alens -T api.anthropic.com -l cowork -- open /Applications/CoWork.app
```

### Multiple transparent targets

Transparent mode requires sudo — you'll be prompted once at launch:

```bash
./alens -T api.anthropic.com -T api.openai.com -- open /Applications/SomeApp.app
```

### OpenAI-based agents (Python)

```bash
./alens -- python my_openai_agent.py
```

### LangChain / LangGraph agent

```bash
./alens -- python langgraph_agent.py
```

### CrewAI

```bash
./alens -- crewai run
```

### Aider

```bash
./alens -- aider --model claude-3.5-sonnet
```

### Custom agent with named output

```bash
./alens -o results/experiment-1 -s experiment-1 -- python my_agent.py
```

### macOS system proxy (native apps)

```bash
./alens -S -- open /Applications/SomeApp.app
```

### Remote proxy (agent on another machine)

```bash
# On the capture host
./alens -H 0.0.0.0 -- echo "proxy ready"

# On the agent host
HTTP_PROXY=http://capture-host:8080 HTTPS_PROXY=http://capture-host:8080 \
  python my_agent.py
```

## How it works

**Explicit proxy mode** (default): Starts `agentlens wait` and launches your command with `HTTP_PROXY`/`HTTPS_PROXY` env vars pointing at the proxy. Works for any agent that respects proxy env vars.

**Transparent mode** (`-T`): Starts `agentlens capture --mode transparent` which sets up macOS `pf` rules to intercept traffic at the network level. No proxy env vars needed — works for apps running in VMs or that otherwise ignore proxy settings. Requires `sudo`.

The web UI is available at `http://localhost:8081` while the session is running.
