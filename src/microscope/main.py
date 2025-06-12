# main.py
import tkinter as tk
import traceback

from .config import HW
from .gui import AcquisitionGUI
from .hardware_control import HardwareInterface, mmc


def main():
    try:
        hw_main_interface = HardwareInterface(config_file_path=HW.cfg_path)
        root = tk.Tk()
        root.minsize(600, 700)
        app = AcquisitionGUI(root, hw_main_interface)
        root.mainloop()
    except Exception as e_main:
        print(f"An unexpected error occurred in __main__: {e_main}")
        traceback.print_exc()
    finally:
        if "mmc" in locals() and mmc.getLoadedDevices():
            mmc.reset()
        print("Script execution finished.")


if __name__ == "__main__":
    main()
