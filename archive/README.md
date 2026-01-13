# Archive Folder

This folder contains deprecated/legacy code that is no longer actively used but kept for reference.

## Archived Date: 2026-01-11

## Contents

### `Dashboard_Coordinator/`
- **Status**: Replaced by `wfms/gateway/service.py`
- **Reason**: Old dashboard implementation, superseded by new WFMS gateway system
- **Keep for**: Historical reference, debugging protocol issues, comparing old vs new implementations

### `Gate_Way_Z3/`
- **Status**: Replaced by `wfms/gateway/`
- **Reason**: Old gateway implementation (gateway_mqtt.py)
- **Keep for**: Reference for MQTT protocol, comparing implementations

### `mock_gateway.deprecated.py`
- **Status**: Replaced by `gateway.service.py --fake-uart`
- **Reason**: Old mock/fake UART implementation
- **Keep for**: Reference if new fake UART has issues

### `telemetry.db`
- **Status**: Test data from development
- **Reason**: Not needed for production, but kept for reference
- **Can delete after**: 2 weeks if no issues

### `TEST_3_TERMINAL.md`
- **Status**: Development notes
- **Reason**: Debugging notes during development
- **Keep for**: Historical context

## When to Delete

These files can be safely deleted after:
- New system runs stable for 2-4 weeks
- No regression bugs that require referencing old code
- Team confirms they don't need old implementations

## Restore Instructions

If you need to restore any file:
```powershell
# From archive back to original location
Move-Item "archive\<filename>" "."
```
