import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from data.orderbook_quotes import QuoteRow
from evolution.rules import validate_rule_dict


NS_MINUTE = 60_000_000_000
NS_SECOND = 1_000_000_000


def _state(ts, *, matched=True, close=100.0):
    return SimpleNamespace(
        ts_event=ts,
        return_60m=1.0 if matched else -1.0,
        signed_flow_persistence_5m=1.0 if matched else -1.0,
        depth10_obi_mean=1.0 if matched else -1.0,
    )


def _rule(confirmations=2):
    result = validate_rule_dict({
        "family_id": "trend-flow-confirmation-v1",
        "entry": {"conditions": [
            {"feature": "return_60m", "op": "gt", "value": 0},
            {"feature": "signed_flow_persistence_5m", "op": "gt", "value": 0},
            {"feature": "depth10_obi_mean", "op": "gt", "value": 0},
        ], "confirmations": confirmations},
        "exit": {"conditions": [{"feature": "return_15m", "op": "lt", "value": 0}], "confirmations": 1, "min_hold_bars": 1},
        "cooldown_bars": 0,
    })
    assert result.valid and result.spec is not None
    return result.spec


class EvolutionSignalDiagnosticTests(unittest.TestCase):
    def test_executable_bps_applies_bid_ask_and_both_fees(self):
        from evolution.signal_diagnostic import executable_bps

        gross, net = executable_bps(100.0, 101.0)
        self.assertAlmostEqual(gross, 100.0)
        self.assertAlmostEqual(net, ((101 * .999) / (100 * 1.001) - 1) * 10_000)
        self.assertLess(net, gross)

    def test_entry_confirmations_reset_on_gap_and_decluster_without_outcomes(self):
        from evolution.signal_diagnostic import collect_entry_events

        start = datetime(2026, 8, 29, tzinfo=UTC)
        timestamps = [start.timestamp() * 1_000_000_000 + index * NS_MINUTE for index in range(1, 130)]
        states = [_state(int(ts)) for ts in timestamps]
        # A gap resets the finite confirmation state and starts a new warmup.
        states[10].ts_event += NS_MINUTE
        events, exclusions = collect_entry_events(states, _rule(), start, start + timedelta(hours=2))
        self.assertEqual(len(events), 1)
        self.assertGreaterEqual(events[0], int(start.timestamp() * 1_000_000_000) + 60 * NS_MINUTE)
        self.assertGreater(exclusions["gap_warmup"], 0)

        # A second matched confirmation within 60 minutes is not selected.
        events, exclusions = collect_entry_events(
            [_state(int(ts)) for ts in timestamps], _rule(1), start, start + timedelta(hours=2),
        )
        self.assertTrue(events)
        self.assertTrue(all(current - previous >= 60 * NS_MINUTE for previous, current in zip(events, events[1:])))
        self.assertGreater(exclusions["spacing"], 0)

    def test_quote_tolerance_and_horizon_boundary_are_excluded(self):
        from evolution.signal_diagnostic import _QuoteIndex, _measure_event

        start = datetime(2026, 8, 29, tzinfo=UTC)
        end = start + timedelta(hours=2)
        start_ns = int(start.timestamp() * 1_000_000_000)
        # Entry target is on time; exit is two seconds late and breaches <=1s tolerance.
        quotes = _QuoteIndex([
            QuoteRow(start_ns + 60 * NS_MINUTE + NS_SECOND, "BTCUSDT.BINANCE", 99, 101, 100, 2, 200),
            QuoteRow(start_ns + 75 * NS_MINUTE + 3 * NS_SECOND, "BTCUSDT.BINANCE", 100, 101, 100.5, 1, 100),
        ], "BTCUSDT.BINANCE", start, end)
        _, reason = _measure_event(quotes, start_ns + 60 * NS_MINUTE, 15, int(end.timestamp() * 1_000_000_000))
        self.assertEqual(reason, "exit_quote_tolerance")
        _, reason = _measure_event(quotes, start_ns + 60 * NS_MINUTE, 60, int(end.timestamp() * 1_000_000_000))
        self.assertEqual(reason, "horizon_out_of_window")

    def test_quote_gap_between_entry_and_exit_is_excluded(self):
        from evolution.signal_diagnostic import _QuoteIndex, _measure_event

        start = datetime(2026, 8, 29, tzinfo=UTC)
        end = start + timedelta(hours=2)
        start_ns = int(start.timestamp() * 1_000_000_000)
        quotes = _QuoteIndex([
            QuoteRow(start_ns + 60 * NS_MINUTE + NS_SECOND, "BTCUSDT.BINANCE", 99, 101, 100, 2, 200),
            QuoteRow(start_ns + 75 * NS_MINUTE + NS_SECOND, "BTCUSDT.BINANCE", 100, 101, 100.5, 1, 100),
        ], "BTCUSDT.BINANCE", start, end)
        _, reason = _measure_event(quotes, start_ns + 60 * NS_MINUTE, 15, int(end.timestamp() * 1_000_000_000))
        self.assertEqual(reason, "quote_gap")

    def test_public_diagnostic_orchestration_measures_matching_state_and_quotes(self):
        from evolution.dataset import DatasetManifest
        from evolution.signal_diagnostic import build_supplemental_signal_diagnostic
        from evolution.supplemental import supplemental_split_name

        start = datetime(2026, 8, 29, tzinfo=UTC)
        end = start + timedelta(days=1)
        split = supplemental_split_name(start, end)
        start_ns = int(start.timestamp() * 1_000_000_000)
        event_ns = start_ns + 62 * NS_MINUTE
        exit_ns = event_ns + 60 * NS_MINUTE + NS_SECOND
        quotes = [
            QuoteRow(ts, "BTCUSDT.BINANCE", 100.0, 101.0, 100.5, 1.0, 100.0)
            for ts in range(event_ns + NS_SECOND, exit_ns + NS_SECOND, NS_SECOND)
        ]
        quotes[-1] = QuoteRow(exit_ns, "BTCUSDT.BINANCE", 102.0, 103.0, 102.5, 1.0, 100.0)
        manifest = DatasetManifest(
            schema_version=2,
            instrument_id="BTCUSDT.BINANCE",
            split=split,
            source_start="2026-08-29T00:00:00Z",
            source_end="2026-08-30T00:00:00Z",
            row_count=100,
            missing_bucket_count=1340,
            first_ts_event=start_ns + NS_MINUTE,
            last_ts_event=start_ns + 100 * NS_MINUTE,
            files={},
            execution_profile="executable",
            quote_interval_seconds=1,
            execution_delay_seconds=1,
            quote_count=len(quotes),
        )
        states = [_state(start_ns + index * NS_MINUTE) for index in range(1, 101)]

        with patch("evolution.signal_diagnostic.verify_manifest", return_value=manifest):
            report = build_supplemental_signal_diagnostic(
                "BTCUSDT.BINANCE", "trend-flow-confirmation-v1", split,
                start, end, Path("unused"),
                split_loader=lambda _root, _instrument: (states, quotes, []),
                now=datetime(2026, 9, 5, tzinfo=UTC),
            )

        self.assertEqual(report["sampled_event_count"], 1)
        event = report["events"][0]
        self.assertNotIn("excluded_reason", event["horizons"]["15"])
        self.assertEqual(event["horizons"]["60"]["entry_quote_ts"], event_ns + NS_SECOND)
        self.assertEqual(event["horizons"]["60"]["exit_quote_ts"], exit_ns)
        self.assertGreater(event["horizons"]["60"]["net_bps"], 0)

    def test_diagnostic_validates_manifest_before_loader(self):
        from evolution.signal_diagnostic import build_supplemental_signal_diagnostic
        from evolution.supplemental import supplemental_split_name

        start = datetime(2026, 8, 29, tzinfo=UTC)
        end = start + timedelta(days=1)
        split = supplemental_split_name(start, end)
        loader = unittest.mock.Mock(side_effect=AssertionError("loader called"))
        with tempfile.TemporaryDirectory() as directory, patch(
            "evolution.signal_diagnostic.verify_manifest", side_effect=ValueError("manifest rejected"),
        ):
            with self.assertRaisesRegex(ValueError, "manifest rejected"):
                build_supplemental_signal_diagnostic(
                    "BTCUSDT.BINANCE", "trend-flow-confirmation-v1", split,
                    start, end, Path(directory), split_loader=loader,
                    now=datetime(2026, 9, 5, tzinfo=UTC),
                )
        loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
