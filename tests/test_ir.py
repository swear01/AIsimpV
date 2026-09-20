"""Type boundaries and concrete operator meanings, checked against the real solver."""
import tempfile
import unittest
from pathlib import Path

from rtl_relate.ir import Invalid, Unsupported, bv, emit, evaluate, expr_type, load_json, op, ref, literal
from rtl_relate.solver import query, run


class IRTests(unittest.TestCase):
    def test_operator_semantics_and_smt_encoding(self):
        true, false = {"bool": True}, {"bool": False}
        cases = [
            (bv(3, 2), 2, 3), (true, "bool", True), (ref("x"), 2, 3),
            (op("eq", bv(3, 2), bv(2, 2)), "bool", False),
            (op("ite", false, bv(1, 2), bv(2, 2)), 2, 2),
            (op("not", false), "bool", True), (op("and", true, false), "bool", False),
            (op("or", true, false), "bool", True), (op("xor", true, true), "bool", False),
            (op("bvnot", bv(1, 2)), 2, 2), (op("bvand", bv(1, 2), bv(2, 2)), 2, 0),
            (op("bvor", bv(1, 2), bv(2, 2)), 2, 3), (op("bvxor", bv(3, 2), bv(2, 2)), 2, 1),
            (op("add", bv(3, 2), bv(1, 2)), 2, 0), (op("sub", bv(0, 2), bv(1, 2)), 2, 3),
            (op("ult", bv(3, 2), bv(0, 2)), "bool", False), (op("ule", bv(3, 2), bv(3, 2)), "bool", True),
            (op("concat", bv(2, 2), bv(1, 1)), 3, 5),
            ({"op": "extract", "args": [bv(13, 4)], "high": 2, "low": 1}, 2, 2),
            ({"op": "zext", "args": [ref("x")], "width": 4}, 4, 3),
            ({"op": "sext", "args": [ref("x")], "width": 4}, 4, 15),
            ({"op": "sext", "args": [bv(1, 2)], "width": 4}, 4, 1),
        ]
        with tempfile.TemporaryDirectory() as directory:
            for index, (expr, typ, expected) in enumerate(cases):
                with self.subTest(expr=expr):
                    self.assertEqual(expr_type(expr, {"x": 2}), typ)
                    self.assertEqual(evaluate(expr, {"x": 3}, {"x": 2}), expected)
                    term = emit(expr, {"x": "(_ bv3 2)"}, {"x": 2})
                    row = run(query([], f"(not (= {term} {literal(expected, typ)}))", 5000), directory, f"op_{index}")
                    self.assertEqual(row["status"], "unsat", row)

    def test_each_operator_rejects_bad_types_or_widths(self):
        invalid = [
            op("eq", bv(0, 1), bv(0, 2)), op("ite", bv(1, 1), bv(0, 1), bv(1, 1)),
            *[op(name, bv(1, 1)) for name in ("not",)],
            *[op(name, bv(1, 1), bv(1, 1)) for name in ("and", "or", "xor")],
            op("bvnot", {"bool": True}),
            *[op(name, bv(1, 1), bv(1, 2)) for name in ("bvand", "bvor", "bvxor", "add", "sub", "ult", "ule")],
            op("concat", {"bool": True}, bv(1, 1)),
            {"op": "extract", "args": [bv(0, 2)], "high": 2, "low": 0},
            *[{"op": name, "args": [bv(0, 2)], "width": 1} for name in ("zext", "sext")],
            {"ref": "x", "assume": True}, {"bool": 1}, bv(4, 2), bv(-1, 2), bv(0, True),
        ]
        for expr in invalid:
            with self.subTest(expr=expr), self.assertRaises(Invalid):
                expr_type(expr, {"x": 2})
        with self.assertRaises(Unsupported):
            expr_type(op("eval", {"bool": True}), {})

    def test_json_duplicate_keys_and_nonfinite_constants_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            for text in ('{"J":true,"J":false}', '{"x":NaN}'):
                path.write_text(text)
                with self.assertRaises(Invalid):
                    load_json(path)


if __name__ == "__main__":
    unittest.main()
