def policy(market, position):
    # Diagnostic: onset entries (episode age < 5 s) with a 60 s hard exit.
    # Companion to seed_policy_onset30.py: onset-subset decay 30 s -> 60 s.
    # Interpreted source, not an established alpha.
    if position.signed_quantity > 0:
        if position.holding_time_ns >= 60000000000:  # 60 s
            return TargetPosition.FLAT
        return TargetPosition.LONG
    if (market.book_imbalance is not None and market.book_imbalance > 0.45
            and market.one_sidedness_age_ns is not None
            and market.one_sidedness_age_ns < 5000000000):
        return TargetPosition.LONG
    return TargetPosition.FLAT
