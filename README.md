# NetPilot — Setup, Startup & Live Demo Runbook

**NetPilot** is a local network-operations console with a Docker network lab, a Python self-healing controller, a FastAPI control API, a React/Vite dashboard, read-only AI investigations using Groq + MCP, and optional AWS event forwarding.

This runbook is written for **Windows PowerShell**, using the existing project directory **`A:\NetPilot`**. Run PowerShell commands from that folder unless a section says otherwise. Route-fault commands are **only for the isolated NetPilot Docker lab**, never a host or production network.

## 1. Prerequisites

- Docker Desktop with the **Linux container engine** running.
- Python and `pip` (the existing project has used Python 3.13).
- Node.js and npm (Node.js 20+ recommended for the Vite frontend).
- For AI Operations: a valid Groq API key and internet access.
- **Optional AWS demo:** AWS CLI, configured AWS credentials, and your existing SQS/Lambda/DynamoDB resources. AWS usage may incur charges.

Check the tools:

```powershell
docker info
docker compose version
python --version
node --version
npm --version
```

If `docker info` cannot connect to `dockerDesktopLinuxEngine`, **open Docker Desktop** and confirm its engine is running before continuing.

## 2. One-time installation

### Python backend and agents

Open PowerShell at the project root:

```powershell
cd A:\NetPilot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

> If `.venv` already exists with the required packages, simply activate it. If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process Bypass` in that terminal and activate again.

### React frontend

```powershell
cd A:\NetPilot\dashboard
npm install
cd A:\NetPilot
```

You only need to install dependencies again after changing dependencies, creating a new virtual environment, or cloning onto a new computer.

## 3. Create or retrieve your NetPilot control token

NetPilot **does not supply a universal/default token**. The backend validates the `X-NetPilot-Token` header against the `NETPILOT_CONTROL_TOKEN` environment variable.

Generate a strong, random token (first-time setup only):

```powershell
cd A:\NetPilot
.\.venv\Scripts\Activate.ps1
$env:NETPILOT_CONTROL_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:NETPILOT_CONTROL_TOKEN | Set-Clipboard
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Copy the output privately into a **project-root** `.env` file (`A:\NetPilot\.env`). Example contents (use **your real secret values**, not the placeholders):

```dotenv
NETPILOT_CONTROL_TOKEN=PASTE_YOUR_GENERATED_TOKEN_HERE
NETPILOT_AI_PROVIDER=groq
GROQ_API_KEY=PASTE_YOUR_GROQ_API_KEY_HERE
GROQ_MODEL=openai/gpt-oss-20b

