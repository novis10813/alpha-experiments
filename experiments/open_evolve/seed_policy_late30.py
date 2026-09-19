def policy(market, position):
    # Diagnostic: late-episode entries (episode age >= 30 s), hard 30 s exit.
    # Completes the age grid with onset (<5 s, run006) and mid (10-30 s).
    # Interpreted source, not an established alpha.
    if position.signed_quantity > 0:
        if position.holding_time_ns >= 30000000000:  # 30 s
            return TargetPosition.FLAT
        return TargetPosition.LONG
    if (market.book_imbalance is not None and market.book_imbalance > 0.45
            and market.one_sidedness_age_ns is not None
            and market.one_sidedness_age_ns >= 30000000000):
        return TargetPosition.LONG
    return TargetPosition.FLAT
