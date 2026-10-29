import json
import pyTigerGraph as tg
from app.config import TG_HOST, TG_USERNAME, TG_PASSWORD, DATA_DIR

print("Seeding data...")
conn = tg.TigerGraphConnection(host=TG_HOST, username=TG_USERNAME, password=TG_PASSWORD, graphname="StakeoutFinal")

with open(DATA_DIR / "transfers.json", "r") as f:
    transfers = json.load(f)

wallets = set()
for t in transfers:
    wallets.add(t["source"])
    wallets.add(t["target"])

wallet_data = [(w, {"is_exit_point": False, "data_source": "synthetic"}) for w in wallets]
conn.upsertVertices("Wallet", wallet_data)

edge_data = [(t["source"], t["target"], {"amount": float(t["amount"]), "timestamp": int(t["timestamp"]), "tx_id": str(t["tx_id"]), "data_source": "synthetic"}) for t in transfers]
conn.upsertEdges("Wallet", "TRANSFER", "Wallet", edge_data)

print("Data Seeded.")
