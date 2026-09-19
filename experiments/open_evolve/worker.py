"""Internal isolated interpreter worker; invoked with Python -I by runtime.py."""

import json
from pathlib import Path
import resource
import sys

# Only standard-library policy/contract modules are imported, never market data.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from experiments.open_evolve.contracts import MarketState, PositionState
from experiments.open_evolve.policy import Policy, PolicyLimits, InvalidPolicy


def main():
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
    def deny_io(event, args):
        if (event == "open" or event.startswith(("socket.", "subprocess.", "os.exec", "os.spawn"))
                or event in ("os.system", "os.fork", "ctypes.dlopen")):
            raise PermissionError("policy worker I/O is disabled")
    sys.addaudithook(deny_io)
    policy = None
    for line in iter(lambda: sys.stdin.buffer.readline(100_001), b""):
        if len(line) > 100_000:
            break
        try:
            message = json.loads(line)
            if policy is None:
                policy = Policy(message["source"], PolicyLimits(**message["limits"]))
                response = {"ready": True}
            else:
                target = policy(MarketState(**message["market"]), PositionState(**message["position"]),
                                allow_short=message["allow_short"])
                response = {"target": target.name}
        except (InvalidPolicy, ValueError, TypeError, KeyError, MemoryError) as exc:
            response = {"error": str(exc)[:1000]}
        sys.stdout.write(json.dumps(response, allow_nan=False) + "\n")
        sys.stdout.flush()
        if "error" in response:
            break


if __name__ == "__main__":
    main()
