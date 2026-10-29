"""
FastAPI Service for Stakeout Graph Intelligence.
Integrates live TigerGraph GSQL queries for scam oracle risk analysis and cluster topology.

STRICT COMPLIANCE:
- NO hardcoded wallet addresses, API keys, or environment variables.
- All configuration imported from app/config.py.
- All data items labeled with dataSource: 'synthetic'.
"""

import datetime
from pathlib import Path
import sys
import pyTigerGraph
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Ensure service directory is on sys.path
SERVICE_DIR = Path(__file__).resolve().parent.parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from app.config import (
    GRAPH_SERVICE_PORT,
    TG_GRAPH_NAME,
    TG_HOST,
    TG_PASSWORD,
    TG_USERNAME,
)
from graph.scoring import calculate_score

app = FastAPI(
    title="Stakeout Graph Intelligence Service",
    description="Crypto scam oracle graph data service powered by TigerGraph",
    version="1.2.0",
)

# Enable CORS for frontend visualization integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize TigerGraph connection using config variables
conn = pyTigerGraph.TigerGraphConnection(
    host=TG_HOST,
    username=TG_USERNAME,
    password=TG_PASSWORD,
    graphname=TG_GRAPH_NAME,
)


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/analyze/{address}")
def analyze_wallet(address: str):
    """
    Analyze risk signals for a target wallet address using the installed TigerGraph GSQL query 'analyze_wallet'.
    """
    cleaned_address = address.strip()

    # Validate address format: must start with "0x" and be exactly 42 characters long
    if not (
        cleaned_address.startswith("0x")
        and len(cleaned_address) == 42
        and all(c in "0123456789abcdefABCDEF" for c in cleaned_address[2:])
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid address format. Address must start with '0x' and be exactly 42 characters long.",
        )

    # 1. Call installed GSQL query 'analyze_wallet'
    try:
        query_results = conn.runInstalledQuery("analyze_wallet", {"target_address": cleaned_address})
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"TigerGraph query execution failed: {str(exc)}",
        )

    
    

    # 2. Safely extract the first item from the result list: raw_data = query_results[0]["result"][0]
    raw_data = {}
    if (
        isinstance(query_results, list)
        and len(query_results) > 0
        and isinstance(query_results[0], dict)
    ):
        result_list = query_results[0].get("result", [])
        if isinstance(result_list, list) and len(result_list) > 0 and isinstance(result_list[0], dict):
            raw_data = result_list[0]
        elif isinstance(result_list, dict):
            raw_data = result_list
    elif isinstance(query_results, dict):
        result_list = query_results.get("result", [])
        if isinstance(result_list, list) and len(result_list) > 0 and isinstance(result_list[0], dict):
            raw_data = result_list[0]
        elif isinstance(result_list, dict):
            raw_data = result_list

    # 3. Extract metrics by checking BOTH root level and "attributes" dictionary
    attrs = raw_data.get("attributes", raw_data)
    if not isinstance(attrs, dict):
        attrs = raw_data

    try:
        total_in = float(attrs.get("total_in", raw_data.get("total_in", 0.0)) or 0.0)
    except (ValueError, TypeError):
        total_in = 0.0

    try:
        total_out = float(attrs.get("total_out", raw_data.get("total_out", 0.0)) or 0.0)
    except (ValueError, TypeError):
        total_out = 0.0
    if total_in == 0.0 and total_out == 0.0:
        raise HTTPException(
            status_code=404,
            detail="Wallet not found in graph database. No transactions found for this address."
        )


    try:
        in_degree = int(attrs.get("in_degree", raw_data.get("in_degree", 0)) or 0)
    except (ValueError, TypeError):
        in_degree = 0

    try:
        out_degree = int(attrs.get("out_degree", raw_data.get("out_degree", 0)) or 0)
    except (ValueError, TypeError):
        out_degree = 0

    # 4. Calculate score using scoring engine (No hardcoding)
    score_result = calculate_score({
        "totalIn": total_in,
        "totalOut": total_out,
        "fanIn": in_degree,
        "fanOut": out_degree,
    })

    behavior_score = score_result["behaviorScore"]
    linked = score_result["linked"]
    signals = score_result["signalDetails"]

    fired_signals = score_result.get("signals", [])
    dynamic_reason = f"Triggered signals: {', '.join(fired_signals)}" if fired_signals else "Behavior below threshold."
    # 5. Return exact JSON schema required
    return {
        "target": cleaned_address,
        "clusterId": "0x" + "0" * 64,
        "behaviorScore": behavior_score,
        "signals": signals,
        "members": [],
        "exitPoints": [],
        "linked": linked,
        "reason": dynamic_reason,
        "dataSource": "synthetic",
        "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@app.get("/cluster/{clusterId}/graph")
def get_cluster_graph(clusterId: str):
    """
    Returns graph topology (nodes and edges) for a cluster using the installed
    TigerGraph GSQL query 'get_cluster_graph'.
    """
    # 1. Validate that clusterId matches a bytes32 format (0x + 64 hex chars)
    if not (
        clusterId.startswith("0x")
        and len(clusterId) == 66
        and all(c in "0123456789abcdefABCDEF" for c in clusterId[2:])
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid clusterId format. Expected 0x followed by 64 hex characters (bytes32).",
        )

    # 2. Run the installed GSQL query 'get_cluster_graph'
    try:
        query_results = conn.runInstalledQuery("get_cluster_graph", {"target_cluster": clusterId})
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"TigerGraph query execution failed: {str(exc)}",
        )

    # 3. Parse the TigerGraph output for Members (wallets) and Transfers (edges)
    members_raw = []
    transfers_raw = []

    if isinstance(query_results, list):
        for item in query_results:
            if isinstance(item, dict):
                for k, v in item.items():
                    if k.lower() == "members":
                        members_raw = v if isinstance(v, list) else [v]
                    elif k.lower() == "transfers":
                        transfers_raw = v if isinstance(v, list) else [v]
    elif isinstance(query_results, dict):
        for k, v in query_results.items():
            if k.lower() == "members":
                members_raw = v if isinstance(v, list) else [v]
            elif k.lower() == "transfers":
                transfers_raw = v if isinstance(v, list) else [v]

    # 6. If the cluster is not found, raise an HTTPException
    if not members_raw:
        raise HTTPException(
            status_code=404,
            detail=f"Cluster '{clusterId}' not found.",
        )

    # 4 & 5. Return JSON matching exact frontend format with dataSource='synthetic'
    nodes = []
    seen_nodes = set()

    for m in members_raw:
        if isinstance(m, dict):
            node_id = (
                m.get("v_id")
                or m.get("id")
                or m.get("address")
                or (m.get("attributes", {}).get("address") if isinstance(m.get("attributes"), dict) else None)
            )
        elif isinstance(m, str):
            node_id = m
        else:
            node_id = str(m)

        if node_id and node_id not in seen_nodes:
            seen_nodes.add(node_id)
            nodes.append({
                "id": node_id,
                "label": "Wallet",
                "dataSource": "synthetic",
            })

    edges = []
    for t in transfers_raw:
        if isinstance(t, dict):
            source = t.get("from_id") or t.get("source") or t.get("from") or t.get("from_v")
            target = t.get("to_id") or t.get("target") or t.get("to") or t.get("to_v")
            edge_label = t.get("e_type") or t.get("label") or "TRANSFER"
            if source and target:
                edges.append({
                    "source": str(source),
                    "target": str(target),
                    "label": str(edge_label),
                    "dataSource": "synthetic",
                })

    # Ensure any endpoint from transfers is included in nodes
    for e in edges:
        for endpoint in (e["source"], e["target"]):
            if endpoint not in seen_nodes:
                seen_nodes.add(endpoint)
                nodes.append({
                    "id": endpoint,
                    "label": "Wallet",
                    "dataSource": "synthetic",
                })

    return {
        "nodes": nodes,
        "edges": edges,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=GRAPH_SERVICE_PORT)
