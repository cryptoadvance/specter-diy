import ast
import sys
from pathlib import Path

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs
    setup_native_stubs()

from unittest import TestCase

import seedqr

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"

# SeedSigner docs/seed_qr/README.md worked example.
DOC_MNEMONIC = "vacuum bridge buddy supreme exclude milk consider tail expand wasp pattern nuclear"
DOC_STANDARD_PAYLOAD = "192402220235174306311124037817700641198012901210"

# Fixed valid 24-word mnemonic (BIP-39 test vector, all-zero entropy).
MNEMONIC_24 = (
    "abandon abandon abandon abandon abandon abandon abandon abandon "
    "abandon abandon abandon abandon abandon abandon abandon abandon "
    "abandon abandon abandon abandon abandon abandon abandon art"
)


def _fake_matrix(size, fill=seedqr.MODULE_BLACK):
    """A deterministic size x size matrix for pure geometry tests."""
    return tuple(bytes([fill]) * size for _ in range(size))


def _identifiable_matrix(size):
    """
    A size x size matrix where module (x, y) encodes its own coordinates
    (as parity bits), so section extraction/recombination can be checked
    against exact expected values rather than a uniform fill.
    """
    return tuple(bytes(((x + y) % 2) for x in range(size)) for y in range(size))


class EncodingTest(TestCase):
    def test_standard_payload_matches_seedsigner_doc_example(self):
        self.assertEqual(seedqr.standard_payload(DOC_MNEMONIC), DOC_STANDARD_PAYLOAD)

    def test_standard_12_word_matrix_is_25x25(self):
        matrix = seedqr.generate_matrix(DOC_STANDARD_PAYLOAD)
        self.assertEqual(len(matrix), 25)
        self.assertTrue(all(len(row) == 25 for row in matrix))

    def test_compact_12_word_matrix_is_21x21(self):
        payload = seedqr.compact_payload(DOC_MNEMONIC)
        self.assertIsInstance(payload, bytes)
        matrix = seedqr.generate_matrix(payload)
        self.assertEqual(len(matrix), 21)

    def test_standard_24_word_matrix_is_29x29(self):
        payload = seedqr.standard_payload(MNEMONIC_24)
        matrix = seedqr.generate_matrix(payload)
        self.assertEqual(len(matrix), 29)

    def test_compact_24_word_matrix_is_25x25(self):
        payload = seedqr.compact_payload(MNEMONIC_24)
        matrix = seedqr.generate_matrix(payload)
        self.assertEqual(len(matrix), 25)

    def test_compact_payload_is_raw_bytes_not_hex(self):
        payload = seedqr.compact_payload(DOC_MNEMONIC)
        self.assertIsInstance(payload, bytes)
        # A hex string would be twice as long and be str, not bytes.
        self.assertNotIsInstance(payload, str)
        self.assertEqual(len(payload), 16)  # 12 words -> 128 bits entropy

    def test_compact_qr_encoder_receives_bytes_object(self):
        """
        The matrix generator must hand the encoder the exact bytes object,
        never a hex-encoded string representation of it.
        """
        import qrcode as qrcode_stub

        seen = {}
        original = qrcode_stub.encode_to_string

        def spy(payload):
            seen["payload"] = payload
            return original(payload)

        qrcode_stub.encode_to_string = spy
        try:
            entropy = seedqr.compact_payload(DOC_MNEMONIC)
            seedqr.generate_matrix(entropy)
        finally:
            qrcode_stub.encode_to_string = original

        self.assertIs(seen["payload"], entropy)
        self.assertIsInstance(seen["payload"], bytes)


class ValidateMatrixTest(TestCase):
    def test_rejects_empty_matrix(self):
        with self.assertRaises(seedqr.MatrixError):
            seedqr.validate_matrix(())

    def test_rejects_non_square_matrix(self):
        with self.assertRaises(seedqr.MatrixError):
            seedqr.validate_matrix((bytes([0, 0]), bytes([0])))

    def test_rejects_invalid_qr_module_count(self):
        with self.assertRaises(seedqr.MatrixError):
            seedqr.validate_matrix(_fake_matrix(22))

    def test_accepts_valid_sizes(self):
        for size in (21, 25, 29):
            self.assertEqual(seedqr.validate_matrix(_fake_matrix(size)), size)


