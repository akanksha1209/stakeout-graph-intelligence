# Stakeout Graph Intelligence Service (`services/graph`)

The Graph & Data Intelligence engine for **Stakeout** — a real-time crypto scam oracle for hackathon defense. This service ingests blockchain transactions, executes TigerGraph topological queries, detects money laundering syndicates, and scores suspicious behaviors.

---

## 👥 Teammate Deliverables

### For Person 2 (Backend & Smart Contract Oracle)
- **Analysis Schema Draft**: [`drafts/analysis.schema.draft.json`](drafts/analysis.schema.draft.json)
- **Scoring Weights & Thresholds**: [`drafts/scoring.draft.json`](drafts/scoring.draft.json)
- **Analysis Endpoint**: `GET /analyze/{address}`
  - Returns risk assessment, `behaviorScore` ($0.0 - 1.0$), triggered signals, and cluster linkage.
  - **Cluster ID format**: `bytes32` (`0x` prefix followed by exactly 64 hex characters), ready for on-chain storage and oracle ingestion.
  - Provenance tagged with `"dataSource": "synthetic"` (or `"testnet"`).

### For Person 3 (Frontend Visualization)
- **Cluster Subgraph Endpoint**: `GET /cluster/{clusterId}/graph`
  - Returns `{ "nodes": [...], "edges": [...] }` formatted for Cytoscape, React Flow, or D3.js.
  - Nodes include roles (`scam_master`, `layering_intermediate`, `exit_point`, `counterparty`), exit point flags, and addresses.
  - Edges include transaction hashes (`txId`), amounts, timestamps, and labels.

---

## 📁 File Structure

```
services/graph/
├── .env.example                       # Environment configuration template
├── .env                               # Local active environment (not tracked)
├── requirements.txt                   # Service dependencies
├── README.md                          # Architecture and run instructions
├── app/
│   ├── __init__.py
│   ├── config.py                      # Fail-loud configuration loader (no hardcoding)
│   └── main.py                        # FastAPI service with CORS enabled (port 8001)
├── graph/
│   ├── __init__.py
│   ├── schema.gsql                    # TigerGraph vertex and edge schema definitions
│   ├── generate.py                    # Procedural synthetic scenario transaction generator
│   ├── load.py                        # pyTigerGraph data ingestion and batch loader
│   ├── scoring.py                     # Config-driven heuristic scam behavior scoring
│   └── evaluate.py                    # Accuracy benchmarking against scenarios ground-truth
├── drafts/
│   ├── analysis.schema.draft.json     # JSON Schema contract for oracle analysis responses
│   └── scoring.draft.json             # Heuristic weights and signal thresholds
└── data/
    ├── transfers.json                 # Synthetic transaction ledger (labeled "synthetic")
    └── scenarios.json                 # Ground truth scenario labels and cluster maps
```

---

## ⚙️ Environment Configuration

Copy `.env.example` to `.env` inside `services/graph/`:

```bash
cp .env.example .env
```

| Variable | Description | Default / Example |
|---|---|---|
| `TG_HOST` | TigerGraph Cloud or local instance URL | `https://your-instance.i.tgcloud.io` |
| `TG_USERNAME` | TigerGraph username | `tigergraph` |
| `TG_PASSWORD` | TigerGraph password | *(Required)* |
| `TG_GRAPH_NAME` | Graph name defined in GSQL | `StakeoutGraph` |
| `SCENARIO_SEED` | Seed for deterministic pseudo-random scenario generator | `42` |
| `GRAPH_SERVICE_PORT` | Port for FastAPI server | `8001` |

> [!IMPORTANT]
> **AGENTS.md Strict Rule Compliance**:
> 1. **No Hardcoding**: No addresses, cluster IDs, thresholds, or API credentials exist in code.
> 2. **Fail Loudly**: If any required environment variable or config file is missing, the process terminates immediately with an explicit error.
> 3. **Data Labels**: Every synthetic transaction, scenario, vertex, and edge is tagged with `data_source: "synthetic"`.

---

## 🚀 Setup & Execution Instructions

### 1. Install Dependencies

Using `pip` or `uv`:

```bash
cd services/graph
pip install -r requirements.txt
```

### 2. Generate Synthetic Scenarios & Ground Truth

