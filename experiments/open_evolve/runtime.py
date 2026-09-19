"""Dedicated, resource-limited process for the restricted policy interpreter.

No arbitrary candidate Python is executed. The worker receives source once and
value-only snapshots thereafter. OS limits contain parser/interpreter faults;
the AST interpreter is the capability boundary (not unrestricted Python sandboxing).
"""

from dataclasses import asdict
import json
import os
from pathlib import Path
import select
import selectors
from time import monotonic
import subprocess
import sys

from experiments.open_evolve.contracts import TargetPosition
from experiments.open_evolve.policy import InvalidPolicy


class PolicyProcess:
    def __init__(self, policy, *, timeout_seconds=2.0):
        self.timeout_seconds = timeout_seconds
        self.process = subprocess.Popen(
            [sys.executable, "-I", str(Path(__file__).with_name("worker.py"))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={"PATH": os.defpath}, cwd="/", start_new_session=True,
        )
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        try:
            self._request({"source": policy.source, "limits": asdict(policy.limits)})
        except BaseException:
            self.close()
            raise

    def _request(self, message):
        try:
            payload = (json.dumps(message, allow_nan=False) + "\n").encode()
            if len(payload) > 100_000:
                raise InvalidPolicy("policy request exceeded protocol limit")
            deadline = monotonic() + self.timeout_seconds
            fd = self.process.stdin.fileno()
            os.set_blocking(fd, False)
            while payload:
                if not select.select([], [fd], [], max(0, deadline - monotonic()))[1]:
                    raise InvalidPolicy("policy worker write timed out")
                count = os.write(fd, payload)
                payload = payload[count:]
            line = b""
            while not line.endswith(b"\n"):
                if not self.selector.select(max(0, deadline - monotonic())):
                    raise InvalidPolicy("policy worker timed out")
                chunk = os.read(self.process.stdout.fileno(), 4096)
                if not chunk or len(line) + len(chunk) > 100_000:
                    raise InvalidPolicy("policy worker terminated or exceeded response limit")
                line += chunk
            result = json.loads(line)
            if "error" in result:
                raise InvalidPolicy(result["error"])
            return result
        except (BrokenPipeError, OSError, ValueError) as exc:
            if isinstance(exc, InvalidPolicy):
                raise
            raise InvalidPolicy("policy worker protocol failure") from exc

    def __call__(self, market, position, *, allow_short):
        response = self._request({"market": asdict(market), "position": asdict(position), "allow_short": allow_short})
        return TargetPosition[response["target"]]

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()
        self.selector.close()
        try:
            self.process.stdin.close()
        except BrokenPipeError:
            pass
        self.process.stdout.close()
