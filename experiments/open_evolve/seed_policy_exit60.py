def policy(market, position):
    # Diagnostic: slow-seed entry with a hard 60-second unconditional exit.
    # Companion to seed_policy_exit30.py for the holding-time decay curve.
    # Interpreted source, not an established alpha.
    if position.signed_quantity > 0:
        if position.holding_time_ns >= 60000000000:  # 60 s
            return TargetPosition.FLAT
        return TargetPosition.LONG
    if market.book_imbalance > 0.45:
        return TargetPosition.LONG
    return TargetPosition.FLAT