class SectionGeometryTest(TestCase):
    def test_21x21_is_3x3_sections_of_7x7(self):
        self.assertEqual(seedqr.modules_per_section(21), 7)
        self.assertEqual(seedqr.num_sections(21), 3)

    def test_25x25_is_5x5_sections_of_5x5(self):
        self.assertEqual(seedqr.modules_per_section(25), 5)
        self.assertEqual(seedqr.num_sections(25), 5)

    def test_29x29_is_6x6_sections_with_partial_final_row_and_col(self):
        self.assertEqual(seedqr.modules_per_section(29), 5)
        self.assertEqual(seedqr.num_sections(29), 6)
        # Last row/col section only has 29 - 5*5 = 4 real modules.
        x0, y0, w, h = seedqr.section_bounds(29, 5, 5)
        self.assertEqual((w, h), (4, 4))
        # A non-final section is fully real.
        x0, y0, w, h = seedqr.section_bounds(29, 0, 0)
        self.assertEqual((w, h), (5, 5))

    def test_section_labels(self):
        self.assertEqual(seedqr.section_label(0, 0), "A-1")
        self.assertEqual(seedqr.section_label(1, 2), "B-3")
        self.assertEqual(seedqr.section_label(5, 5), "F-6")

    def test_every_real_module_is_in_exactly_one_section(self):
        for size in (21, 25, 29):
            n = seedqr.num_sections(size)
            mps = seedqr.modules_per_section(size)
            covered = [[0] * size for _ in range(size)]
            for row in range(n):
                for col in range(n):
                    x0, y0, w, h = seedqr.section_bounds(size, row, col)
                    for dy in range(h):
                        for dx in range(w):
                            covered[y0 + dy][x0 + dx] += 1
            for y in range(size):
                for x in range(size):
                    self.assertEqual(
                        covered[y][x], 1,
                        "module (%d, %d) in a %dx%d matrix covered %d times" % (
                            x, y, size, size, covered[y][x],
                        ),
                    )

    def test_recombining_sections_reproduces_original_matrix_exactly(self):
        for size in (21, 25, 29):
            matrix = _identifiable_matrix(size)
            n = seedqr.num_sections(size)
            mps = seedqr.modules_per_section(size)
            rebuilt = [[None] * size for _ in range(size)]
            for row in range(n):
                for col in range(n):
                    section = seedqr.extract_section(matrix, row, col)
                    x0, y0, w, h = seedqr.section_bounds(size, row, col)
                    for dy in range(mps):
                        for dx in range(mps):
                            value = section[dy][dx]
                            in_bounds = dx < w and dy < h
                            if in_bounds:
                                self.assertNotEqual(value, seedqr.MODULE_OUTSIDE)
                                rebuilt[y0 + dy][x0 + dx] = value
                            else:
                                self.assertEqual(value, seedqr.MODULE_OUTSIDE)
            for y in range(size):
                for x in range(size):
                    self.assertEqual(rebuilt[y][x], matrix[y][x])

    def test_partial_section_distinguishes_outside_from_white(self):
        # 29x29 all-white matrix: real modules in the partial corner section
        # must read as MODULE_WHITE, padding cells as MODULE_OUTSIDE.
        matrix = _fake_matrix(29, fill=seedqr.MODULE_WHITE)
        section = seedqr.extract_section(matrix, 5, 5)
        for dy in range(5):
            for dx in range(5):
                if dx < 4 and dy < 4:
                    self.assertEqual(section[dy][dx], seedqr.MODULE_WHITE)
                else:
                    self.assertEqual(section[dy][dx], seedqr.MODULE_OUTSIDE)

    def test_out_of_range_section_raises(self):
        with self.assertRaises(ValueError):
            seedqr.section_bounds(21, 3, 0)
        with self.assertRaises(ValueError):
            seedqr.extract_section(_fake_matrix(21), 0, 3)

    def test_extract_real_section_has_no_outside_padding(self):
        # 29x29: partial trailing row/col sections must come back sized to
        # their true (smaller) extent, never padded up to 5x5 with filler.
        matrix = _identifiable_matrix(29)
        full = seedqr.extract_real_section(matrix, 0, 0)
        self.assertEqual((len(full), len(full[0])), (5, 5))

        corner = seedqr.extract_real_section(matrix, 5, 5)  # F-6: 4x4 real
        self.assertEqual((len(corner), len(corner[0])), (4, 4))

        edge_row = seedqr.extract_real_section(matrix, 5, 0)  # F-1: 4 rows x 5 cols
        self.assertEqual((len(edge_row), len(edge_row[0])), (4, 5))

        edge_col = seedqr.extract_real_section(matrix, 0, 5)  # A-6: 5 rows x 4 cols
        self.assertEqual((len(edge_col), len(edge_col[0])), (5, 4))

        for section in (full, corner, edge_row, edge_col):
            for row in section:
                self.assertNotIn(seedqr.MODULE_OUTSIDE, row)

    def test_extract_real_section_matches_true_matrix_values(self):
        for size in (21, 25, 29):
            matrix = _identifiable_matrix(size)
            n = seedqr.num_sections(size)
            for row in range(n):
                for col in range(n):
                    x0, y0, w, h = seedqr.section_bounds(size, row, col)
                    section = seedqr.extract_real_section(matrix, row, col)
                    for dy in range(h):
                        for dx in range(w):
                            self.assertEqual(section[dy][dx], matrix[y0 + dy][x0 + dx])


