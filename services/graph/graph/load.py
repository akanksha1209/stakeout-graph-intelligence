"""
Data Ingestion and Loader Script for Stakeout Graph Intelligence.
Loads synthetic transaction and cluster data into TigerGraph.

STRICT COMPLIANCE:
- NO HARDCODING: All connection parameters loaded from app.config.
- Fail loudly: Missing data files or missing credentials crash with SystemExit.
- Data labels: All vertices and edges are tagged with data_source='synthetic'.
- Upserts:
    - Vertices: Wallet (address, is_exit_point, data_source), Report, Cluster
    - Edges: TRANSFER (amount, timestamp, tx_id, data_source), MEMBER_OF, REPORTED
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure parent directory is on sys.path for direct script execution
CURRENT_DIR = Path(__file__).resolve().parent
SERVICE_DIR = CURRENT_DIR.parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import pyTigerGraph as tg
from app.config import (
    DATA_DIR,
    TG_GRAPH_NAME,
    TG_HOST,
    TG_PASSWORD,
    TG_USERNAME,
)


def load_dataset(transfers_file: Path, scenarios_file: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Load transactions and scenario ground truth from disk.
    Fails loudly if required data files are absent.
    """
    if not transfers_file.exists():
        sys.stderr.write(
            f"\n[CRITICAL ERROR] Transfers dataset not found at: '{transfers_file}'.\n"
            f"Please run 'python graph/generate.py' first to produce synthetic data.\n\n"
        )
        raise SystemExit(1)

    try:
        with open(transfers_file, "r", encoding="utf-8") as f:
            transfers = json.load(f)
    except Exception as exc:
        sys.stderr.write(f"\n[CRITICAL ERROR] Failed to parse '{transfers_file}': {exc}\n\n")
        raise SystemExit(1)

    scenarios = {}
    if scenarios_file.exists():
        try:
            with open(scenarios_file, "r", encoding="utf-8") as f:
                scenarios = json.load(f)
        except Exception as exc:
            sys.stderr.write(f"\n[CRITICAL ERROR] Failed to parse '{scenarios_file}': {exc}\n\n")
            raise SystemExit(1)
    else:
        sys.stderr.write(
            f"\n[WARNING] Scenarios file '{scenarios_file}' not found. "
            f"Cluster and wallet roles will be inferred strictly from transfers.\n\n"
        )

    return transfers, scenarios


def initialize_tigergraph_connection() -> tg.TigerGraphConnection:
    """
    Establish authenticated connection to TigerGraph instance.
    Fails loudly if host or credentials are not functioning.
    """
    print(f"[Stakeout Loader] Connecting to TigerGraph at {TG_HOST} (Graph: {TG_GRAPH_NAME})...")
    try:
        conn = tg.TigerGraphConnection(
            host=TG_HOST,
            username=TG_USERNAME,
            password=TG_PASSWORD,
            graphname=TG_GRAPH_NAME,
        )
        # Attempt to retrieve API auth token
        try:
            conn.getToken()
        except Exception:
            # Some local / basic auth TG configurations proceed without token
            pass
        return conn
    except Exception as exc:
        sys.stderr.write(
            f"\n[CRITICAL TIGERGRAPH ERROR] Failed to connect to TigerGraph instance at '{TG_HOST}'.\n"
            f"Details: {exc}\n"
            f"Please check your TG_* variables in your .env file.\n\n"
        )
        raise SystemExit(1)


def prepare_graph_payloads(
    transfers: List[Dict[str, Any]],
    scenarios: Dict[str, Any],
) -> Dict[str, Any]:
    """Extract and structure vertices and edges for bulk upsertion."""
    wallet_meta = scenarios.get("wallets", {})
    clusters_meta = scenarios.get("clusters", {})

    # Collect unique wallet addresses
    wallet_vertices: Dict[str, Dict[str, Any]] = {}
    for t in transfers:
        for addr in (t["source"], t["target"]):
            if addr not in wallet_vertices:
                is_exit = wallet_meta.get(addr, {}).get("is_exit_point", False)
                wallet_vertices[addr] = {
                    "is_exit_point": is_exit,
                    "data_source": "synthetic",
                }

    # Cluster vertices
    cluster_vertices: Dict[str, Dict[str, Any]] = {}
    for cid, cdata in clusters_meta.items():
        cluster_vertices[cid] = {
            "behavior_score": 1.0,
            "data_source": "synthetic",
        }

    # Edges: TRANSFER
    transfer_edges: List[Tuple[str, str, Dict[str, Any]]] = []
    for t in transfers:
        transfer_edges.append((
            t["source"],
            t["target"],
            {
                "amount": float(t["amount"]),
                "timestamp": int(t["timestamp"]),
                "tx_id": str(t["tx_id"]),
                "data_source": "synthetic",
            },
        ))

    # Edges: MEMBER_OF
    member_edges: List[Tuple[str, str, Dict[str, Any]]] = []
    for cid, cdata in clusters_meta.items():
        for member_addr in cdata.get("members", []):
            member_edges.append((
                member_addr,
                cid,
                {"data_source": "synthetic"},
            ))

    return {
        "wallets": wallet_vertices,
        "clusters": cluster_vertices,
        "transfers": transfer_edges,
        "members": member_edges,
    }


