def policy(market, position):
    if position.signed_quantity > 0:
        if market.trade_imbalance < 0 or position.holding_time_ns >= 1000000000:
            return TargetPosition.FLAT
        return TargetPosition.LONG
    if market.book_imbalance > 0.2 and market.trade_imbalance > 0.2:
        return TargetPosition.LONG
    return TargetPosition.FLAT