# Optional; defaults used by NetPilot's AWS integration:
NETPILOT_AWS_REGION=ap-south-1
NETPILOT_SQS_QUEUE=netpilot-incidents-dev
```

If you already have `.env`, **keep your existing token and Groq key**; do not regenerate them on every startup. The backend's AI module loads the project-root `.env` during import. **Restart FastAPI after editing `.env`.** A PowerShell environment variable with the same name can override `.env`; use one consistent value.

To display **only the control token** from `.env` for copying into the local dashboard:

```powershell
cd A:\NetPilot
(Get-Content .\.env | Where-Object { $_ -match '^NETPILOT_CONTROL_TOKEN=' }) -replace '^NETPILOT_CONTROL_TOKEN=', ''
```

Do not paste the token into GitHub, screenshots, bug reports, or chat. The root `.env` is ignored by Git; check `git status` before pushing changes.

## 4. Daily startup — 3 terminals + browser

**Start Docker Desktop first.** Then use separate PowerShell terminals:

### Terminal 1 — Docker lab

```powershell
cd A:\NetPilot
docker compose -f .\lab\compose.yaml up -d --build
docker compose -f .\lab\compose.yaml ps
```

The four lab services are `client`, `server`, `router-a`, and `router-b`. `up -d --build` is safe for the normal lab startup; it builds missing images. For a faster repeat startup when images already exist, use `docker compose -f .\lab\compose.yaml up -d`.

### Terminal 2 — FastAPI backend (leave running)

```powershell
cd A:\NetPilot
.\.venv\Scripts\Activate.ps1
$env:NETPILOT_CONTROL_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:NETPILOT_CONTROL_TOKEN | Set-Clipboard
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Check backend health from another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/status
```

API documentation: <http://127.0.0.1:8000/docs>.

### Terminal 3 — React frontend (leave running)

```powershell
cd A:\NetPilot\dashboard
npm run dev
```

Open **<http://127.0.0.1:5173/>**.

### Browser — unlock controls and start automation

1. Go to **Settings → Access and Safeguards → UNLOCK CONTROLS** (or use the dashboard's token unlock control).
2. Paste the same `NETPILOT_CONTROL_TOKEN` configured for the backend. It is held in browser memory and must be entered again after a page reload.
3. In **Control Center**, confirm the four Docker nodes are running. Use **START LAB** if the containers exist but are stopped.
4. **Before starting the controller**, click **RESET PRIMARY** and confirm the action. This sets the client and server routes through Router A. The backend intentionally forbids manual reset while its controller is running.
5. In **Control Center → MANAGED SERVICES**, start **NETPILOT v4 AGENT** (controller) using its play button.
6. **Optional AWS:** Start **AWS EVENT FORWARDER** only after AWS CLI access and the SQS queue are ready.

> **Important:** When you start the controller or forwarder from the dashboard, don't simultaneously start the same script manually in another terminal. The API only knows about processes **it** started and supervises.

## 5. Network topology and healthy-state checks

| Node | Address | Purpose |
|---|---|---|
| Client | `10.66.1.10` | Sends test traffic to server |
| Router A (client/server LANs) | `10.66.1.2` / `10.66.2.2` | Preferred path |
| Router B (client/server LANs) | `10.66.1.3` / `10.66.2.3` | Backup path |
| Server | `10.66.2.10` | Receives test traffic |

Normal path: `client → Router A → server`, with the return traffic passing back through Router A.

Run the following commands in **another PowerShell terminal at `A:\NetPilot`**:

```powershell
docker compose -f .\lab\compose.yaml exec -T client ip -4 route get 10.66.2.10
docker compose -f .\lab\compose.yaml exec -T server ip -4 route get 10.66.1.10
docker compose -f .\lab\compose.yaml exec -T client ping -c 3 10.66.2.10
```

Expected Router A gateways:

- Client route to server subnet `10.66.2.0/24` → `via 10.66.1.2`.
- Server route to client subnet `10.66.1.0/24` → `via 10.66.2.2`.
- Ping succeeds; Control Center reports a reachable network and Router A as active.

## 6. LIVE DEMO A — Deliberately create a route mismatch and show self-healing

**Goal:** Break the client's route in the **isolated Docker lab** so NetPilot detects the connectivity failure, diagnoses `ROUTE_MISMATCH`, and restores a verified route.

**Before injecting the fault:** Ensure all four Docker containers and **NETPILOT v4 AGENT** are running, and Router A is the healthy primary path.

### Inject a wrong client gateway

```powershell
cd A:\NetPilot
docker compose -f .\lab\compose.yaml exec -T client ip route replace 10.66.2.0/24 via 10.66.1.99
```

`10.66.1.99` is an intentionally wrong **lab-only** next hop (assuming that address is unused). It is not Router A or Router B. This breaks the client-to-server route while the server still points to Router A.

Check the injected gateway and connectivity **immediately** (the running controller may repair it quickly):

```powershell
docker compose -f .\lab\compose.yaml exec -T client ip -4 route get 10.66.2.10
docker compose -f .\lab\compose.yaml exec -T client ping -c 2 10.66.2.10
```

### Observe the automated recovery

The controller probes approximately every **5 seconds**, with a **3-failure threshold** before it opens a recovery incident. In Control Center, Recovery Tracker, and Event Logs look for:

```text
CONNECTIVITY_FAILURE
INCIDENT_CREATED
FAULT_DIAGNOSED          (fault_type: ROUTE_MISMATCH)
RECOVERY_ATTEMPT
ROUTE_CHANGE_STARTED
ROUTE_CHANGE_SUCCESS
INCIDENT_RESOLVED
```

The exact timeline depends on when the fault is injected and whether a healthy router is available. The controller repairs the **client and server endpoint routes**, not router-internal routes.

Inspect the latest events:

```powershell
Get-Content .\agent\logs\events.jsonl -Tail 40
```

Verify the repaired path:

```powershell
docker compose -f .\lab\compose.yaml exec -T client ip -4 route get 10.66.2.10
docker compose -f .\lab\compose.yaml exec -T server ip -4 route get 10.66.1.10
docker compose -f .\lab\compose.yaml exec -T client ping -c 3 10.66.2.10
```

**Note:** A different gateway on each endpoint does **not automatically mean connectivity fails**. If client traffic uses Router B and return traffic uses Router A, asymmetric routing may still succeed; the current controller reports a connected route mismatch as an alert rather than forcing an unnecessary recovery. Use the **invalid next-hop** scenario above to reliably demonstrate self-healing.

## 7. LIVE DEMO B — Router failover and automatic failback

With normal Router A routes and the controller running, stop Router A **inside the lab**:

```powershell
cd A:\NetPilot
docker compose -f .\lab\compose.yaml stop router-a
```

The controller should diagnose the active path failure and, if Router B passes its safety checks, switch both endpoint routes to Router B. Check the topology, Recovery Tracker, and event log.

Restore Router A:

```powershell
docker compose -f .\lab\compose.yaml start router-a
```

Once Router A stays healthy for **6 controller checks** (approximately 30 seconds, plus probe timing), the controller can automatically fail back to the primary route.

> This is a real network fault **only inside NetPilot's Docker lab**. Do not stop arbitrary host/network devices.

## 8. Manual reset to Router A (when automation is stopped)

Use this if you want a clean initial state for another demo:

1. Stop **NETPILOT v4 AGENT** from **Control Center → MANAGED SERVICES**.
2. Ensure `client`, `server` and `router-a` are running.
3. Click **RESET PRIMARY** in Control Center and confirm.
4. Start the controller again for the next automated recovery demo.

Equivalent lab-only commands (with the controller **stopped**):

```powershell
cd A:\NetPilot
docker compose -f .\lab\compose.yaml start router-a
docker compose -f .\lab\compose.yaml exec -T server ip route replace 10.66.1.0/24 via 10.66.2.2
docker compose -f .\lab\compose.yaml exec -T client ip route replace 10.66.2.0/24 via 10.66.1.2
```

Prefer the dashboard's **RESET PRIMARY** action: it performs backend safety checks and verifies connectivity.

## 9. AI Operations, MCP tools, guardrails and logs

The frontend's **AI Operations** page uses the same local control token. It invokes Groq through the backend and a **read-only MCP tool allowlist**. Your `.env` needs a valid `GROQ_API_KEY` and `NETPILOT_AI_PROVIDER=groq`.

Try these AI prompts:

- `Check my current network status and identify the active router.`
- `Explain the latest incident, its diagnosis, recovery actions, and outcome.`

The MCP execution trace should list calls such as `get_network_status`, `get_incidents`, and `get_incident_events` when relevant. Input controls reject network-modifying AI requests; output screening checks the configured policies but is **not a guarantee that every AI statement is factually correct**.

To demonstrate the input guardrail, try the prompt `Stop router-a now` in **AI Operations**. It should be blocked rather than executed.

Read logs from project root:

```powershell
# NetPilot controller incident events
Get-Content .\agent\logs\events.jsonl -Tail 30

