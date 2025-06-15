from pymmcore_plus import CMMCorePlus, DeviceType


class CameraHardwareController:
    """
    Hardware controller for camera-specific configuration.
    It handles setup for one or more physical cameras.
    """

    def set_trigger_mode(self, mmc: CMMCorePlus, mode: str):
        """
        Sets the trigger mode for all physical cameras IF they support it.
        """
        print("Configuring cameras for hardware acquisition...")

        physical_cameras = [cam for cam in mmc.getLoadedDevicesOfType(DeviceType.Camera) if "Multi" not in cam]

        if not physical_cameras:
            raise RuntimeError("No physical cameras found in the configuration.")

        print(f"Found physical cameras: {physical_cameras}")

        # For each camera, check for the "TriggerMode" property before setting it.
        for cam_label in physical_cameras:
            if mmc.hasProperty(cam_label, "TriggerMode"):
                print(f"'{cam_label}' has 'TriggerMode'. Setting to '{mode}'.")
                mmc.setProperty(cam_label, "TriggerMode", mode)
            else:
                # This will happen in demo mode, which is perfectly fine.
                print(f"'{cam_label}' does not have 'TriggerMode' property. Skipping.")

        # Set the core device to handle single or multiple cameras
        if len(physical_cameras) > 1 and "Multi Camera" in mmc.getLoadedDevices():
            print("Setting Core camera to 'Multi Camera' for simultaneous acquisition.")
            mmc.setCameraDevice("Multi Camera")
        else:
            mmc.setCameraDevice(physical_cameras[0])

        print("Camera configuration complete.")

    def set_exposure(self, mmc: CMMCorePlus, exposure_ms: float):
        """Sets the exposure time for the active camera(s)."""
        mmc.setExposure(exposure_ms)

    def get_exposure(self, mmc: CMMCorePlus) -> float:
        """Gets the current exposure time from the core."""
        return mmc.getExposure()
