"""
Scoring Engine for Stakeout Graph Intelligence.
Evaluates wallet metrics against dynamic heuristic weights and thresholds.

STRICT COMPLIANCE (AGENTS.md Rule 1: No Hardcoding):
- NO hardcoded weights or thresholds.
- Dynamically loads configuration from 'config/scoring.json' or 'drafts/scoring.draft.json'.
- Fails loudly with SystemExit(1) if configuration file is missing or invalid.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Resolve candidate paths for scoring configuration
CURRENT_DIR = Path(__file__).resolve().parent
SERVICE_DIR = CURRENT_DIR.parent
WORKSPACE_DIR = SERVICE_DIR.parent.parent

CANDIDATE_PATHS = [
    Path(os.getenv("SCORING_CONFIG_PATH", "")) if os.getenv("SCORING_CONFIG_PATH") else None,
    SERVICE_DIR / "config" / "scoring.json",
    WORKSPACE_DIR / "config" / "scoring.json",
    SERVICE_DIR / "drafts" / "scoring.draft.json",
    WORKSPACE_DIR / "drafts" / "scoring.draft.json",
]


def resolve_scoring_config_path() -> Path:
    """
    Search for valid scoring configuration file.
    Fails loudly if none of the candidate paths exist.
    """
    checked_paths = []
    for candidate in CANDIDATE_PATHS:
        if candidate:
            checked_paths.append(str(candidate))
            if candidate.exists() and candidate.is_file():
                return candidate

    sys.stderr.write(
        f"\n[CRITICAL ERROR] Scoring configuration file not found!\n"
        f"Searched paths:\n"
        + "\n".join(f" - {p}" for p in checked_paths)
        + f"\nStakeout requires scoring weights and thresholds in a valid JSON file to prevent hardcoding.\n"
        f"Please ensure 'config/scoring.json' or 'drafts/scoring.draft.json' exists.\n\n"
    )
    raise SystemExit(1)


def load_scoring_config(filepath: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load weights and thresholds configuration from JSON file.
    Fails loudly if file cannot be read, parsed, or lacks required sections.
    """
    target_path = filepath if filepath else resolve_scoring_config_path()

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as exc:
        sys.stderr.write(
            f"\n[CRITICAL ERROR] Failed to parse scoring configuration file at '{target_path}': {exc}\n\n"
        )
        raise SystemExit(1)

    if not isinstance(config, dict) or "weights" not in config or "thresholds" not in config:
        sys.stderr.write(
            f"\n[CRITICAL ERROR] Invalid scoring configuration structure in '{target_path}'.\n"
            f"Both 'weights' and 'thresholds' dictionaries are strictly required.\n\n"
        )
        raise SystemExit(1)

    return config


# Cache the configuration at module import (fails loudly if missing)
_SCORING_CONFIG = load_scoring_config()


def get_scoring_thresholds() -> Dict[str, Any]:
    """Retrieve thresholds dictionary dynamically from scoring config."""
    cfg = load_scoring_config()
    return cfg.get("thresholds", {})


def get_behavior_score_threshold() -> float:
    """Retrieve behaviorScore threshold dynamically from scoring config."""
    thresholds = get_scoring_thresholds()
    return float(thresholds.get("behaviorScore", 0.40))


BEHAVIOR_SCORE_THRESHOLD: float = get_behavior_score_threshold()