class TouchMappingTest(TestCase):
    def test_top_left_tap_maps_to_a1(self):
        section = seedqr.coord_to_section(0, 0, 21, module_px=10)
        self.assertEqual(section, (0, 0))
        self.assertEqual(seedqr.section_label(*section), "A-1")

    def test_bottom_right_valid_module_maps_to_final_section(self):
        size = 29
        module_px = 10
        last_px = size * module_px - 1  # inside the very last module
        section = seedqr.coord_to_section(last_px, last_px, size, module_px)
        self.assertEqual(section, (5, 5))
        self.assertEqual(seedqr.section_label(*section), "F-6")

    def test_taps_outside_matrix_bounds_are_ignored(self):
        size, module_px = 21, 10
        matrix_px = size * module_px
        self.assertIsNone(seedqr.coord_to_module(-1, 0, size, module_px))
        self.assertIsNone(seedqr.coord_to_module(0, -1, size, module_px))
        self.assertIsNone(seedqr.coord_to_module(matrix_px, 0, size, module_px))
        self.assertIsNone(seedqr.coord_to_module(0, matrix_px, size, module_px))

    def test_taps_in_quiet_zone_are_ignored_by_caller_contract(self):
        # coord_to_module takes coordinates with the quiet zone already
        # excluded; anything the caller maps to a negative offset (i.e. a
        # tap that landed in the quiet zone) must be rejected the same way
        # as any other out-of-bounds tap.
        size, module_px = 21, 10
        self.assertIsNone(seedqr.coord_to_module(-5, -5, size, module_px))

    def test_taps_exactly_on_section_boundary_are_handled_consistently(self):
        size, module_px = 25, 10
        mps = seedqr.modules_per_section(size)
        boundary_px = mps * module_px  # first pixel of the *next* section
        # last pixel column of the first section
        self.assertEqual(
            seedqr.coord_to_section(boundary_px - 1, 0, size, module_px),
            (0, 0),
        )
        # first pixel column of the second section
        self.assertEqual(
            seedqr.coord_to_section(boundary_px, 0, size, module_px),
            (0, 1),
        )

    def test_screen_offset_is_the_callers_responsibility_and_composes_linearly(self):
        # Simulates a screen translating a raw touch point into
        # matrix-relative coordinates before calling coord_to_section.
        size, module_px = 21, 10
        origin_x, origin_y = 37, 84  # matrix top-left on screen
        raw_x, raw_y = origin_x + 15, origin_y + 5  # inside module (1, 0)
        rel_x, rel_y = raw_x - origin_x, raw_y - origin_y
        self.assertEqual(seedqr.coord_to_module(rel_x, rel_y, size, module_px), (1, 0))


