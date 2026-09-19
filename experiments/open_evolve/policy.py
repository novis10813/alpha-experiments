"""Bounded interpreter for an allowlisted subset of Python policy functions.

Candidate source is parsed, never exec/eval'd or imported. Attribute access only
reads named scalar fields from copied input dictionaries. There are no Python
object references, user-defined calls, loops, containers, or persistent globals
in the interpreted language. This is a restricted Python search space, not a
sandbox for arbitrary Python. Extending the grammar requires a security review.
"""

import ast
from dataclasses import asdict, dataclass
from hashlib import sha256
import math
import operator

from experiments.open_evolve.contracts import MarketState, PositionState, TargetPosition, validate_target


class InvalidPolicy(ValueError):
    pass


@dataclass(frozen=True)
class PolicyLimits:
    max_source_bytes: int
    max_ast_nodes: int
    max_steps: int

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in vars(self).values()):
            raise ValueError("policy limits must be positive integers")


_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.Mod: operator.mod}
_COMPARE = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
            ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
            ast.Is: operator.is_, ast.IsNot: operator.is_not}
_FUNCTIONS = {"abs": abs, "min": min, "max": max}
_ALLOWED = (
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.If,
    ast.Assign, ast.Name, ast.Load, ast.Store, ast.Constant, ast.Attribute,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.Call, ast.IfExp,
    ast.And, ast.Or, ast.Not, ast.UAdd, ast.USub,
    *_BINARY, *_COMPARE,
)
_RESERVED = {"market", "position", "TargetPosition", *_FUNCTIONS}


class Policy:
    def __init__(self, source: str, limits: PolicyLimits):
        self.limits = limits
        if len(source.encode()) > limits.max_source_bytes:
            raise InvalidPolicy("source size limit exceeded")
        try:
            tree = ast.parse(source)
        except (SyntaxError, RecursionError) as exc:
            raise InvalidPolicy("invalid Python source") from exc
        nodes = list(ast.walk(tree))
        if len(nodes) > limits.max_ast_nodes:
            raise InvalidPolicy("AST node limit exceeded")
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
            raise InvalidPolicy("source must contain only def policy(market, position)")
        fn = tree.body[0]
        args = fn.args
        if (fn.name != "policy" or fn.decorator_list or fn.returns or fn.type_params
                or [a.arg for a in args.args] != ["market", "position"]
                or args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg
                or args.defaults or args.kw_defaults or any(a.annotation for a in args.args)):
            raise InvalidPolicy("expected unannotated def policy(market, position)")
        for node in nodes:
            if isinstance(node, ast.FunctionDef) and node is not fn:
                raise InvalidPolicy("nested functions are forbidden")
            if not isinstance(node, _ALLOWED):
                raise InvalidPolicy(f"unsupported syntax: {type(node).__name__}")
            if isinstance(node, ast.Constant):
                if type(node.value) not in (int, float, bool, type(None)):
                    raise InvalidPolicy("only numeric, boolean and None constants are allowed")
                self._finite(node.value)
            if isinstance(node, ast.Name) and node.id.startswith("_"):
                raise InvalidPolicy("private names are forbidden")
            if isinstance(node, ast.Attribute):
                if not isinstance(node.value, ast.Name):
                    raise InvalidPolicy("nested attribute access is forbidden")
                fields = {"market": MarketState.__dataclass_fields__,
                          "position": PositionState.__dataclass_fields__,
                          "TargetPosition": TargetPosition.__members__}
                if node.value.id not in fields or node.attr not in fields[node.value.id]:
                    raise InvalidPolicy("attribute not in policy schema")
            if isinstance(node, ast.Assign):
                if (len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name)
                        or node.targets[0].id in _RESERVED):
                    raise InvalidPolicy("assignment must target a local scalar")
            if isinstance(node, ast.Call):
                if (not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS
                        or node.keywords or not 1 <= len(node.args) <= 4):
                    raise InvalidPolicy("only bounded abs/min/max calls are allowed")
        self.source = source
        self.source_hash = sha256(source.encode()).hexdigest()
        self.complexity = len(nodes) + sum(isinstance(n, ast.If) for n in nodes)
        self._body = fn.body

    @staticmethod
    def _finite(value):
        if type(value) is int and value.bit_length() > 128:
            raise InvalidPolicy("integer magnitude limit exceeded")
        if type(value) is float and not math.isfinite(value):
            raise InvalidPolicy("nonfinite arithmetic")
        return value

    def __call__(self, market: MarketState, position: PositionState, *, allow_short: bool):
        inputs = {"market": asdict(market), "position": asdict(position),
                  "TargetPosition": dict(TargetPosition.__members__)}
        locals_ = {}
        remaining = self.limits.max_steps

        def step():
            nonlocal remaining
            remaining -= 1
            if remaining < 0:
                raise InvalidPolicy("instruction budget exceeded")

        def expression(node):
            step()
            if isinstance(node, ast.Constant):
                return node.value
            if isinstance(node, ast.Name):
                if node.id not in locals_:
                    raise InvalidPolicy(f"undefined local: {node.id}")
                return locals_[node.id]
            if isinstance(node, ast.Attribute):
                return inputs[node.value.id][node.attr]
            if isinstance(node, ast.BinOp):
                return self._finite(_BINARY[type(node.op)](expression(node.left), expression(node.right)))
            if isinstance(node, ast.UnaryOp):
                op = {ast.Not: operator.not_, ast.UAdd: operator.pos, ast.USub: operator.neg}
                return self._finite(op[type(node.op)](expression(node.operand)))
            if isinstance(node, ast.BoolOp):
                value = expression(node.values[0])
                for item in node.values[1:]:
                    if (isinstance(node.op, ast.And) and not value
                            or isinstance(node.op, ast.Or) and value):
                        return value
                    value = expression(item)
                return value
            if isinstance(node, ast.Compare):
                left = expression(node.left)
                for op, right_node in zip(node.ops, node.comparators):
                    right = expression(right_node)
                    if not _COMPARE[type(op)](left, right):
                        return False
                    left = right
                return True
            if isinstance(node, ast.IfExp):
                return expression(node.body if expression(node.test) else node.orelse)
            if isinstance(node, ast.Call):
                return self._finite(_FUNCTIONS[node.func.id](*(expression(a) for a in node.args)))
            raise InvalidPolicy("unsupported expression")

        def block(statements):
            for node in statements:
                step()
                if isinstance(node, ast.Return):
                    return True, expression(node.value) if node.value is not None else None
                if isinstance(node, ast.Assign):
                    locals_[node.targets[0].id] = expression(node.value)
                elif isinstance(node, ast.If):
                    found, value = block(node.body if expression(node.test) else node.orelse)
                    if found:
                        return True, value
                elif not isinstance(node, ast.Assign):
                    raise InvalidPolicy("unsupported statement")
            return False, None

        try:
            _, result = block(self._body)
            return validate_target(result, allow_short=allow_short)
        except InvalidPolicy:
            raise
        except (ValueError, TypeError, ArithmeticError, RecursionError) as exc:
            raise InvalidPolicy(f"policy evaluation failed: {type(exc).__name__}") from exc
