def determine_linking(wallet_data: dict, rules_config: dict) -> tuple[bool, str]:
    if wallet_data.get("isKnownVictim", False):
        return False, "Known victim excluded."
    if wallet_data.get("incoming", 0) > 0 and wallet_data.get("outgoing", 0) == 0:
        return False, "Inbound funding ignored."
    if wallet_data.get("outflowsToCluster", 0) == 1:
        return False, "One-off payer excluded."
    if wallet_data.get("outflowsToCluster", 0) >= rules_config.get("repeatedFlowsMin", 2):
        return True, "Repeated structured outflow."
    if wallet_data.get("fundedByCluster", 0) > 0 and wallet_data.get("passThroughRatio", 0) >= rules_config.get("passThroughRatioMin", 0.4):
        return True, "Funded by cluster and forwards onward."
    return False, "Behavior below threshold."
