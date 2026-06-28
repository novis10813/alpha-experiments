import unittest
from dataclasses import dataclass


@dataclass(frozen=True)
class Quote:
    bid: float
    ask: float


class CommonExecutionTests(unittest.TestCase):
    def test_quote_execution_return_uses_bid_ask_by_side(self):
        from common.execution import net_return
        from common.execution import quote_execution_return
        from common.execution import side_from_alpha

        entry = Quote(bid=100, ask=101)
        exit_quote = Quote(bid=103, ask=104)

        self.assertAlmostEqual(quote_execution_return(1, entry, exit_quote), (103 / 101) - 1)
        self.assertAlmostEqual(quote_execution_return(-1, entry, exit_quote), (100 / 104) - 1)
        self.assertEqual(quote_execution_return(0, entry, exit_quote), 0.0)
        self.assertAlmostEqual(net_return(0.01, 2), 0.0098)
        self.assertEqual(side_from_alpha(-0.5), -1)


if __name__ == "__main__":
    unittest.main()

