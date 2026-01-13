# Project Conventions
This document outlines the coding and organizational conventions for the WFMS Gateway project. Adhering to these conventions ensures consistency, maintainability, and ease of collaboration among team members.                                      

---

## 1. Folder Purpose (Sacred)

**Never put files in the wrong folder. Ever.**

| Folder | Purpose | What Goes Here | What DOESN'T | Can Import Prod Code? |
|--------|---------|---|---|---|
| **`wfms/`** | ⭐ Production gateway | `service.py`, `proto.py`, `config.py` | Test scripts, demo tools | YES (import each other) |
| **`tools/`** | Dev utilities & scripts | Setup scripts, monitors, generators | Production logic | ❌ NO |
| **`tests/smoke/`** | Sanity/regression tests | `.ps1`, `.py` test scripts | Production code | ❌ NO (only imports wfms/) |
| **`archive/`** | Historical read-only | Old implementations | New code, active features | ❌ NO (never import this) |
| **`docs/`** | Documentation | Guides, conventions, architecture | Code that runs | ❌ NO |
| **`Coordinator_Node/`** | Zigbee firmware (C) | `.c`, `.h` firmware files | Python, scripts | N/A (separate project) |
| **root** | Project config/overview | `README.md`, `.env.example`, `mosquitto.conf` | Anything else | (read-only) |

**Golden Rule**: If you create a new file and don't know where it goes, **ask before committing**.

---

## 2. File Naming Convention

Consistent names = easy searching.

| Type | Format | Example | Why |
|------|--------|---------|-----|
| **Production module** | `snake_case.py` | `service.py`, `proto.py` | Python standard |
| **Test script** | `test_*.ps1` or `test_*.py` | `test_mqtt_connection.ps1` | Pytest compatible |
| **Utility script** | `action_noun.ps1` | `start_broker.ps1`, `configure_valve.py` | Clear intent |
| **Config file** | `.conf`, `config.py`, `.env` | `mosquitto.conf`, `gateway/config.py` | Standard names |
| **Documentation** | `TOPIC_DESCRIPTION.md` | `PROJECT_MAP.md`, `CONVENTIONS.md` | All caps = important |
| **Archive file** | (original name) | `Dashboard_Coordinator/`, `old_gateway.py` | Keep original for history |

---

## 3. Lifecycle: From Idea to Production

```
1. PROTOTYPE (tools/)
   ↓ Your new script/utility lives here first
   ├─ Test it locally
   ├─ Get feedback
   
2. STABILIZE (tests/smoke/)
   ↓ If it's a regression test, add it here
   ├─ Should pass 100% of the time
   
3. PROMOTE (wfms/)
   ↓ If it's production logic, move to wfms/
   ├─ Never move back to tools/
   
4. DEPRECATE (archive/)
   ↓ If replaced by newer code, move here
   ├─ Add date & reason in archive/README.md
   ├─ NEVER DELETE
   
5. FREEZE (archive/)
   ↓ Code in archive is read-only
   ├─ Can reference for bug-fixing
   ├─ Cannot import or execute from main codebase
```

**Rule**: Delete only cache (`.pyc`, `__pycache__`). Everything else → `archive/`.

---

## 4. Import Policy (Prevent Chaos)

**These imports are ALLOWED:**

```python
# ✅ OK - wfms modules import each other
wfms/gateway/service.py:
  from wfms.common.proto import make_cmd_line
  from wfms.gateway.config import Config

# ✅ OK - test imports from wfms
tests/smoke/test_mqtt.ps1:
  # Can call: python -m wfms.gateway.service

# ✅ OK - tools can import wfms for testing
tools/serial/configure_valve.py:
  from wfms.common.contract import TOPIC_CMD_VALVE
```

**These imports are FORBIDDEN:**

```python
# ❌ NO - wfms cannot import from tools
wfms/gateway/service.py:
  from tools.helpers import something  # BANNED

# ❌ NO - wfms cannot import from archive
wfms/gateway/service.py:
  from archive.old_gateway import OldService  # BANNED

# ❌ NO - tools scripts importing tools scripts (discouraged)
tools/mqtt/start_broker.ps1:
  source tools/serial/setup.ps1  # Avoid

# ❌ NO - archive cannot be executed
python archive/Dashboard_Coordinator/dashboard.py  # BANNED
```

