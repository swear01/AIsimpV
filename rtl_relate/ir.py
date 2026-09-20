"""Typed, data-only expressions shared by manual models and the RTL adapter."""
import hashlib
import json


class Invalid(ValueError):
    pass


class Unsupported(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def bv(value, width):
    return {"bv": value, "width": width}


def ref(name):
    return {"ref": name}


def op(name, *args):
    return {"op": name, "args": list(args)}


def fields(obj, names, what):
    if not isinstance(obj, dict) or set(obj) != set(names):
        raise Invalid(f"{what}: expected fields {sorted(names)}")


def valid_type(typ):
    if typ == "bool" or type(typ) is int and 1 <= typ <= 4096:
        return typ
    raise Invalid(f"invalid type: {typ!r}")


def valid_hash(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise Invalid("expected SHA-256 hex digest")


def expr_type(expr, env, depth=0):
    if depth > 100:
        raise Invalid("expression nesting exceeds 100")
    if not isinstance(expr, dict):
        raise Invalid("expression must be an object")
    if "ref" in expr:
        fields(expr, {"ref"}, "reference")
        if not isinstance(expr["ref"], str) or expr["ref"] not in env:
            raise Invalid(f"unknown or disallowed reference: {expr['ref']!r}")
        return valid_type(env[expr["ref"]])
    if "bool" in expr:
        fields(expr, {"bool"}, "Boolean constant")
        if type(expr["bool"]) is not bool:
            raise Invalid("Boolean constant must be true or false")
        return "bool"
    if "bv" in expr:
        fields(expr, {"bv", "width"}, "bit-vector constant")
        width = valid_type(expr["width"])
        if type(width) is not int or type(expr["bv"]) is not int or not 0 <= expr["bv"] < 1 << width:
            raise Invalid("bit-vector constant out of range")
        return width
    name = expr.get("op")
    names = {"eq", "ite", "not", "and", "or", "xor", "bvnot", "bvand", "bvor", "bvxor",
             "add", "sub", "ult", "ule", "extract", "concat", "zext", "sext"}
    if not isinstance(name, str) or name not in names:
        raise Unsupported(f"unsupported operator: {name!r}")
    extras = {"high", "low"} if name == "extract" else {"width"} if name in {"zext", "sext"} else set()
    fields(expr, {"op", "args"} | extras, "operator")
    if not isinstance(expr["args"], list):
        raise Invalid("operator arguments must be a list")
    types = [expr_type(a, env, depth + 1) for a in expr["args"]]
    arity = 3 if name == "ite" else 1 if name in {"not", "bvnot", "extract", "zext", "sext"} else 2
    if len(types) != arity:
        raise Invalid(f"{name} expects {arity} arguments")
    if name == "ite":
        if types[0] != "bool" or types[1] != types[2]:
            raise Invalid("ite needs Bool condition and equal branch types")
        return types[1]
    if name == "eq":
        if types[0] != types[1]:
            raise Invalid("equality operand types differ")
        return "bool"
    if name in {"not", "and", "or", "xor"}:
        if any(t != "bool" for t in types):
            raise Invalid(f"{name} expects Bool")
        return "bool"
    if any(type(t) is not int for t in types):
        raise Invalid(f"{name} expects bit-vectors")
    if name == "concat":
        return valid_type(sum(types))
    if name == "extract":
        high, low = expr["high"], expr["low"]
        if type(high) is not int or type(low) is not int or not 0 <= low <= high < types[0]:
            raise Invalid("extract bounds out of range")
        return high - low + 1
    if name in {"zext", "sext"}:
        width = valid_type(expr["width"])
        if type(width) is not int or width < types[0]:
            raise Invalid("extension target narrower than operand")
        return width
    if len(types) == 2 and types[0] != types[1]:
        raise Invalid(f"{name} operand widths differ")
    return "bool" if name in {"ult", "ule"} else types[0]


def sort(typ):
    return "Bool" if typ == "bool" else f"(_ BitVec {typ})"


def literal(value, typ):
    if typ == "bool":
        return "true" if value else "false"
    return f"(_ bv{value} {typ})"


def emit(expr, bindings, types):
    if "ref" in expr:
        return bindings[expr["ref"]]
    if "bool" in expr:
        return literal(expr["bool"], "bool")
    if "bv" in expr:
        return literal(expr["bv"], expr["width"])
    name = expr["op"]
    args = [emit(a, bindings, types) for a in expr["args"]]
    if name == "extract":
        return f"((_ extract {expr['high']} {expr['low']}) {args[0]})"
    if name in {"zext", "sext"}:
        amount = expr["width"] - expr_type(expr["args"][0], types)
        return f"((_ {'zero_extend' if name == 'zext' else 'sign_extend'} {amount}) {args[0]})"
    smt = {"eq": "=", "add": "bvadd", "sub": "bvsub", "ult": "bvult", "ule": "bvule"}.get(name, name)
    return f"({smt} {' '.join(args)})"


def evaluate(expr, values, types):
    typ = expr_type(expr, types)
    if "ref" in expr:
        value = values[expr["ref"]]
        if typ == "bool":
            if type(value) is not bool:
                raise Invalid("Bool assignment is not bool")
        elif type(value) is not int or not 0 <= value < 1 << typ:
            raise Invalid("BV assignment out of range")
        return value
    if "bool" in expr:
        return expr["bool"]
    if "bv" in expr:
        return expr["bv"]
    name = expr["op"]
    args = [evaluate(a, values, types) for a in expr["args"]]
    a = args[0]
    b = args[1] if len(args) > 1 else None
    if name == "eq": return a == b
    if name == "ite": return b if a else args[2]
    if name == "not": return not a
    if name == "and": return a and b
    if name == "or": return a or b
    if name == "xor": return a != b
    if name == "ult": return a < b
    if name == "ule": return a <= b
    if name == "bvnot": result = ~a
    elif name == "bvand": result = a & b
    elif name == "bvor": result = a | b
    elif name == "bvxor": result = a ^ b
    elif name == "add": result = a + b
    elif name == "sub": result = a - b
    elif name == "concat": result = (a << expr_type(expr["args"][1], types)) | b
    elif name == "extract": result = a >> expr["low"]
    elif name == "zext": result = a
    elif name == "sext":
        width = expr_type(expr["args"][0], types)
        result = a - (1 << width) if a & (1 << (width - 1)) else a
    else: raise Unsupported(name)
    return result & ((1 << typ) - 1)


def validate_model(model):
    fields(model, {"version", "name", "source_sha256", "clock", "symbols", "init", "next", "observe"}, "model")
    if type(model["version"]) is not int or model["version"] != 1:
        raise Unsupported("model version")
    if not isinstance(model["name"], str) or not model["name"]:
        raise Invalid("model name required")
    valid_hash(model["source_sha256"])
    fields(model["clock"], {"name", "edge"}, "model clock")
    if model["clock"]["edge"] != "positive":
        raise Unsupported("model requires one positive-edge clock")
    if not isinstance(model["clock"]["name"], str) or not model["clock"]["name"]:
        raise Invalid("model clock name required")
    if not isinstance(model["symbols"], dict):
        raise Invalid("symbols must be a dictionary")
    types, states = {}, {}
    for key, symbol in model["symbols"].items():
        if not isinstance(key, str) or not key:
            raise Invalid("nonempty symbol ID required")
        fields(symbol, {"kind", "type", "signed", "origin"}, "symbol")
        if symbol["kind"] not in {"state", "input", "nondet"}:
            raise Invalid("unknown symbol kind")
        if type(symbol["signed"]) is not bool or not isinstance(symbol["origin"], str) or not symbol["origin"]:
            raise Invalid("signedness and origin required")
        types[key] = valid_type(symbol["type"])
        if symbol["kind"] == "state":
            states[key] = types[key]
    if expr_type(model["init"], states) != "bool":
        raise Invalid("initial predicate is not Bool")
    if not isinstance(model["next"], dict) or set(model["next"]) != set(states):
        raise Invalid("next must cover every state exactly")
    for key, expr in model["next"].items():
        if expr_type(expr, types) != states[key]:
            raise Invalid(f"next type mismatch: {key}")
    if not isinstance(model["observe"], dict) or not model["observe"]:
        raise Invalid("at least one observation required")
    for key, expr in model["observe"].items():
        if not isinstance(key, str) or not key:
            raise Invalid("invalid observation name")
        expr_type(expr, types)
    return types


def symbols_of(model, kind):
    return {key: s["type"] for key, s in model["symbols"].items() if s["kind"] == kind}


def load_json(path):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise Invalid(f"duplicate JSON key: {key}")
            obj[key] = value
        return obj
    with open(path, encoding="utf-8") as stream:
        return json.load(stream, object_pairs_hook=unique,
                         parse_constant=lambda x: (_ for _ in ()).throw(Invalid(f"invalid JSON constant {x}")))