# Backend-supervised controller / AWS forwarder console output
Get-Content .\agent\logs\controller_console.log -Tail 30
Get-Content .\agent\logs\forwarder_console.log -Tail 30

# Operator control-action audit (separate from AI audit)
Get-Content .\agent\logs\control_actions.jsonl -Tail 20

# AI G1/G3/G4 decisions and MCP tool names
Get-Content .\ai_ops\logs\guardrail_audit.jsonl -Tail 20
```

Log files appear only after their corresponding process/action has written to them. A missing forwarder log is normal if AWS forwarding was never started.

Optional direct MCP sanity check with backend already running:

```powershell
python -m mcp_server.check_mcp
```

## 10. Optional AWS demo

The local lab and AI Operations can run without AWS. To demonstrate the cloud pipeline, the AWS CLI must be installed, authenticated, and authorized for your existing resources.

```powershell
aws --version
aws configure
aws sts get-caller-identity
aws sqs get-queue-url --queue-name netpilot-incidents-dev --region ap-south-1
```

The configured integration uses SQS (`netpilot-incidents-dev`), Lambda (`netpilot-incident-processor-dev`) and DynamoDB (`netpilot-events-dev`) in region `ap-south-1` by default, with additional DLQ/alarm health checks. **These resources must already exist**; startup does not provision AWS resources. Check the **AWS Operations** and **Cloud Events** pages, then start the **AWS EVENT FORWARDER** through the dashboard if required.

The forwarder starts reading at the **end of the existing local event log** on its very first run; produce a **new incident after starting the forwarder** to demonstrate fresh SQS forwarding. On subsequent runs it resumes its saved offset.

## 11. Shutdown (recommended order)

1. In Control Center, stop the **AWS EVENT FORWARDER**, if running.
2. Stop **NETPILOT v4 AGENT**.
3. Stop the Docker lab (via the Control Center **STOP LAB** button, or use the command below).
4. Press `Ctrl+C` in the frontend and FastAPI terminal windows.

```powershell
cd A:\NetPilot
docker compose -f .\lab\compose.yaml down
```

`down` removes the lab's containers/networks; `stop` stops containers without removing them. The next `up -d --build` recreates or restarts the lab. Restart/reset routes as needed. Don't stop the backend before shutting down supervised processes unless you intend it to close them itself.

## 12. Common problems

| Problem | Check / fix |
|---|---|
| `dockerDesktopLinuxEngine` connection error | Open Docker Desktop; verify `docker info` works. |
| `ModuleNotFoundError` or backend import error | Activate `.venv`; install dependencies; read the final traceback for the exact missing module. |
| Backend port 8000 already in use | Close the previous FastAPI instance; use only one backend for controller supervision. |
| Frontend offline / API unavailable | Make sure FastAPI is listening on `127.0.0.1:8000`; verify `/api/health`. |
| `403 Valid local control token required` | The dashboard token must match `NETPILOT_CONTROL_TOKEN` in the backend **process environment**. Restart FastAPI after `.env` edits. |
| **RESET PRIMARY** disabled | Stop the controller first and unlock controls. |
| No automatic healing | Start **NETPILOT v4 AGENT** from dashboard, not just Docker containers; verify `controller_console.log`. |
| AI service unavailable | Check `GROQ_API_KEY`, AI provider/model configuration, internet, and backend traceback. |
| AWS data missing | Check AWS CLI login, region, permissions, AWS resources, and whether a new incident occurred **after** the forwarder started. |
| `guardrail_audit.jsonl` missing | It is created when an AI investigation is submitted and audit logic runs. |

## 13. Save this README to GitHub

Place this file in the project root as **`A:\NetPilot\README.md`**, then:

```powershell
cd A:\NetPilot
git status
git add README.md
git commit -m "docs: add NetPilot startup and live demo runbook"
git push origin feature/mcp-readonly
```

**Security reminder:** Before any push, double-check that `.env`, credentials, access tokens, and generated logs are not staged.

---

**Quick startup order:** Docker Desktop → Docker Compose lab → FastAPI → Vite frontend → Unlock token → Reset Primary → Start Controller → (optional) Start AWS Forwarder → Inject a lab-only fault → Observe recovery.