**Why?** Circular dependencies, hard to untangle, breaks when refactoring.

---

## 5. Every File Needs a Header

No exceptions. Every script/module must have a header so future devs know what it does.

### Python Header Template

```python
"""
Module Name - One-line description

Purpose:
    What does this module do?
    Why does it exist?

Key Classes/Functions:
    - function_name(): What it does
    - ClassName: What it manages

Usage Examples:
    python -m wfms.gateway.service
    python -m wfms.gateway.service --fake-uart

Requirements:
    - Python 3.11+
    - paho-mqtt >= 2.0
    - pydantic >= 2.0

See Also:
    - ../common/proto.py - Protocol parsing
    - ../common/contract.py - MQTT topics
"""

import logging
logger = logging.getLogger(__name__)
```

### PowerShell Header Template

```powershell
# Script Name - One-line description
#
# Purpose:
#   What does this script do?
#   Why would someone run it?
#
# Usage:
#   .\script_name.ps1 [-param1 value] [-force]
#
# Parameters:
#   -param1     What it does
#   -force      Override confirmation
#
# Examples:
#   .\start_broker.ps1                # Start broker
#   .\start_broker.ps1 -port 1884    # Custom port
#
# Requirements:
#   - Windows 10+
#   - Admin privileges (if using -force)
#   - Mosquitto installed
#
# See Also:
#   .\restart_broker.ps1
#   tools/mqtt/README.md

param(
    [string]$Port = "1883",
    [switch]$Force
)
```

### Script Header Template

```bash
#!/bin/bash
# Script Name - One-line description
#
# Purpose:
#   What does this script do?
#
# Usage:
#   ./script.sh [options]
#
# Requirements:
#   - Bash 4.0+
#   - Command1, Command2
```

---

## 6. Git Commit Messages (Format & Discipline)

**Format**: `type(scope): description [details]`

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code restructuring (no behavior change)
- `docs`: Documentation update
- `test`: Add/update tests
- `chore`: Maintenance (deps, config)
- `ci`: CI/CD changes

**Scope** (optional but recommended):
- `gateway`: Changes to gateway service
- `protocol`: Changes to UART protocol
- `mqtt`: MQTT integration changes
- `tests`: Test files
- `docs`: Documentation

### Examples (Good)

```
feat(gateway): add extract_frames() for multi-frame UART parsing
- Handles @ACK/@INFO mid-line due to echo/buffer concatenation
- Fixes issue #42 (timeout on ACK)

fix(protocol): UART line ending CRLF + resync
- Changed TX from LF to CRLF to match CLI behavior
- Reduces dính rác (line concatenation) on coordinator

refactor(tests): reorganize test structure
- Move test_*.ps1 to tests/smoke/
- Add smoke test README

docs: Create PROJECT_MAP.md for quick reference
```

### Examples (Bad)

```
❌ update stuff
❌ fix bug
❌ changes
❌ asdf
❌ WIP
```

**Rule**: Commits are permanent history. Be descriptive for future debugging.

---

## 7. Code Review Checklist (Before Committing)

Use this checklist **every time** before `git commit`:

### Structure
- [ ] File in correct folder? (See Section 1)
- [ ] Follows naming convention? (See Section 2)
- [ ] Has header comment with purpose + usage + requirements?

### Code Quality
- [ ] No circular imports? (See Section 4)
- [ ] No hardcoded paths (use `.env` or config)?
- [ ] No credentials/passwords committed?
- [ ] No `.pyc`, `__pycache__`, `.env` in commit?

### Functionality
- [ ] Tested locally?
- [ ] Smoke tests pass? (`cd tests\smoke && .\test_mqtt_connection.ps1`)
- [ ] If protocol changed: Added regression test?
- [ ] If MQTT topics changed: Updated `contract.py` + `PROJECT_MAP.md`?