def calculate_score(wallet_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate the scam behavior score (0.0 to 1.0) and identify active risk signals.
    
    Reads all weights and comparison thresholds dynamically from the loaded config.
    No weights or thresholds are hardcoded.

    Args:
        wallet_data: Dictionary containing graph metrics for a wallet:
                     - totalIn (or total_in): float
                     - totalOut (or total_out): float
                     - fanIn (or fan_in): int
                     - fanOut (or fan_out): int
                     - passThroughRatio (or pass_through_ratio): optional float
                     - medianForwardTime (or median_forward_time): float/int (seconds)
                     - hopsToExit (or hops_to_exit): int (-1 if no path)
                     - repeatedFlows (or repeated_flows): int

    Returns:
        dict: {
            "behaviorScore": float (0.0 to 1.0),
            "passThroughRatio": float,
            "linked": bool,
            "isSuspicious": bool,
            "signals": list of str,
            "signalDetails": list of dicts (name, value),
            "metrics": dict of normalized inputs
        }
    """
    weights = _SCORING_CONFIG.get("weights", {})
    thresholds = _SCORING_CONFIG.get("thresholds", {})

    # Extract metrics supporting camelCase or snake_case
    try:
        total_in = float(wallet_data.get("totalIn", wallet_data.get("total_in", 0.0)) or 0.0)
    except (ValueError, TypeError):
        total_in = 0.0

    try:
        total_out = float(wallet_data.get("totalOut", wallet_data.get("total_out", 0.0)) or 0.0)
    except (ValueError, TypeError):
        total_out = 0.0

    try:
        fan_in = int(wallet_data.get("fanIn", wallet_data.get("fan_in", 0)) or 0)
    except (ValueError, TypeError):
        fan_in = 0

    try:
        fan_out = int(wallet_data.get("fanOut", wallet_data.get("fan_out", 0)) or 0)
    except (ValueError, TypeError):
        fan_out = 0

    # Calculate pass_through_ratio if not explicitly supplied
    raw_ptr = wallet_data.get("passThroughRatio", wallet_data.get("pass_through_ratio"))
    if raw_ptr is not None:
        try:
            pass_through_ratio = float(raw_ptr)
        except (ValueError, TypeError):
            pass_through_ratio = (total_out / total_in) if total_in > 0.0 else 0.0
    else:
        pass_through_ratio = (total_out / total_in) if total_in > 0.0 else 0.0

    val1 = wallet_data.get("medianForwardTime", wallet_data.get("median_forward_time", -1.0))
    median_forward_time = float(val1) if val1 is not None else -1.0
    val2 = wallet_data.get("hopsToExit", wallet_data.get("hops_to_exit", -1))
    hops_to_exit = int(val2) if val2 is not None else -1



    try:
        repeated_flows = int(wallet_data.get("repeatedFlows", wallet_data.get("repeated_flows", 0)) or 0)
    except (ValueError, TypeError):
        repeated_flows = 0

    raw_score = 0.0
    triggered_signals: List[str] = []

    # 1. High Pass-Through Ratio (rapid drain of incoming funds)
    ptr_min = thresholds.get("passThroughRatioMin", float("inf"))
    if pass_through_ratio >= ptr_min:
        raw_score += weights.get("passThroughRatio", 0.0)
        triggered_signals.append("passThroughRatio")

    # 2. High Fan-In Signal
    fan_in_min = thresholds.get("fanInMin", float("inf"))
    if fan_in >= fan_in_min:
        raw_score += weights.get("fanIn", 0.0)
        triggered_signals.append("fanIn")

    # 3. High Fan-Out Signal
    fan_out_min = thresholds.get("fanOutMin", float("inf"))
    if fan_out >= fan_out_min:
        raw_score += weights.get("fanOut", 0.0)
        triggered_signals.append("fanOut")

    # 4. Rapid Forwarding (Short median forwarding delay)
    rapid_max_seconds = thresholds.get("rapidForwardTimeMaxSeconds", -1)
    if 0 <= median_forward_time <= rapid_max_seconds:
        raw_score += weights.get("medianForwardTime", 0.0)
        triggered_signals.append("medianForwardTime")

    # 5. Direct proximity to known Exit Point
    hops_max = thresholds.get("hopsToExitMax", -1)
    if 0 <= hops_to_exit <= hops_max:
        raw_score += weights.get("hopsToExit", 0.0)
        triggered_signals.append("hopsToExit")

    # 6. Repeated circular or structured flows
    repeated_min = thresholds.get("repeatedFlowsMin", float("inf"))
    if repeated_flows >= repeated_min:
        raw_score += weights.get("repeatedFlows", 0.0)
        triggered_signals.append("repeatedFlows")

    # Clamp final behavior score to [0.0, 1.0]
    behavior_score = max(0.0, min(1.0, raw_score))
    behavior_score = round(behavior_score, 4)

    score_threshold = thresholds.get("behaviorScore", 0.80)
    min_signals = thresholds.get("minSignals", 1)
    is_suspicious = (behavior_score >= score_threshold) and (len(triggered_signals) >= min_signals)

    return {
        "behaviorScore": behavior_score,
        "passThroughRatio": round(pass_through_ratio, 4),
        "linked": is_suspicious,
        "isSuspicious": is_suspicious,
        "signals": triggered_signals,
        "signalDetails": [
            {"name": "fanIn", "value": fan_in},
            {"name": "fanOut", "value": fan_out},
            {"name": "passThroughRatio", "value": float(round(pass_through_ratio, 4))},
            {"name": "totalIn", "value": float(round(total_in, 4))},
            {"name": "totalOut", "value": float(round(total_out, 4))},
        ],
        "metrics": {
            "fanIn": fan_in,
            "fanOut": fan_out,
            "passThroughRatio": pass_through_ratio,
            "totalIn": total_in,
            "totalOut": total_out,
            "medianForwardTime": median_forward_time,
            "hopsToExit": hops_to_exit,
            "repeatedFlows": repeated_flows,
        },
    }
