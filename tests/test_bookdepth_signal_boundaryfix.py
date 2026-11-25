import unittest
from research.bookdepth_signal_diagnostic_boundaryfix import split_indices, contiguous_horizon

class SplitBoundaryTests(unittest.TestCase):
    def test_train_excludes_cross_boundary_exit(self):
        # Train [0, 5): for h=2, valid signals are 0,1,2 only.
        self.assertEqual(list(split_indices(0, 5, 12, 2)), [0, 1, 2])

    def test_validation_starts_at_its_own_boundary(self):
        # Validation [5, 9): h=2 signals 5,6; 7 would exit at index 9.
        self.assertEqual(list(split_indices(5, 9, 12, 2)), [5, 6])

    def test_oos_last_valid_signal_is_included(self):
        # OOS [8, 12): h=2 signals 8,9; both exits remain before index 12.
        self.assertEqual(list(split_indices(8, 12, 12, 2)), [8, 9])

    def test_one_minute_horizon_keeps_last_in_split_signal(self):
        self.assertEqual(list(split_indices(5, 9, 12, 1)), [5, 6, 7])

    def test_no_signal_when_split_shorter_than_horizon(self):
        self.assertEqual(list(split_indices(5, 6, 12, 2)), [])

    def test_reject_invalid_horizon(self):
        with self.assertRaises(ValueError):
            split_indices(0, 5, 12, 0)

    def test_contiguous_horizon_accepts_complete_minutes(self):
        rows = [{"t": i * 60000} for i in range(4)]
        self.assertTrue(contiguous_horizon(rows, 0, 3))

    def test_contiguous_horizon_rejects_internal_gap(self):
        rows = [{"t": 0}, {"t": 60000}, {"t": 180000}, {"t": 240000}]
        self.assertFalse(contiguous_horizon(rows, 0, 3))

if __name__ == "__main__":
    unittest.main()
