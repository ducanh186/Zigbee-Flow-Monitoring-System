
# Copilot / GitHub Agent Instructions

Purpose: provide concise, actionable guidance to AI coding agents working on
the PC-side of the Zigbee Flow Monitoring System. Focus on Python, tests,
tools and integration; do NOT modify firmware C code (see Ownership section).

0) Project goal (high-level)
- Build a Zigbee-based water flow monitoring + valve control system. Relevant
  components for this repo: `pc_gateway.py` (UART gateway), `dashboard.py`
  (Streamlit UI), and `fake_device.py` (simulator / sample data generator).

1) Ownership & scope boundary (VERY IMPORTANT)
- You MUST handle: Python dashboard/app, utility scripts, and PC-side tooling.
- You MUST NOT edit or create `.c` / `.h` firmware files. If firmware changes
  are required, produce a short "Change Request" (file names, function-level
  changes, rationale, expected UART output) and stop.

2) Expected UART protocol (PC dashboard contract)
- Coordinator -> PC: `@DATA`, `@INFO`, `@LOG` lines with JSON payloads.
  Example: `@DATA {"flow":55,"valve":"closed","battery":83}`
- PC -> Coordinator: send `@CMD {"id":1,"op":"valve_set","value":"open"}`
- Coordinator -> PC: ACKs as `@ACK {"id":1,"ok":true,...}`

Rules:
- Treat each UART line as an independent message; ignore malformed JSON
  (log and continue). Never crash the UI on bad input.
- Always support selecting COM port + baudrate from UI/CLI.

3) Python dashboard requirements (minimum / Week-2 target)
- Show current `flow`, `valve` state, and `battery` percent.
- Simple visualization of last-N flow samples (text or small plot).
- Manual controls: send `open` / `closed` via `@CMD` with incrementing `id`.
- Connection handling: auto-reconnect or clear error message; allow port
  changes without restarting when possible.

Nice-to-have:
- CSV logging, Auto/Manual indicator, basic alerts (flow > threshold).

4) Output format for responses / PRs
When implementing changes provide:
1) Short plan (3–6 bullets)
2) Code changes (full file contents for new/changed Python files)
3) One-line run command
4) Test steps: real COM port and mocked serial verification

5) Coding standards (Python)
- Use `pyserial` for UART; prefer a `SerialReader` background thread with a
  message queue to the UI.
- Keep dependencies minimal; add timeouts and safe shutdown.
- If using Streamlit: do not block main thread; use `session_state` + background
  thread + periodic refresh (see `dashboard.py`).

6) Testing checklist (include in PR description)
- [ ] Open COM port and read streaming lines
- [ ] Parses `@DATA` and updates UI
- [ ] Sending `@CMD` yields visible `@ACK`
- [ ] Handles malformed lines without crashing
- [ ] Clean exit (port closed, thread stopped)

7) When firmware changes are needed
- Do NOT edit firmware here. Instead write a Change Request with:
  - target file(s), functions to change
  - exact UART format changes expected
  - test steps to verify (examples using `fake_device.py`)

Quick pointers (useful file locations):
- `pc_gateway.py`: `ZigbeeGateway`, `_normalize_json()`, `send_command()`, db schema
- `dashboard.py`: `reader_thread_fn`, parsing helpers `parse_data_line()`,
  `make_cmd()` and Streamlit UI layout
- `fake_device.py`: how to simulate `@DATA` and `@ACK` for integration tests

If you want, I can also (pick one): expand test examples, add a small
`tests/` harness that feeds sample lines into a `SerialReader`, or prepare a
Change Request template for firmware edits. Which would you prefer?
