"""
Evaluation Script for Stakeout Graph Intelligence Service.
Benchmarking oracle prediction accuracy against ground truth scenarios.

STRICT COMPLIANCE:
- NO hardcoded wallet addresses or cluster IDs.
- Reads ground truth dynamically from data/scenarios.json.
- Gracefully handles network errors when the FastAPI service is unreachable.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure services/graph directory is on sys.path
CURRENT_DIR = Path(__file__).resolve().parent
SERVICE_DIR = CURRENT_DIR.parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import httpx

try:
    from app.config import GRAPH_SERVICE_PORT
except Exception:
    GRAPH_SERVICE_PORT = int(os.getenv("GRAPH_SERVICE_PORT", "8001"))

DEFAULT_SCENARIOS_FILE = SERVICE_DIR / "data" / "scenarios.json"


def load_scenarios_data(filepath: Path) -> Any:
    """
    Safely load scenarios dataset from JSON.
    Fails loudly if file does not exist or cannot be parsed.
    """
    if not filepath.exists():
        sys.stderr.write(
            f"\n[CRITICAL ERROR] Scenarios dataset not found at: '{filepath}'.\n"
            f"Please run 'python graph/generate.py' first to produce ground-truth data.\n\n"
        )
        raise SystemExit(1)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        sys.stderr.write(
            f"\n[CRITICAL ERROR] Failed to parse JSON in '{filepath}': {exc}\n\n"
        )
        raise SystemExit(1)


def extract_wallets_from_data(data: Any) -> List[Dict[str, Any]]:
    """
    Safely extract wallet records whether scenarios.json is formatted
    as a list, a dictionary with a 'wallets' key, or an address map.
    """
    wallets: List[Dict[str, Any]] = []

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                wallets.append(item)
            elif isinstance(item, str):
                wallets.append({"address": item})
    elif isinstance(data, dict):
        if "wallets" in data:
            wallets_val = data["wallets"]
            if isinstance(wallets_val, dict):
                for addr, info in wallets_val.items():
                    if isinstance(info, dict):
                        w = dict(info)
                        if "address" not in w:
                            w["address"] = addr
                        wallets.append(w)
                    else:
                        wallets.append({"address": addr, "role": str(info)})
            elif isinstance(wallets_val, list):
                for item in wallets_val:
                    if isinstance(item, dict):
                        wallets.append(item)
                    elif isinstance(item, str):
                        wallets.append({"address": item})
        else:
            # Check if root dict is an address map { "0x...": { ... } }
            for k, v in data.items():
                if isinstance(k, str) and k.startswith("0x"):
                    if isinstance(v, dict):
                        w = dict(v)
                        if "address" not in w:
                            w["address"] = k
                        wallets.append(w)
                    else:
                        wallets.append({"address": k, "role": str(v)})

    return wallets


def determine_ground_truth(wallet_item: Dict[str, Any]) -> Optional[bool]:
    """
    Determine binary ground truth label for a wallet:
    - Scam (True): role/type in ["scam_master", "layering_intermediate", "exit_point"]
    - Innocent (False): role/type in ["merchant", "framed", "critic", "victim"]
    """
    raw_role = str(wallet_item.get("role") or wallet_item.get("type") or "").lower().strip()

    # Rule 1: Explicit scam roles -> True
    scam_roles = {"scam_master", "layering_intermediate", "exit_point"}
    if raw_role in scam_roles:
        return True

    # Rule 2: Explicit innocent roles / keywords -> False
    innocent_keywords = ["merchant", "framed", "framing", "critic", "victim", "regular", "user", "noise"]
    if any(keyword in raw_role for keyword in innocent_keywords):
        return False

    # Check fallback boolean flag if present
    if "is_scam" in wallet_item:
        return bool(wallet_item["is_scam"])

    return None


def run_evaluation(
    api_base_url: str,
    scenarios_path: Path = DEFAULT_SCENARIOS_FILE,
) -> None:
    """
    Execute benchmark against FastAPI /analyze endpoint.
    Computes confusion matrix, precision, recall, and lists discrepancies.
    """
    print(f"\n[Stakeout Evaluator] Loading ground-truth from: {scenarios_path}")
    raw_data = load_scenarios_data(scenarios_path)
    wallets = extract_wallets_from_data(raw_data)

    if not wallets:
        sys.stderr.write(
            f"\n[ERROR] No wallet records found in '{scenarios_path}'.\n\n"
        )
        raise SystemExit(1)

    print(f"[Stakeout Evaluator] Parsed {len(wallets)} wallet entries from scenarios.")
    print(f"[Stakeout Evaluator] Testing API connection at: {api_base_url}/health")

    client = httpx.Client(timeout=10.0)

    # Preflight check to verify if the API is running
    try:
        health_resp = client.get(f"{api_base_url}/health")
        if health_resp.status_code != 200:
            sys.stderr.write(
                f"\n[WARNING] Health check endpoint returned status: {health_resp.status_code}\n"
            )
        else:
            print("[Stakeout Evaluator] API connection confirmed (status: ok).\n")
    except httpx.RequestError as exc:
        sys.stderr.write(
            f"\n[NETWORK ERROR] Could not reach Stakeout Graph API at '{api_base_url}'.\n"
            f"Details: {exc}\n"
            f"Please verify that your FastAPI service is running:\n"
            f"  python services/graph/app/main.py\n"
            f"  or uvicorn app.main:app --port {GRAPH_SERVICE_PORT}\n\n"
        )
        raise SystemExit(1)

    tp = 0
    fp = 0
    tn = 0
    fn = 0
    evaluated_count = 0

    false_positives: List[Dict[str, Any]] = []
    false_negatives: List[Dict[str, Any]] = []

    for idx, w in enumerate(wallets, start=1):
        address = w.get("address")
        if not address:
            continue

        ground_truth = determine_ground_truth(w)
        if ground_truth is None:
            continue  # Skip unclassified entries

        role = w.get("role") or w.get("type") or "unknown"
        analyze_url = f"{api_base_url}/analyze/{address}"

        try:
            resp = client.get(analyze_url)
        except httpx.RequestError as exc:
            print(f"[ERROR] Request failed for {address}: {exc}")
            continue

        if resp.status_code != 200:
            print(f"[ERROR] API returned status {resp.status_code} for {address}: {resp.text}")
            continue

        try:
            api_data = resp.json()
        except Exception:
            print(f"[ERROR] Failed to parse JSON response for {address}")
            continue

        api_linked = bool(api_data.get("linked", False))
        behavior_score = api_data.get("behaviorScore", 0.0)
        evaluated_count += 1

        # Evaluate against confusion matrix
        if ground_truth is True and api_linked is True:
            tp += 1
        elif ground_truth is False and api_linked is True:
            fp += 1
            false_positives.append({
                "address": address,
                "role": role,
                "behaviorScore": behavior_score,
                "signals": api_data.get("signals", []),
                "reason": api_data.get("reason", ""),
            })
        elif ground_truth is False and api_linked is False:
            tn += 1
        elif ground_truth is True and api_linked is False:
            fn += 1
            false_negatives.append({
                "address": address,
                "role": role,
                "behaviorScore": behavior_score,
                "signals": api_data.get("signals", []),
                "reason": api_data.get("reason", ""),
            })

    # Calculations
    precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    f1_score = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    accuracy = ((tp + tn) / evaluated_count) if evaluated_count > 0 else 0.0

    # Print Report
    print("=" * 72)
    print("                 STAKEOUT GRAPH SERVICE ACCURACY BENCHMARK")
    print("=" * 72)
    print(f"API Endpoint:       {api_base_url}/analyze/{{address}}")
    print(f"Ground-Truth File:  {scenarios_path}")
    print(f"Evaluated Wallets:  {evaluated_count}")
    print("-" * 72)

    print("CONFUSION MATRIX:")
    print(f"  True Positives  (TP) : {tp:<4} [Flagged by API, and is a scam]")
    print(f"  False Positives (FP) : {fp:<4} [Flagged by API, but is innocent]")
    print(f"  True Negatives  (TN) : {tn:<4} [Not flagged by API, and is innocent]")
    print(f"  False Negatives (FN) : {fn:<4} [Not flagged by API, but is a scam]")
    print("-" * 72)

    print("METRICS:")
    print(f"  Precision : {precision:.4f} ({precision * 100:.2f}%)  [TP / (TP + FP)]")
    print(f"  Recall    : {recall:.4f} ({recall * 100:.2f}%)  [TP / (TP + FN)]")
    print(f"  F1 Score  : {f1_score:.4f}")
    print(f"  Accuracy  : {accuracy:.4f} ({accuracy * 100:.2f}%)")
    print("-" * 72)

    # Print False Positives
    print(f"FALSE POSITIVES (Innocent wallets wrongly flagged) - Count: {len(false_positives)}")
    if false_positives:
        for idx, item in enumerate(false_positives, start=1):
            print(f"  {idx}. Address: {item['address']}")
            print(f"     Role: {item['role']} | Score: {item['behaviorScore']}")
            print(f"     Reason: {item['reason']}")
    else:
        print("  None (Zero false positives)")
    print("-" * 72)

    # Print False Negatives
    print(f"FALSE NEGATIVES (Scam wallets missed by API) - Count: {len(false_negatives)}")
    if false_negatives:
        for idx, item in enumerate(false_negatives, start=1):
            print(f"  {idx}. Address: {item['address']}")
            print(f"     Role: {item['role']} | Score: {item['behaviorScore']}")
            print(f"     Reason: {item['reason']}")
    else:
        print("  None (Zero false negatives)")
    print("=" * 72 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate Stakeout Graph Service accuracy against scenario ground truth."
    )
    parser.add_argument(
        "--api-url",
        default=f"http://127.0.0.1:{GRAPH_SERVICE_PORT}",
        help=f"Base URL of Graph Service API (default: http://127.0.0.1:{GRAPH_SERVICE_PORT})",
    )
    parser.add_argument(
        "--scenarios-file",
        type=Path,
        default=DEFAULT_SCENARIOS_FILE,
        help="Path to scenarios.json file",
    )
    args = parser.parse_args()

    run_evaluation(
        api_base_url=args.api_url.rstrip("/"),
        scenarios_path=args.scenarios_file,
    )


if __name__ == "__main__":
    main()
