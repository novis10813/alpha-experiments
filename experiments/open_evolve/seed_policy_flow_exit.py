def policy(market, position):
    # Medium-frequency style: dual-condition entry with tight exits
    # (flow-reversal, -3 bps stop, 2-minute time stop).
    # Interpreted source, not an established alpha.
    if position.signed_quantity > 0:
        if position.holding_time_ns >= 120000000000:
            return TargetPosition.FLAT
        if position.unrealized_return_bps is not None and position.unrealized_return_bps < -3:
            return TargetPosition.FLAT
        if market.trade_imbalance is not None and market.trade_imbalance < -0.2:
            return TargetPosition.FLAT
        return TargetPosition.LONG
    if market.trade_imbalance is not None and market.trade_imbalance > 0.3:
        if market.book_imbalance is not None and market.book_imbalance > 0.1:
            return TargetPosition.LONG
    return TargetPosition.FLAT
