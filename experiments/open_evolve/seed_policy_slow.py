def policy(market, position):
    # Low-frequency style: enter only on strong one-sided book pressure,
    # hold near the 5-minute cap. Interpreted source, not an established alpha.
    if position.signed_quantity > 0:
        if position.holding_time_ns >= 240000000000:
            return TargetPosition.FLAT
        return TargetPosition.LONG
    if market.book_imbalance > 0.45:
        return TargetPosition.LONG
    return TargetPosition.FLAT