### Documentation
- [ ] If new feature: Updated `PROJECT_MAP.md`?
- [ ] If new port/service: Updated port table in `PROJECT_MAP.md`?
- [ ] If violates conventions: Updated `CONVENTIONS.md`?
- [ ] Commit message follows format? (`type(scope): description`)

### Final Sanity
- [ ] No `TODO`, `FIXME`, `HACK` left uncommented?
- [ ] No debug print statements left?
- [ ] No console.log / Write-Host spam?

---

## 8. When You Break the Rules (Exceptions)

**Approved exceptions:**

1. **Archive**: Old code in archive can violate rules (it's read-only).
2. **Firmware**: `Coordinator_Node/`, `Sensor_Node/`, `Vavle_Node/` are separate (C projects).
3. **Config**: `.env`, `mosquitto.conf` live at root (production requirements).
4. **One-off**: Temporary test file? Tag with `_tmp_` prefix, clean up after 1 day.

**NOT approved:**

- "I was in a hurry" → No. Always follow rules.
- "Just this once" → No. Rules exist for a reason.
- "It's small" → No. Rules apply to all files.

**If you must break rules**: File an issue, discuss with team, update this document.

---

## 9. Folder Structure Enforcement (Future-Proofing)

To prevent "file chaos", here's the rule: **Don't add files to root unless absolutely necessary.**

**Questions to ask before adding to root:**

1. Is this `.env`, `.conf`, `.md`, or `.gitignore`? → OK at root.
2. Is this Python code or a script that runs daily? → Move to `wfms/`, `tools/`, or `tests/`.
3. Is this temporary/experimental? → Put in `tools/` first.
4. Is this documentation? → Put in `docs/`.

**Current approved files at root:**
- `README.md` - Project overview
- `.env.example` - Config template
- `.gitignore` - Git ignore rules
- `mosquitto.conf` - MQTT config
- `mosquitto.conf.md` - Config docs
- `ORGANIZATION.md` - Structure overview
- `PROJECT_MAP.md` - Technical reference
- `INSTRUCTIONS.md` - Next steps
- `docs/` - Documentation folder

---

## 10. Quick Decision Tree

```
New file? Follow this:

Is it production code?
├─ YES → Goes to wfms/
│   ├─ Gateway logic → wfms/gateway/
│   ├─ Protocol logic → wfms/common/
│   └─ Dashboard logic → wfms/dashboards/
└─ NO → Goes to tools/ or tests/ or docs/

Is it a test?
├─ YES → Goes to tests/
│   ├─ Sanity test → tests/smoke/
│   ├─ Integration test → tests/integration/ (TBD)
│   └─ Performance test → tests/performance/ (TBD)
└─ NO → Check above

Is it a utility/tool?
├─ YES → Goes to tools/
│   ├─ Setup scripts → tools/setup/
│   ├─ MQTT tools → tools/mqtt/
│   ├─ Serial tools → tools/serial/
│   └─ Other tools → tools/
└─ NO → Check above

Is it documentation?
├─ YES → Goes to docs/
│   ├─ Guides → docs/guides/
│   ├─ Architecture → docs/architecture/
│   └─ Conventions → docs/CONVENTIONS.md
└─ NO → Check above

Is it config or reference?
├─ YES → Goes to root
│   ├─ MQTT config → mosquitto.conf
│   ├─ Gateway config → wfms/.env
│   └─ Project map → PROJECT_MAP.md
└─ NO → Ask!
```

---

## 📋 Summary

| Rule | Consequence of Ignoring |
|------|---|
| Put files in correct folder | Codebase becomes unsearchable chaos |
| Follow naming convention | Can't find anything, grep becomes useless |
| Add file headers | New devs waste hours figuring out what code does |
| Respect import rules | Circular dependencies break everything |
| Follow commit format | Git history becomes useless for debugging |
| Never delete, only archive | Lose history, can't reference old approaches |
| Update docs when changing code | Next dev (or future you) gets confused |

**Status**: 🟢 Conventions locked. New files must follow these rules.
