def policy(market, position):
    # Diagnostic control: enter only into continuing episodes
    # (book_imbalance > 0.45 and episode age >= 60 s), hard 30 s exit.
    # If the onset hypothesis holds, its 30 s markout should be ~0 while
    # seed_policy_onset30's is large.
    # Interpreted source, not an established alpha.
    if position.signed_quantity > 0:
        if position.holding_time_ns >= 30000000000:  # 30 s
            return TargetPosition.FLAT
        return TargetPosition.LONG
    if (market.book_imbalance is not None and market.book_imbalance > 0.45
            and market.one_sidedness_age_ns is not None
            and market.one_sidedness_age_ns >= 60000000000):
        return TargetPosition.LONG
    return TargetPosition.FLAT
