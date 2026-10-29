"""
Synthetic Blockchain Transaction Generator for Stakeout Graph Intelligence.
Generates deterministic synthetic transaction graphs and scenario benchmarks.

STRICT COMPLIANCE:
- NO HARDCODING: All addresses, cluster IDs, and transactions are generated
  procedurally using hashlib and random seeded exclusively by SCENARIO_SEED.
- Fails loudly on missing configuration.
- Data labels: All records, wallets, and edges are labeled data_source="synthetic".
- Outputs:
    - data/transfers.json (source, target, amount, timestamp, tx_id, data_source)
    - data/scenarios.json (comprehensive ground truth labels for oracle benchmarks)
"""

import hashlib
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure parent directory is on sys.path for direct script execution
CURRENT_DIR = Path(__file__).resolve().parent
SERVICE_DIR = CURRENT_DIR.parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from app.config import DATA_DIR, SCENARIO_SEED


def make_cluster_id(members: List[str]) -> str:
    """
    Generate a deterministic bytes32 cluster identifier.
    Sorts addresses lexicographically, computes SHA-256 hash,
    and formats as '0x' + 64 hexadecimal characters.

    Args:
        members: List of member wallet addresses.

    Returns:
        bytes32 hex string formatted as 0x + 64 hex chars.
    """
    if not members:
        raise ValueError("Cannot generate cluster ID for empty member list")
    
    sorted_members = sorted(m.lower().strip() for m in members)
    combined = "".join(sorted_members).encode("utf-8")
    digest = hashlib.sha256(combined).hexdigest()
    return f"0x{digest}"


def generate_eth_address(rng: random.Random) -> str:
    """
    Deterministically generate a synthetic 20-byte Ethereum address.
    Format: '0x' + 40 hex characters.
    """
    raw_bytes = rng.randbytes(20)
    return f"0x{raw_bytes.hex()}"


def generate_tx_id(rng: random.Random) -> str:
    """
    Deterministically generate a synthetic 32-byte transaction hash.
    Format: '0x' + 64 hex characters.
    """
    raw_bytes = rng.randbytes(32)
    return f"0x{raw_bytes.hex()}"


def create_transfer(
    source: str,
    target: str,
    amount: float,
    timestamp: int,
    rng: random.Random,
) -> Dict[str, Any]:
    """Create a standardized transfer record with required synthetic label."""
    return {
        "source": source,
        "target": target,
        "amount": round(amount, 6),
        "timestamp": timestamp,
        "tx_id": generate_tx_id(rng),
        "data_source": "synthetic",
    }