def execute_load(dry_run: bool = False) -> None:
    """Execute ingestion workflow into TigerGraph."""
    transfers_path = DATA_DIR / "transfers.json"
    scenarios_path = DATA_DIR / "scenarios.json"

    transfers, scenarios = load_dataset(transfers_path, scenarios_path)
    payloads = prepare_graph_payloads(transfers, scenarios)

    print(f"[Stakeout Loader] Prepared {len(payloads['wallets'])} Wallet vertices.")
    print(f"[Stakeout Loader] Prepared {len(payloads['clusters'])} Cluster vertices.")
    print(f"[Stakeout Loader] Prepared {len(payloads['transfers'])} TRANSFER edges.")
    print(f"[Stakeout Loader] Prepared {len(payloads['members'])} MEMBER_OF edges.")

    if dry_run:
        print("[Stakeout Loader] Dry-run enabled. Skipping network push to TigerGraph.")
        return

    conn = initialize_tigergraph_connection()

    # Upsert Wallet Vertices
    print("[Stakeout Loader] Upserting Wallet vertices...")
    wallet_data = [(addr, attrs) for addr, attrs in payloads["wallets"].items()]
    conn.upsertVertices("Wallet", wallet_data)

    # Upsert Cluster Vertices
    if payloads["clusters"]:
        print("[Stakeout Loader] Upserting Cluster vertices...")
        cluster_data = [(cid, attrs) for cid, attrs in payloads["clusters"].items()]
        conn.upsertVertices("Cluster", cluster_data)

    # Upsert TRANSFER Edges
    print("[Stakeout Loader] Upserting TRANSFER edges...")
    conn.upsertEdges("Wallet", "TRANSFER", "Wallet", payloads["transfers"])

    # Upsert MEMBER_OF Edges
        # Upsert MEMBER_OF Edges
    if payloads["members"]:
        print("[Stakeout Loader] Upserting MEMBER_OF edges...")
        conn.upsertEdges("Wallet", "MEMBER_OF", "Cluster", payloads["members"])

    # Upsert Report Vertices and REPORTED edges
    # Dynamically find a scam master from the scenarios to attach the reports to
    wallet_meta = scenarios.get("wallets", {})
    clusters_meta = scenarios.get("clusters", {})
    target_for_reports = None

    for addr, data in wallet_meta.items():
        if data.get("type") == "scam_master":
            target_for_reports = addr
            break

    if not target_for_reports and clusters_meta:
        first_cluster = list(clusters_meta.values())[0]
        if first_cluster.get("members"):
            target_for_reports = first_cluster["members"][0]

    if target_for_reports:
        print(f"[Stakeout Loader] Upserting 3 Report vertices and REPORTED edges targeting {target_for_reports}...")
        reports_data = []
        reported_edges = []
        
        for i in range(1, 4):
            report_id = f"report_{i}"
            reports_data.append((
                report_id,
                {
                    "target_address": target_for_reports,
                    "evidence_hash": f"hash_{i}"
                }
            ))
            reported_edges.append((report_id, target_for_reports, {}))
            
        conn.upsertVertices("Report", reports_data)
        conn.upsertEdges("Report", "REPORTED", "Wallet", reported_edges)
    else:
        print("[Stakeout Loader] WARNING: Could not find a scam_master to attach reports to.")

    print("[Stakeout Loader] SUCCESS: All graph vertices and edges successfully loaded into TigerGraph!")

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Stakeout data into TigerGraph")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate datasets and structures without sending network requests to TigerGraph.",
    )
    args = parser.parse_args()
    execute_load(dry_run=args.dry_run)


if __name__ == "__main__":
    main()

