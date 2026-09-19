def policy(market, position):
    # 30-minute trend rider: enter on strong aligned book/flow pressure and
    # hold until flow flips, the book turns against the position, an 8 bps
    # stop hits, or the 30-minute cap. Interpreted source, not an alpha.
    if position.signed_quantity > 0:
        if position.holding_time_ns >= 1_800_000_000_000:  # 30-minute cap
            return TargetPosition.FLAT
        if position.unrealized_return_bps is not None and position.unrealized_return_bps < -8:
            return TargetPosition.FLAT
        if market.trade_imbalance is not None and market.trade_imbalance < -0.3:
            return TargetPosition.FLAT
        if market.book_imbalance < -0.2:
            return TargetPosition.FLAT
        return TargetPosition.LONG
    if market.book_imbalance > 0.3:
        if market.trade_imbalance is not None and market.trade_imbalance > 0.15:
            return TargetPosition.LONG
        if market.ofi is not None and market.ofi > 0:
            return TargetPosition.LONG
    return TargetPosition.FLAT
