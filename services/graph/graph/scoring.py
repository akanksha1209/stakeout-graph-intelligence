import json, os, sys
from pathlib import Path

def calculate_score(wallet_data: dict) -> dict:
    config_path = Path(__file__).resolve().parent.parent / "config" / "scoring.json"
    if not config_path.exists():
        sys.exit(f"FATAL: Missing config at {config_path}")
        
    with open(config_path, "r") as f:
        config = json.load(f)
        
    weights = config.get("weights", {})
    thresholds = config.get("thresholds", {})
    
    fan_in = wallet_data.get("fanIn", 0)
    fan_out = wallet_data.get("fanOut", 0)
    total_in = wallet_data.get("totalIn", 0.0)
    total_out = wallet_data.get("totalOut", 0.0)
    
    pass_through = (total_out / total_in) if total_in > 0 else 0.0
    score = 0.0
    signals = []
    
    if pass_through >= thresholds.get("passThroughRatioMin", 0.4):
        score += weights.get("passThroughRatio", 0.25)
        signals.append("passThroughRatio")
    if fan_in >= thresholds.get("fanInMin", 3):
        score += weights.get("fanIn", 0.10)
        signals.append("fanIn")
    if fan_out >= thresholds.get("fanOutMin", 3):
        score += weights.get("fanOut", 0.10)
        signals.append("fanOut")
        
    return {
        "behaviorScore": round(min(score, 1.0), 4),
        "passThroughRatio": round(pass_through, 4),
        "signals": signals,
        "signalDetails": [
            {"name": "fanIn", "value": fan_in},
            {"name": "fanOut", "value": fan_out},
            {"name": "passThroughRatio", "value": round(pass_through, 4)},
            {"name": "totalIn", "value": total_in},
            {"name": "totalOut", "value": total_out}
        ]
    }
