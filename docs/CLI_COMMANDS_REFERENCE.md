
# Zigbee CLI Reference

> Quick CLI reference for the **Zigbee Flow Monitoring System** projects.

**Applies to:** Z3Light, Z3Switch, Sensor Node, Actuator Node, Coordinator Node, Z3Gateway

---

## Table of Contents

- [Conventions](#conventions)
- [1. Basic Commands](#1-basic-commands)
- [2. Coordinator - Network Management](#2-coordinator---network-management)
- [3. End Device / Router - Join & Leave](#3-end-device--router---join--leave)
- [4. Binding](#4-binding)
- [5. ZCL Commands](#5-zcl-commands)
- [6. Debug & Diagnostics](#6-debug--diagnostics)
- [7. OTA Update](#7-ota-update)
- [8. Example Workflows](#8-example-workflows)
- [Z3Gateway (Linux/PC)](#z3gateway-linuxpc)
- [Important Notes](#important-notes)

---

## Conventions

### CLI Prompt

| Prompt | Role | Project |
|--------|------|---------|
| `Z3Light>` | Router / Light / Coordinator | Z3Light |
| `Z3Switch>` | Switch / Sensor / Actuator | Z3Switch |

### Network Roles (quick view)

- **Coordinator:** forms and manages the Zigbee network (Z3Light or Z3Gateway)
- **Router:** forwards messages and extends coverage
- **End Device:** endpoint device (Sensor Node, Actuator Node)

---

## 1. Basic Commands

### Show node/network info

```bash
info
````

**Fields you’ll typically see:**

| Field           | Meaning        | Typical values                                 |
| --------------- | -------------- | ---------------------------------------------- |
| `chan`          | Zigbee channel | 11–26                                          |
| `panID`         | Network PAN ID | 0x0000–0xFFFF                                  |
| `nodeType`      | Node type      | 0x00=Coordinator, 0x02=Router, 0x03=End Device |
| `network state` | Network state  | 0x00=No network, 0x02=Joined                   |

**Example output:**

```text
Z3Light>info
node [...] chan [15] pwr [3]
panID [0x5140] nodeID [0x0F72]
nodeType [0x02]
network state [02]
```

### List available commands / plugins

```bash
help                           # List all commands
plugin                         # List plugins
plugin <plugin-name>           # Show details for a plugin
```

Use this when you forget syntax or see: **"Incorrect number of arguments"**.

---

## 2. Coordinator - Network Management

### Form a network

**Option A: Default configuration (fast demo)**

```bash
plugin network-creator start 0
```

* Uses default channel mask and settings
* Best for quick testing

**Option B: Custom configuration**

```bash
plugin network-creator form 1 0xBEEF 20 11
```

| Param    | Meaning                            |
| -------- | ---------------------------------- |
| `1`      | Centralized network (Trust Center) |
| `0xBEEF` | PAN ID                             |
| `20`     | Zigbee channel                     |
| `11`     | TX power (dBm)                     |

**Verify:** run `info` and check `network state [02]`.

### Open/close the network for joining

```bash
# Open network (permit join ~180s)
plugin network-creator-security open-network

# Close network
plugin network-creator-security close-network
```

Typical usage:

* Testing: allow other nodes to join
* Security: close after devices joined

### Leave the network

```bash
network leave
```

Use when you want a clean reset, or to change PAN/channel.

---

## 3. End Device / Router - Join & Leave

### Join a network

```bash
plugin network-steering start 0
```

Requirements:

* Coordinator already formed the network
* Coordinator is currently **open-network**

**Verify:** `info` shows correct `chan`, `panID`, and `network state [02]`.

### Leave the network

```bash
network leave
```

---

## 4. Binding

### Print binding table

```bash
option binding-table print
```

### Manual binding

```bash
option binding-table set <index> <clusterId> <localEp> <remoteEp> {<remoteEUI64>}
```

**Example:** bind On/Off (0x0006) from Switch → Light

```bash
option binding-table set 0 0x0006 0x01 0x01 {EUI64_Light}
option binding-table print
```

### Find & Bind (automatic)

**On the Target (Light):**

```bash
plugin find-and-bind target 1
```

**On the Initiator (Switch):**

```bash
plugin find-and-bind initiator 1
```

**Verify:**

```bash
option binding-table print
```

---

## 5. ZCL Commands

### On/Off cluster commands

```bash
zcl on-off on
zcl on-off off
zcl on-off toggle
```

### Send ZCL command (addressing)

```bash
send 0xFFFF 1 1                # Broadcast
send <nodeId> 1 1              # Unicast
```

Use this to test clusters without relying on physical buttons.

---

## 6. Debug & Diagnostics

### Reduce RX log spam

```bash
option print-rx-msgs disable
```

### Inspect network topology

```bash
plugin stack-diagnostics neighbor-table     # Neighbors (routing view)
plugin stack-diagnostics child-table        # Child end devices
plugin stack-diagnostics route-table        # Routing table
```

Use these when debugging join/routing/connectivity issues.

### Read an attribute (ZCL global command)

```bash
zcl global read <clusterId> <attributeId>
send <nodeId> <srcEp> <dstEp>
```

**Example:** read On/Off attribute (cluster 0x0006, attr 0x0000)

```bash
zcl global read 0x0006 0x0000
send 0x1234 1 1
```

---

## 7. OTA Update

### Build OTA files

**Step 1: Create `.gbl` from `.s37`**

```bash
commander gbl create output.gbl --app input.s37
```

**Step 2: Create `.ota` from `.gbl`**

```bash
image-builder --create output.ota \
  --version 22 \
  --manuf-id 0x1002 \
  --image-type 0 \
  --tag-id 0x0000 \
  --tag-file output.gbl \
  --string "Firmware v22"
```

### OTA client (device side)

```bash
plugin ota-client start
```

Requirement: an OTA Server is configured and reachable in the network.

---

## 8. Example Workflows

### Demo: Light & Switch

**1) Coordinator/Light**

```bash
plugin network-creator start 0
info
```

**2) Switch joins**

```bash
plugin network-steering start 0
info
```

**3) Find & Bind**

```bash
# On Light
plugin find-and-bind target 1

# On Switch
plugin find-and-bind initiator 1
```

**4) Verify binding**

```bash
option binding-table print
```

**5) Test**

* Press the Switch button → Light LED toggles

---

### Flow Monitoring System

**1) Coordinator forms + opens network**

```bash
plugin network-creator start 0
plugin network-creator-security open-network
```

**2) Sensor Node joins**

```bash
plugin network-steering start 0
info
```

**3) Actuator Node joins**

```bash
plugin network-steering start 0
info
```

**4) Check topology**

```bash
plugin stack-diagnostics neighbor-table
plugin stack-diagnostics child-table
```

**5) Debug data flow (read + control)**

```bash
# Read flow value from Sensor (example cluster/attr)
zcl global read 0x000C 0x0055
send <sensorNodeId> 1 1

# Control valve via On/Off
zcl on-off on
send <actuatorNodeId> 1 1
```

---

## Z3Gateway (Linux/PC)

### Start the gateway

```bash
sudo ./build/debug/Z3Gateway -p /dev/ttyACM0
```

Requirements:

* Zigbee kit runs NCP firmware
* Connected via USB to the PC

What it does:

* Acts as Zigbee Coordinator
* Bridges data to PC/Cloud (depending on your implementation)

---

## Important Notes

⚠️ **Common issues**

| Issue                           | Likely cause                     | Fix                                            |
| ------------------------------- | -------------------------------- | ---------------------------------------------- |
| "Incorrect number of arguments" | Missing parameters               | Use `plugin <name>` to see correct syntax      |
| Node cannot join                | Coordinator not open for joining | `plugin network-creator-security open-network` |
| No binding found                | Find & Bind not executed         | Re-run binding workflow                        |
| No data transfer                | Routing issue                    | Check `neighbor-table` and `route-table`       |

💡 **Practical tips**

* Always run `info` first before deeper debugging
* Disable `print-rx-msgs` to make logs readable
* Keep a note of each node’s `EUI64` and `nodeId`
* Use `option binding-table print` to confirm bindings

---

**Last updated:** aligned with **Gecko SDK 4.x** and **Simplicity Studio 5**

```
```
