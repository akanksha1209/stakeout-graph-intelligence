import datetime
from pathlib import Path
import sys
import json
import pyTigerGraph
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Ensure service directory is on sys.path
SERVICE_DIR = Path(__file__).resolve().parent.parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from app.config import TG_GRAPH_NAME, TG_HOST, TG_PASSWORD, TG_USERNAME
from graph.scoring import calculate_score
from graph.linking import determine_linking

app = FastAPI(title="Stakeout Graph Intelligence", version="2.0.0")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=False, 
    allow_methods=["*"], 
    allow_headers=["*"]
)

# Initialize TigerGraph connection
conn = pyTigerGraph.TigerGraphConnection(
    host=TG_HOST, 
    username=TG_USERNAME, 
    password=TG_PASSWORD, 
    graphname=TG_GRAPH_NAME
)

# Load rules safely
RULES_PATH = Path(__file__).resolve().parent.parent / "config" / "rules.json"
try:
    with open(RULES_PATH, "r") as f:
        RULES_CONFIG = json.load(f)
except Exception:
    RULES_CONFIG = {"behaviorScore": 0.60, "minSignals": 2, "repeatedFlowsMin": 2, "passThroughRatioMin": 0.4}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/analyze/{address}")
def analyze_wallet(address: str):
    cleaned_address = address.lower().strip()
    
    # Validate address format
    if not (cleaned_address.startswith("0x") and len(cleaned_address) == 42):
        raise HTTPException(status_code=400, detail="Invalid address format. Expected 0x + 40 hex chars.")

    try:
        # Run the V1 GSQL query
        query_results = conn.runInstalledQuery("analyze_wallet", {"target_address": cleaned_address})
        
        if not query_results or len(query_results) == 0:
            raise HTTPException(status_code=404, detail="Wallet not found in graph database.")
            
        r = query_results[0]
        
        # Helper to handle TigerGraph returning either a scalar or a list
        def get_val(key, default=0):
            val = r.get(key, default)
            if isinstance(val, list):
                return val[0] if val else default
            return val

        # Check if wallet exists
        if get_val("found") == 0:
            raise HTTPException(status_code=404, detail="Wallet not found in graph database.")

        # Extract Metrics
        total_in = float(get_val("total_in", 0.0))
        total_out = float(get_val("total_out", 0.0))
        in_degree = int(get_val("in_degree", 0))
        out_degree = int(get_val("out_degree", 0))
        
        # Calculate Score
        score_result = calculate_score({
            "totalIn": total_in, 
            "totalOut": total_out, 
            "fanIn": in_degree, 
            "fanOut": out_degree
        })

        # Apply Linking Rules
        wallet_facts = {
            "isKnownVictim": len(r.get("reporters", [])) > 0,
            "incoming": in_degree,
            "outgoing": out_degree,
            "outflowsToCluster": int(get_val("outflows_to_cluster", 0)),
            "fundedByCluster": 1 if in_degree > 0 else 0,
            "passThroughRatio": score_result.get("passThroughRatio", 0.0)
        }
        
        is_linked, link_reason = determine_linking(wallet_facts, RULES_CONFIG)
        
        # Extract Cluster Data safely
        cluster_ids = r.get("clusterIds", [])
        real_cluster_id = cluster_ids[0] if isinstance(cluster_ids, list) and cluster_ids else None
        
        members_raw = r.get("membersList", [])
        # Team Lead requirement: Return empty list if no cluster
        members = members_raw if isinstance(members_raw, list) and real_cluster_id else []
        
        exit_points_raw = r.get("exitPointsList", [])
        exit_points = exit_points_raw if isinstance(exit_points_raw, list) else []

        return {
            "target": cleaned_address,
            "clusterId": real_cluster_id,
            "behaviorScore": score_result["behaviorScore"],
            "signals": score_result.get("signals", []),
            "metrics": score_result.get("signalDetails", []),
            "members": members,
            "exitPoints": exit_points,
            "unrelatedReporterCount": len(r.get("reporters", [])),
            "linked": is_linked,
            "reason": link_reason,
            "dataSource": "synthetic",
            "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"TigerGraph execution failed: {str(exc)}")


@app.get("/cluster/{clusterId}/graph")
def get_cluster_graph(clusterId: str):
    # Validate clusterId format
    if not (clusterId.startswith("0x") and len(clusterId) == 66):
        raise HTTPException(status_code=400, detail="Invalid clusterId format.")

    try:
        query_results = conn.runInstalledQuery("get_cluster_graph", {"target_cluster": clusterId})
        
        nodes, edges, seen_nodes = [], [], set()
        
        for res in query_results:
            if "Members" in res:
                for m in res["Members"]:
                    addr = m["attributes"]["address"]
                    if addr not in seen_nodes:
                        seen_nodes.add(addr)
                        nodes.append({
                            "id": addr,
                            "role": "exit_point" if m["attributes"].get("is_exit_point") else "member",
                            "dataSource": m["attributes"].get("data_source", "synthetic")
                        })
            if "transfers" in res:
                for e in res["transfers"]:
                    edges.append({
                        "source": e["from_id"], 
                        "target": e["to_id"],
                        "amount": e["attributes"].get("amount", 0),
                        "timestamp": e["attributes"].get("timestamp", 0),
                        "txId": e["attributes"].get("tx_id", ""),
                        "dataSource": e["attributes"].get("data_source", "synthetic")
                    })
                    
        return {"clusterId": clusterId, "nodes": nodes, "edges": edges}
        
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)