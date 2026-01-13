## Importing .sls Projects into Simplicity Studio 5

This folder contains Simplicity Studio project archives for the Zigbee Flow Monitoring System:

- `Coordinator_Node.sls` – Coordinator firmware project
- `Sensor node.sls` – Sensor node firmware project
- `Valve_node.sls` – Valve/actuator node firmware project

Follow the steps below to import and build these projects in Simplicity Studio 5.

### Prerequisites

- Simplicity Studio 5 installed (latest version recommended)
- Gecko SDK and Zigbee stacks installed in Simplicity Studio
- A supported Silicon Labs EFR32 development kit connected via USB

### Step 1 – Start Simplicity Studio

1. Launch **Simplicity Studio 5**.
2. Make sure your EFR32 board is detected in the **Debug Adapters** view.

### Step 2 – Open the Import Wizard

1. From the top menu, select:
	- **File → Import...**
2. In the import dialog, choose:
	- **Existing Projects into Workspace** (or **Simplicity Studio → Project** if available), then click **Next**.

### Step 3 – Select the .sls Archive

1. In the **Select archive file** option, click **Browse**.
2. Navigate to the repository folder:
	- `D:\CODE\Zigbee-Flow-Monitoring-System\file_project\`
3. Choose one of the `.sls` files, for example:
	- `Coordinator_Node.sls`
4. Simplicity Studio will list the project(s) found in the archive.

### Step 4 – Configure Import Options

1. Make sure **Copy projects into workspace** is **checked** (recommended).
2. Verify that the project you want to import is selected.
3. Click **Finish** to import the project.

Repeat **Step 3–4** for:

- `Sensor node.sls`
- `Valve_node.sls`

### Step 5 – Build the Project

1. In the **Project Explorer**, right-click the imported project (e.g. `Coordinator_Node`).
2. Select **Build Project** (or **Clean Project** then **Build Project** if needed).
3. Wait for the build to complete without errors.

### Step 6 – Flash the Firmware to the Board

1. Ensure the correct board is selected in the **Debug Adapters** view.
2. Right-click the project (e.g. `Coordinator_Node`) and choose **Debug As → Silicon Labs ARM Program** or **Flash to Device** (depending on your Simplicity Studio version).
3. Confirm the target device and flash settings, then start the programming process.

Repeat flashing for the **Sensor** and **Valve** node projects on their corresponding boards.

### Notes

- If Simplicity Studio cannot find the correct SDK, open **Project → Properties → C/C++ Build → Settings** and adjust the SDK path or toolchain as needed.
- If you move this repository, you may need to re-import the projects or update any absolute paths inside the project properties.