def generate_all_scenarios(seed: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Generate the 6 required scenarios using procedural pseudo-random logic.
    
    Scenarios generated:
    1. Scam Cluster: 4 victims send to 1 master -> master splits to 3 -> merges to 1 exit point.
    2. Rotation: Exit point funds a new wallet, which forwards onward.
    3. Framing: 3 fresh wallets send dust to an innocent wallet.
    4. Dusting: Scam cluster sends dust to a critic wallet.
    5. Hard Negative: Busy merchant with high fan-in/out, but innocent.
    6. Noise: Random normal wallets.
    """
    rng = random.Random(seed)
    base_timestamp = 1700000000  # Base epoch for coherent relative timestamps

    transfers: List[Dict[str, Any]] = []
    wallets: Dict[str, Dict[str, Any]] = {}
    scenarios_metadata: Dict[str, Any] = {}

    def register_wallet(
        address: str,
        role: str,
        scenario: str,
        is_exit_point: bool = False,
        is_scam: bool = False,
        cluster_id: str | None = None,
    ) -> None:
        wallets[address] = {
            "address": address,
            "role": role,
            "scenario": scenario,
            "is_exit_point": is_exit_point,
            "is_scam": is_scam,
            "cluster_id": cluster_id,
            "data_source": "synthetic",
        }

    # =========================================================================
    # SCENARIO 1: Scam Cluster
    # 4 victims -> 1 master -> 3 intermediate/layering wallets -> 1 exit point
    # =========================================================================
    victims = [generate_eth_address(rng) for _ in range(4)]
    master_wallet = generate_eth_address(rng)
    intermediates = [generate_eth_address(rng) for _ in range(3)]
    exit_point_wallet = generate_eth_address(rng)

    # Calculate cluster ID over all syndicate members (master + intermediates + exit)
    scam_members = [master_wallet] + intermediates + [exit_point_wallet]
    scam_cluster_id = make_cluster_id(scam_members)

    for v in victims:
        register_wallet(v, role="victim", scenario="scam_cluster", is_scam=False)
    register_wallet(master_wallet, role="scam_master", scenario="scam_cluster", is_scam=True, cluster_id=scam_cluster_id)
    for inter in intermediates:
        register_wallet(inter, role="layering_intermediate", scenario="scam_cluster", is_scam=True, cluster_id=scam_cluster_id)
    register_wallet(exit_point_wallet, role="exit_point", scenario="scam_cluster", is_exit_point=True, is_scam=True, cluster_id=scam_cluster_id)

    # 1a. Victims send funds to Master
    t_cursor = base_timestamp + 1000
    victim_amounts = [round(rng.uniform(1.5, 3.5), 4) for _ in range(4)]
    total_victims_amount = sum(victim_amounts)

    for v, amt in zip(victims, victim_amounts):
        t_cursor += rng.randint(60, 300)
        transfers.append(create_transfer(v, master_wallet, amt, t_cursor, rng))

    # 1b. Master splits funds to 3 intermediate layering wallets (Fan-out)
    split_amounts = [round(total_victims_amount / 3.0, 4) for _ in range(3)]
    t_cursor += 120  # Fast forwarding
    for inter, split_amt in zip(intermediates, split_amounts):
        t_cursor += rng.randint(30, 90)
        transfers.append(create_transfer(master_wallet, inter, split_amt, t_cursor, rng))

    # 1c. Intermediate layering wallets merge funds into Exit Point (Consolidation)
    for inter, split_amt in zip(intermediates, split_amounts):
        t_cursor += rng.randint(45, 180)
        # Minus slight transaction fee simulation
        exit_amt = round(split_amt * 0.995, 4)
        transfers.append(create_transfer(inter, exit_point_wallet, exit_amt, t_cursor, rng))

    scenarios_metadata["scam_cluster"] = {
        "cluster_id": scam_cluster_id,
        "description": "4 victims funnel to master, layered through 3 wallets, consolidated into 1 exit point.",
        "master": master_wallet,
        "victims": victims,
        "intermediates": intermediates,
        "exit_point": exit_point_wallet,
        "members": scam_members,
        "data_source": "synthetic",
    }

    # =========================================================================
    # SCENARIO 2: Rotation
    # Exit point funds a new wallet, which forwards onward
    # =========================================================================
    rotated_wallet = generate_eth_address(rng)
    forwarded_target = generate_eth_address(rng)
    register_wallet(rotated_wallet, role="rotated_address", scenario="rotation", is_scam=True, cluster_id=scam_cluster_id)
    register_wallet(forwarded_target, role="rotated_destination", scenario="rotation", is_scam=True)

    t_cursor += rng.randint(1800, 3600)
    rotation_amount = round(total_victims_amount * 0.95, 4)
    transfers.append(create_transfer(exit_point_wallet, rotated_wallet, rotation_amount, t_cursor, rng))

    t_cursor += rng.randint(120, 600)
    transfers.append(create_transfer(rotated_wallet, forwarded_target, round(rotation_amount * 0.99, 4), t_cursor, rng))

    scenarios_metadata["rotation"] = {
        "description": "Exit point funds new wallet which immediately forwards onward (address hopping).",
        "funded_by": exit_point_wallet,
        "rotated_wallet": rotated_wallet,
        "forwarded_target": forwarded_target,
        "data_source": "synthetic",
    }

    # =========================================================================
    # SCENARIO 3: Framing
    # 3 fresh wallets send dust to an innocent wallet
    # =========================================================================
    innocent_framed_wallet = generate_eth_address(rng)
    fresh_framing_wallets = [generate_eth_address(rng) for _ in range(3)]

    register_wallet(innocent_framed_wallet, role="framed_victim", scenario="framing", is_scam=False)
    for f in fresh_framing_wallets:
        register_wallet(f, role="framing_burner", scenario="framing", is_scam=False)

    for f in fresh_framing_wallets:
        t_cursor += rng.randint(300, 1200)
        dust_amount = round(rng.uniform(0.0001, 0.0008), 6)
        transfers.append(create_transfer(f, innocent_framed_wallet, dust_amount, t_cursor, rng))

    scenarios_metadata["framing"] = {
        "description": "3 fresh addresses send micro dust to an innocent target to simulate guilt by association.",
        "target": innocent_framed_wallet,
        "framing_wallets": fresh_framing_wallets,
        "data_source": "synthetic",
    }

    # =========================================================================
    # SCENARIO 4: Dusting
    # Scam cluster sends dust to a critic wallet
    # =========================================================================
    critic_wallet = generate_eth_address(rng)
    register_wallet(critic_wallet, role="critic_target", scenario="dusting", is_scam=False)

    t_cursor += rng.randint(600, 2400)
    dusting_amount = round(rng.uniform(0.0002, 0.0009), 6)
    # One of the scam intermediate wallets dusts the critic
    transfers.append(create_transfer(intermediates[0], critic_wallet, dusting_amount, t_cursor, rng))

    scenarios_metadata["dusting"] = {
        "description": "Scam cluster member sends dust to a critic address (tainting attack).",
        "sender": intermediates[0],
        "critic": critic_wallet,
        "dust_amount": dusting_amount,
        "data_source": "synthetic",
    }

    # =========================================================================
    # SCENARIO 5: Hard Negative
    # Busy merchant with high fan-in/out, but innocent
    # =========================================================================
    merchant_wallet = generate_eth_address(rng)
    customers = [generate_eth_address(rng) for _ in range(8)]
    suppliers = [generate_eth_address(rng) for _ in range(4)]

    register_wallet(merchant_wallet, role="merchant", scenario="hard_negative", is_scam=False)
    for c in customers:
        register_wallet(c, role="merchant_customer", scenario="hard_negative", is_scam=False)
    for s in suppliers:
        register_wallet(s, role="merchant_supplier", scenario="hard_negative", is_scam=False)

    # Merchant receives payments from diverse customers spread out over days
    t_merchant = base_timestamp + 86400
    for c in customers:
        t_merchant += rng.randint(1800, 7200)
        c_amt = round(rng.uniform(0.05, 1.2), 4)
        transfers.append(create_transfer(c, merchant_wallet, c_amt, t_merchant, rng))

    # Merchant pays regular supplier / settlement payouts at normal cadence
    for s in suppliers:
        t_merchant += rng.randint(3600, 14400)
        s_amt = round(rng.uniform(0.3, 1.8), 4)
        transfers.append(create_transfer(merchant_wallet, s, s_amt, t_merchant, rng))

    scenarios_metadata["hard_negative"] = {
        "description": "High fan-in and fan-out commercial merchant with legitimate organic cash flows.",
        "merchant": merchant_wallet,
        "customers": customers,
        "suppliers": suppliers,
        "data_source": "synthetic",
    }

    # =========================================================================
    # SCENARIO 6: Noise
    # Random normal wallets
    # =========================================================================
    noise_pairs = [(generate_eth_address(rng), generate_eth_address(rng)) for _ in range(4)]
    noise_transfers_meta = []
    t_noise = base_timestamp + 4000
    for sender, recipient in noise_pairs:
        register_wallet(sender, role="regular_user", scenario="noise", is_scam=False)
        register_wallet(recipient, role="regular_user", scenario="noise", is_scam=False)
        t_noise += rng.randint(500, 4000)
        n_amt = round(rng.uniform(0.1, 0.5), 4)
        transfers.append(create_transfer(sender, recipient, n_amt, t_noise, rng))
        noise_transfers_meta.append({"from": sender, "to": recipient, "amount": n_amt})

    scenarios_metadata["noise"] = {
        "description": "Normal peer-to-peer noise transactions.",
        "transactions": noise_transfers_meta,
        "data_source": "synthetic",
    }

    # Assemble scenarios ground truth
    scenarios_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "data_source": "synthetic",
        "clusters": {
            scam_cluster_id: {
                "scenario": "scam_cluster",
                "cluster_id": scam_cluster_id,
                "master": master_wallet,
                "members": scam_members,
                "exit_points": [exit_point_wallet],
                "data_source": "synthetic",
            }
        },
        "scenarios": scenarios_metadata,
        "wallets": wallets,
    }

    return transfers, scenarios_data


def main() -> None:
    """Generate datasets and persist them to data/transfers.json and data/scenarios.json."""
    print(f"[Stakeout Generator] Generating synthetic dataset using SCENARIO_SEED={SCENARIO_SEED}...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    transfers, scenarios_data = generate_all_scenarios(SCENARIO_SEED)

    transfers_path = DATA_DIR / "transfers.json"
    scenarios_path = DATA_DIR / "scenarios.json"

    with open(transfers_path, "w", encoding="utf-8") as f:
        json.dump(transfers, f, indent=2)

    with open(scenarios_path, "w", encoding="utf-8") as f:
        json.dump(scenarios_data, f, indent=2)

    print(f"[Stakeout Generator] SUCCESS: {len(transfers)} transfers written to {transfers_path}")
    print(f"[Stakeout Generator] SUCCESS: Scenario ground-truth written to {scenarios_path}")


if __name__ == "__main__":
    main()

