"""Behavioral tests for aligned circular-block index paths."""

import random
import unittest

from block_resampling import circular_block_indices, paired_resample


class CircularBlockIndicesTests(unittest.TestCase):
    def test_seeded_wrap_and_last_block_truncation(self):
        # Random(11) starts 3, 4, 3, 3, 4, 4 for these two paths.
        self.assertEqual(
            circular_block_indices(5, block_length=2, replicates=2, seed=11),
            ((3, 4, 4, 0, 3), (3, 4, 4, 0, 4)),
        )

    def test_reproducibility_and_global_rng_isolation(self):
        random.seed(90210)
        before = random.getstate()
        first = circular_block_indices(7, block_length=3, replicates=4, seed=19)
        self.assertEqual(first, circular_block_indices(7, block_length=3, replicates=4, seed=19))
        self.assertEqual(random.getstate(), before)
        self.assertIsInstance(first, tuple)
        self.assertTrue(all(isinstance(path, tuple) and len(path) == 7 for path in first))

    def test_singleton_and_full_length_block(self):
        self.assertEqual(circular_block_indices(1, block_length=1, replicates=2, seed=0), ((0,), (0,)))
        for path in circular_block_indices(4, block_length=4, replicates=3, seed=2):
            self.assertEqual(len(path), 4)
            self.assertEqual(set(path), {0, 1, 2, 3})
            self.assertTrue(all(path[i] == (path[0] + i) % 4 for i in range(4)))

    def test_rejects_invalid_parameters(self):
        cases = (
            (0, 1, 1, 0), (3, 0, 1, 0), (3, 4, 1, 0), (3, 1, 0, 0),
            (True, 1, 1, 0), (3, False, 1, 0), (3, 1, True, 0),
            (3.0, 1, 1, 0), (3, 1, 1, False), (3, 1, 1, 1.2),
        )
        for n, length, reps, seed in cases:
            with self.subTest(args=(n, length, reps, seed)):
                with self.assertRaises((TypeError, ValueError)):
                    circular_block_indices(n, block_length=length, replicates=reps, seed=seed)


class PairedResampleTests(unittest.TestCase):
    def test_one_path_preserves_alignment_and_sources(self):
        left = [10.0, 20.0, 30.0, 40.0, 50.0]
        right = [1.0, 2.0, 3.0, 4.0, 5.0]
        path = [4, 0, 1, 2, 3]
        result = paired_resample([left, right], path)
        self.assertEqual(result, ((50.0, 10.0, 20.0, 30.0, 40.0), (5.0, 1.0, 2.0, 3.0, 4.0)))
        self.assertEqual(left, [10.0, 20.0, 30.0, 40.0, 50.0])
        self.assertEqual(right, [1.0, 2.0, 3.0, 4.0, 5.0])
        self.assertEqual(path, [4, 0, 1, 2, 3])

    def test_singleton_and_constant_cash_path(self):
        self.assertEqual(paired_resample(((0.0,), (7,)), (0,)), ((0.0,), (7,)))
        self.assertEqual(paired_resample(((0.0, 0.0), (2.0, 4.0)), (1, 1)), ((0.0, 0.0), (4.0, 4.0)))

    def test_rejects_invalid_series_and_paths(self):
        cases = (
            ((), ()), (((1, 2), (3,)), (0, 1)), (((1, 2),), (0,)),
            (((1, 2),), ()), (((1, 2),), (-1, 0)), (((1, 2),), (0, 2)),
            (((1, 2),), (0, True)), (((1, 2),), (0, 1.0)),
            (((1, float('nan')),), (0, 1)), (((1, float('inf')),), (0, 1)),
            (((1, False),), (0, 1)), (((1, '2'),), (0, 1)),
            (((),), ()), (3.0, (0,)), (((1, 2),), 1),
            (((1, 2),), '01'), ('12', (0, 1)), ((1, 2), (0, 1)),
        )
        for series, path in cases:
            with self.subTest(series=series, path=path):
                with self.assertRaises((TypeError, ValueError)):
                    paired_resample(series, path)


if __name__ == '__main__':
    unittest.main()