class NavigationTest(TestCase):
    def test_left_unavailable_in_column_1(self):
        nav = seedqr.ZoomNavigator(size=25, row=2, col=0)
        self.assertFalse(nav.can_move("left"))
        self.assertEqual(nav.move("left"), (2, 0))

    def test_up_unavailable_in_row_a(self):
        nav = seedqr.ZoomNavigator(size=25, row=0, col=2)
        self.assertFalse(nav.can_move("up"))
        self.assertEqual(nav.move("up"), (0, 2))

    def test_right_and_down_stop_at_correct_edge(self):
        size = 25
        n = seedqr.num_sections(size)
        nav = seedqr.ZoomNavigator(size=size, row=0, col=0)
        for _ in range(n + 2):
            nav.move("right")
        self.assertEqual(nav.col, n - 1)
        for _ in range(n + 2):
            nav.move("down")
        self.assertEqual(nav.row, n - 1)

    def test_navigation_into_partial_final_section_works(self):
        size = 29
        n = seedqr.num_sections(size)
        nav = seedqr.ZoomNavigator(size=size, row=0, col=0)
        for _ in range(n - 1):
            self.assertTrue(nav.can_move("right"))
            nav.move("right")
        for _ in range(n - 1):
            self.assertTrue(nav.can_move("down"))
            nav.move("down")
        self.assertEqual(nav.section, (n - 1, n - 1))
        self.assertEqual(nav.label, "F-6")
        x0, y0, w, h = seedqr.section_bounds(size, *nav.section)
        self.assertEqual((w, h), (4, 4))

    def test_returning_to_overview_preserves_current_section(self):
        nav = seedqr.ZoomNavigator(size=25, row=0, col=0)
        nav.move("right")
        nav.move("down")
        selected = nav.section
        # Simulate closing the zoom view and reopening it at the section it
        # was last on -- the overview screen just needs to remember the
        # tuple and hand it back as the initial position.
        reopened = seedqr.ZoomNavigator(size=25, row=selected[0], col=selected[1])
        self.assertEqual(reopened.section, selected)

    def test_unknown_direction_raises(self):
        with self.assertRaises(ValueError):
            seedqr.neighbor_section(0, 0, 25, "sideways")


class NoUnconditionalPrintTest(TestCase):
    """
    Regression tests ensuring secret QR content (mnemonic, SeedQR digits,
    Compact SeedQR bytes, the QR matrix) can't reach stdout/logs.
    """

    def _assert_no_unconditional_print(self, path, qualnames):
        """
        For each dotted qualname (e.g. "QRCode._set_text"), assert the
        function body contains no `print(...)` call at its own top level
        (i.e. every print call, if any, is nested inside a conditional).
        """
        tree = ast.parse(path.read_text(), filename=str(path))
        found = {}

        class ClassVisitor(ast.NodeVisitor):
            def visit_ClassDef(self, node):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        found["%s.%s" % (node.name, item.name)] = item
                self.generic_visit(node)

        ClassVisitor().visit(tree)

        for qualname in qualnames:
            self.assertIn(qualname, found, "%s not found in %s" % (qualname, path))
            func = found[qualname]
            for stmt in func.body:
                is_print_expr = (
                    isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Call)
                    and isinstance(stmt.value.func, ast.Name)
                    and stmt.value.func.id == "print"
                )
                self.assertFalse(
                    is_print_expr,
                    "%s in %s contains an unconditional print() call" % (qualname, path),
                )

    def test_qrcode_component_has_no_unconditional_print(self):
        path = SRC_DIR / "gui" / "components" / "qrcode.py"
        self._assert_no_unconditional_print(path, ["QRCode._set_text", "QRCode.set_text"])

    def test_seedqr_pure_functions_never_print(self):
        import builtins

        calls = []
        original_print = builtins.print
        builtins.print = lambda *a, **kw: calls.append((a, kw))
        try:
            matrix = seedqr.generate_matrix(DOC_STANDARD_PAYLOAD)
            for size in (21, 25, 29):
                m = _identifiable_matrix(size)
                n = seedqr.num_sections(size)
                for row in range(n):
                    for col in range(n):
                        seedqr.extract_section(m, row, col)
            nav = seedqr.ZoomNavigator(size=29, row=0, col=0)
            for direction in ("right", "down", "left", "up"):
                nav.move(direction)
            seedqr.compact_payload(DOC_MNEMONIC)
        finally:
            builtins.print = original_print
        self.assertEqual(calls, [])

    def test_ram_keystore_does_not_display_raw_seedqr_payload_as_text(self):
        """
        Standard/Compact SeedQR selections must route to the dedicated
        transcription viewer, not to QRAlert(message=<raw payload>), which
        would render the digit string / hex underneath the QR code.
        """
        path = SRC_DIR / "keystore" / "ram.py"
        src = path.read_text()
        self.assertNotIn("hexlify(qr_msg)", src)
