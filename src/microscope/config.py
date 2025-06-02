from pathlib import Path

# Micro-Manager config
MM_CONFIG_PATH = Path(
    r"C:\\Program Files\\Micro-Manager_2.0.3_20241209\\20250523-OPM.cfg"
)

# Ensure the file exists
if not MM_CONFIG_PATH.exists():
    raise FileNotFoundError(f"Micro-Manager config not found at {MM_CONFIG_PATH}")
