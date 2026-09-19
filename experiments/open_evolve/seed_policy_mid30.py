def policy(market, position):
    # Diagnostic: mid-episode entries (10 s <= episode age < 30 s),
    # hard 30 s exit. Tests the refined run006 hypothesis that the 30 s
    # edge peaks at mid-episode age. Interpreted source, not an alpha.
    if position.signed_quantity > 0:
        if position.holding_time_ns >= 30000000000:  # 30 s
            return TargetPosition.FLAT
        return TargetPosition.LONG
    if (market.book_imbalance is not None and market.book_imbalance > 0.45
            and market.one_sidedness_age_ns is not None
            and 10000000000 <= market.one_sidedness_age_ns < 30000000000):
        return TargetPosition.LONG
    return TargetPosition.FLAT
