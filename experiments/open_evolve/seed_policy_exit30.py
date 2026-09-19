def policy(market, position):
    # Diagnostic: slow-seed entry with a hard 30-second unconditional exit.
    # Measures whether the 30s entry markout is capturable as PnL.
    # Interpreted source, not an established alpha.
    if position.signed_quantity > 0:
        if position.holding_time_ns >= 30000000000:  # 30 s
            return TargetPosition.FLAT
        return TargetPosition.LONG
    if market.book_imbalance > 0.45:
        return TargetPosition.LONG
    return TargetPosition.FLAT
