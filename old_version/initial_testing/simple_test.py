from pymmcore_plus import CMMCorePlus

mmc = CMMCorePlus()

# Try loading custom config
mmc.loadSystemConfiguration("hardware_profiles/demo.cfg")

# --- Print Device Roles ---
print("=== Device Roles ===")
print("Camera:", mmc.getCameraDevice())
print("XYStage:", mmc.getXYStageDevice())
print("FocusStage:", mmc.getFocusDevice())
print("Shutter:", mmc.getShutterDevice())
print()

# --- List All Devices ---
print("=== All Loaded Devices ===")
devices = mmc.getLoadedDevices()
for device in devices:
    print(f"- {device}")
print()

# --- Optional: Print Properties for Each Device ---
print("=== Device Properties ===")
for device in devices:
    print(f"[{device}]")
    props = mmc.getDevicePropertyNames(device)
    for prop in props:
        value = mmc.getProperty(device, prop)
        print(f"  {prop} = {value}")
    print()
