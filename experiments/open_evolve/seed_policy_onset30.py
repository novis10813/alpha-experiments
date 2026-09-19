def policy(market, position):
    # Diagnostic: enter only at episode onset (book_imbalance > 0.45 and
    # episode age < 5 s), hard 30 s exit. No re-entry into a continuing
    # episode. Tests whether the onset subset carries the 30 s edge.
    # Interpreted source, not an established alpha.
    if position.signed_quantity > 0:
        if position.holding_time_ns >= 30000000000:  # 30 s
            return TargetPosition.FLAT
        return TargetPosition.LONG
    if (market.book_imbalance is not None and market.book_imbalance > 0.45
            and market.one_sidedness_age_ns is not None
            and market.one_sidedness_age_ns < 5000000000):
        return TargetPosition.LONG
    return TargetPosition.FLAT
