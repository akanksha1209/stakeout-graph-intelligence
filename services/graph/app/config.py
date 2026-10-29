"""
Configuration module for Stakeout Graph Intelligence Service.
Compliant with AGENTS.md strict rules:
- No hardcoded secrets, addresses, or endpoints.
- Fails loudly with SystemExit on missing required configuration.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Resolve paths
SERVICE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = SERVICE_DIR.parent.parent

# Attempt loading .env from service directory, then root workspace
load_dotenv(dotenv_path=SERVICE_DIR / ".env")
load_dotenv(dotenv_path=WORKSPACE_DIR / ".env")
load_dotenv()


def required(name: str) -> str:
    """
    Retrieve a required environment variable or terminate immediately with a clear error.
    
    Args:
        name: Name of the environment variable.
        
    Returns:
        The stripped string value of the environment variable.
        
    Raises:
        SystemExit: If the variable is absent or empty.
    """
    value = os.getenv(name)
    if value is None or value.strip() == "":
        sys.stderr.write(
            f"\n[CRITICAL CONFIGURATION ERROR] Missing required environment variable: '{name}'.\n"
            f"Stakeout Graph Service requires this setting to run.\n"
            f"Please verify your .env file or environment definitions.\n\n"
        )
        raise SystemExit(1)
    return value.strip()


# TigerGraph Credentials & Connection Settings
TG_HOST: str = required("TG_HOST")
TG_USERNAME: str = required("TG_USERNAME")
TG_PASSWORD: str = required("TG_PASSWORD")
TG_GRAPH_NAME: str = required("TG_GRAPH_NAME")

# Scenario Generator Seed
try:
    SCENARIO_SEED: int = int(required("SCENARIO_SEED"))
except ValueError:
    sys.stderr.write(
        f"\n[CRITICAL CONFIGURATION ERROR] SCENARIO_SEED must be a valid integer, "
        f"got '{os.getenv('SCENARIO_SEED')}'.\n\n"
    )
    raise SystemExit(1)

# Service Network Port
raw_port = os.getenv("GRAPH_SERVICE_PORT", "8001").strip()
try:
    GRAPH_SERVICE_PORT: int = int(raw_port)
except ValueError:
    sys.stderr.write(
        f"\n[CRITICAL CONFIGURATION ERROR] GRAPH_SERVICE_PORT must be an integer, got '{raw_port}'.\n\n"
    )
    raise SystemExit(1)

# Common directory paths
DATA_DIR = SERVICE_DIR / "data"
DRAFTS_DIR = SERVICE_DIR / "drafts"