Generates the 6 required scenarios into `data/transfers.json` and `data/scenarios.json`:
1. **Scam Cluster**: 4 victims funnel into 1 master wallet $\to$ master splits to 3 layering wallets $\to$ merges into 1 exit point.
2. **Rotation**: Exit point funds a fresh address which immediately hops/forwards funds.
3. **Framing**: 3 fresh burner addresses send micro-dust to an innocent wallet.
4. **Dusting**: Scam cluster member sends dust to an investigative critic wallet.
5. **Hard Negative**: Commercial merchant with high fan-in/fan-out and organic delays.
6. **Noise**: Normal peer-to-peer transaction pairs.

Run:
```bash
python graph/generate.py
```

### 3. Load Data into TigerGraph

To test and validate the payload parsing without network access:
```bash
python graph/load.py --dry-run
```

To ingest live vertices (`Wallet`, `Cluster`, `Report`) and edges (`TRANSFER`, `MEMBER_OF`, `REPORTED`) into TigerGraph:
```bash
python graph/load.py
```

### 4. Start the FastAPI Service

Run the server on port 8001 (or configured `GRAPH_SERVICE_PORT`):
```bash
python app/main.py
```
Or with Uvicorn directly:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

### 5. Evaluate Oracle Accuracy Benchmark

Compares ground truth from `data/scenarios.json` against `/analyze` endpoint predictions to calculate Confusion Matrix, Precision, Recall, and identify any False Positives / False Negatives:
```bash
python graph/evaluate.py
```

---

## 📡 API Reference

### 1. Health Check
`GET /health`
```json
{
  "status": "ok"
}
```

### 2. Analyze Wallet
`GET /analyze/{address}`
- **Param**: `address` (e.g. `0x8ba8f83718aa8f3bd1f65e8144e61d9ab30fcb06`)
- **Response**:
```json
{
  "target": "0x8ba8f83718aa8f3bd1f65e8144e61d9ab30fcb06",
  "clusterId": "0x806999e7692593a57fb87637f87fe82a9b08fdea0fdd31f1ba34cb697290400b",
  "behaviorScore": 0.9,
  "signals": [
    "fanIn",
    "fanOut",
    "passThroughRatio",
    "medianForwardTime",
    "hopsToExit"
  ],
  "members": [
    "0x8ba8f83718aa8f3bd1f65e8144e61d9ab30fcb06",
    "0xa6c1ad8f2906e732b10f4db789d35ea68c088ab3",
    "0xf648818ba4a6656be0cb6e382a5dff72ac1dda96",
    "0x908137478bd536cf4b778ade1fe7a9010b3341c2",
    "0xbd2b4acec46edf287a43b9b21175306c76a81a57"
  ],
  "exitPoints": [
    "0xbd2b4acec46edf287a43b9b21175306c76a81a57"
  ],
  "linked": true,
  "reason": "High scam risk detected (score: 0.9). Triggered signals: fanIn, fanOut, passThroughRatio, medianForwardTime, hopsToExit. Associated with cluster 0x806999e7... containing 5 nodes.",
  "dataSource": "synthetic",
  "createdAt": "2026-10-28T16:06:19.950449+00:00"
}
```

### 3. Cluster Graph Visualization
`GET /cluster/{clusterId}/graph`
- **Param**: `clusterId` (bytes32 hex: `0x` + 64 hex characters)
- **Response**:
```json
{
  "clusterId": "0x806999e7692593a57fb87637f87fe82a9b08fdea0fdd31f1ba34cb697290400b",
  "nodes": [
    {
      "id": "0x8ba8f83718aa8f3bd1f65e8144e61d9ab30fcb06",
      "label": "Wallet",
      "role": "scam_master",
      "isExitPoint": false,
      "dataSource": "synthetic"
    },
    {
      "id": "0xbd2b4acec46edf287a43b9b21175306c76a81a57",
      "label": "Wallet",
      "role": "exit_point",
      "isExitPoint": true,
      "dataSource": "synthetic"
    }
  ],
  "edges": [
    {
      "id": "0x9767c2188e12e65b1364f5d8717b0d5803ca8d9aa6a3b7437ff59fce63911f0b",
      "source": "0x9d79b1a37f31801cd11a6706fb40d6bd57526846",
      "target": "0x8ba8f83718aa8f3bd1f65e8144e61d9ab30fcb06",
      "amount": 2.0557,
      "timestamp": 1700001157,
      "txId": "0x9767c2188e12e65b1364f5d8717b0d5803ca8d9aa6a3b7437ff59fce63911f0b",
      "label": "TRANSFER",
      "dataSource": "synthetic"
    }
  ]
}
```

