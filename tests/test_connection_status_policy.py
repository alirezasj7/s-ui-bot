"""State transitions, fresh latency windows and multi-endpoint coverage."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.services.connection_status_policy import aggregate_host, apply_observation, is_fresh
from app.services.connection_status_types import (
    ConnectionStatus as Status,
    EndpointHealth,
    EndpointIdentity,
    ObservationKind as Kind,
    ProbeObservation,
)


class HealthPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 15, tzinfo=timezone.utc)
        self.identity = EndpointIdentity("endpoint-one", "generation-one")

    def observe(self, kind: Kind, previous: EndpointHealth | None = None, *, delay: int = 100,
                destination: str = "gstatic", seconds: int = 0, identity: EndpointIdentity | None = None) -> EndpointHealth:
        observation = ProbeObservation(kind, self.now + timedelta(seconds=seconds),
                                       destination if kind == Kind.SUCCESS else None, delay if kind == Kind.SUCCESS else None)
        return apply_observation(identity or self.identity, observation, previous=previous)

    def test_new_endpoint_starts_unknown_and_first_success_is_healthy(self) -> None:
        self.assertEqual(EndpointHealth(self.identity).status, Status.UNKNOWN)
        self.assertEqual(self.observe(Kind.SUCCESS).status, Status.HEALTHY)

    def test_three_failures_then_two_successes_drive_outage_and_recovery(self) -> None:
        state = self.observe(Kind.SUCCESS)
        for index, expected in enumerate((Status.DEGRADED, Status.DEGRADED, Status.DOWN), 1):
            state = self.observe(Kind.FAILURE, state, seconds=index)
            self.assertEqual(state.status, expected)
            self.assertEqual(state.failure_streak, index)
            self.assertIsNone(state.delay_ms)
        state = self.observe(Kind.SUCCESS, state, seconds=4)
        self.assertEqual(state.status, Status.DEGRADED)
        state = self.observe(Kind.SUCCESS, state, seconds=5)
        self.assertEqual(state.status, Status.HEALTHY)
        self.assertEqual(state.failure_streak, 0)

    def test_unknown_breaks_failure_streak_and_requires_fresh_recovery(self) -> None:
        state = self.observe(Kind.FAILURE)
        state = self.observe(Kind.FAILURE, state, seconds=1)
        state = self.observe(Kind.UNKNOWN, state, seconds=2)
        self.assertEqual((state.status, state.failure_streak, state.success_streak), (Status.UNKNOWN, 0, 0))
        self.assertIsNone(state.delay_ms)
        failed = self.observe(Kind.FAILURE, state, seconds=3)
        self.assertEqual((failed.status, failed.failure_streak), (Status.DEGRADED, 1))
        recovered = self.observe(Kind.SUCCESS, state, seconds=3)
        self.assertEqual(recovered.status, Status.DEGRADED)
        self.assertEqual(self.observe(Kind.SUCCESS, recovered, seconds=4).status, Status.HEALTHY)

    def test_stale_and_future_previous_samples_break_streaks(self) -> None:
        initial = self.observe(Kind.SUCCESS)
        for seconds in (180, 181, -1):
            with self.subTest(seconds=seconds):
                result = self.observe(Kind.SUCCESS, initial, seconds=seconds)
                self.assertEqual(result.status, Status.DEGRADED)
                self.assertEqual(result.success_streak, 1)
                self.assertEqual(len(result.samples), 1)

    def test_2000_is_healthy_but_a_larger_median_is_degraded(self) -> None:
        self.assertEqual(self.observe(Kind.SUCCESS, delay=2000).status, Status.HEALTHY)
        slow = self.observe(Kind.SUCCESS, delay=2001)
        self.assertEqual(slow.status, Status.DEGRADED)
        again = self.observe(Kind.SUCCESS, slow, delay=2000, seconds=1)
        self.assertEqual(again.status, Status.DEGRADED)
        self.assertEqual(again.delay_ms, 2001)

    def test_median_contains_only_five_fresh_successes_in_the_same_series(self) -> None:
        state = None
        for index, delay in enumerate((10, 20, 30, 40, 100, 500)):
            state = self.observe(Kind.SUCCESS, state, delay=delay, seconds=index)
        self.assertEqual(len(state.samples), 5)
        self.assertEqual(state.delay_ms, 40)
        changed = self.observe(Kind.SUCCESS, state, destination="cloudflare", delay=900, seconds=6)
        self.assertEqual(len(changed.samples), 1)
        self.assertEqual(changed.delay_ms, 900)
        changed = self.observe(Kind.SUCCESS, changed, delay=50, seconds=179)
        self.assertEqual(len(changed.samples), 1)

    def test_account_or_endpoint_generation_change_starts_a_new_series(self) -> None:
        state = self.observe(Kind.FAILURE)
        for identity in (EndpointIdentity("other", "generation-one"), EndpointIdentity("endpoint-one", "new")):
            with self.subTest(identity=identity):
                changed = self.observe(Kind.SUCCESS, state, identity=identity, delay=10, seconds=1)
                self.assertEqual(changed.status, Status.HEALTHY)
                self.assertEqual(changed.failure_streak, 0)

    def test_freshness_expires_at_exact_boundary_and_rejects_naive_time(self) -> None:
        self.assertTrue(is_fresh(self.now, now=self.now + timedelta(seconds=179)))
        self.assertFalse(is_fresh(self.now, now=self.now + timedelta(seconds=180)))
        self.assertFalse(is_fresh(self.now + timedelta(seconds=1), now=self.now))
        self.assertFalse(is_fresh(None, now=self.now))
        with self.assertRaises(ValueError):
            is_fresh(self.now.replace(tzinfo=None), now=self.now)

    def test_partial_stale_and_old_generation_coverage_never_becomes_healthy(self) -> None:
        one = self.observe(Kind.SUCCESS)
        other = EndpointIdentity("endpoint-two", "generation-one")
        two = self.observe(Kind.SUCCESS, identity=other)
        expected = (self.identity, other)
        for states, now in (((one,), self.now), ((one, two), self.now + timedelta(seconds=180)),
                            ((one, self.observe(Kind.SUCCESS, identity=EndpointIdentity("endpoint-two", "old"))), self.now)):
            with self.subTest(states=states):
                self.assertEqual(aggregate_host(states, expected=expected, now=now).status, Status.UNKNOWN)

    def test_aggregation_requires_all_healthy_or_all_verified_down(self) -> None:
        other = EndpointIdentity("two", "generation-one")
        healthy = self.observe(Kind.SUCCESS)
        second = self.observe(Kind.SUCCESS, identity=other)
        expected = (self.identity, other)
        self.assertEqual(aggregate_host((healthy, second), expected=expected, now=self.now).status, Status.HEALTHY)
        down = None
        for second_number in range(3):
            down = self.observe(Kind.FAILURE, down, identity=other, seconds=second_number)
        self.assertEqual(aggregate_host((healthy, down), expected=expected, now=self.now + timedelta(seconds=3)).status, Status.DEGRADED)
        first_down = None
        for second_number in range(3):
            first_down = self.observe(Kind.FAILURE, first_down, seconds=second_number)
        result = aggregate_host((first_down, down), expected=expected, now=self.now + timedelta(seconds=3))
        self.assertEqual(result.status, Status.DOWN)
        self.assertIsNone(result.delay_ms)
        self.assertEqual(result.covered, 2)
        self.assertEqual(aggregate_host((healthy, second), expected=expected, now=self.now, enabled=False).status, Status.PAUSED)

    def test_failed_sample_cannot_contain_a_fabricated_delay(self) -> None:
        for delay in (True, -1, 5001, 1.5):
            with self.subTest(delay=delay), self.assertRaises(ValueError):
                ProbeObservation(Kind.SUCCESS, self.now, "gstatic", delay)
        with self.assertRaises(ValueError):
            ProbeObservation(Kind.FAILURE, self.now, delay_ms=1)
