import unittest
import numpy as np
from src.lattice_strategies.graphs import mst_neighbors, tree_covariance


class GraphTests(unittest.TestCase):
    def test_signed_correlation_distance_selects_tree(self):
        corr = np.array([[1., .8, -.7], [.8, 1., -.5], [-.7, -.5, 1.]])
        self.assertEqual(mst_neighbors(corr), [[1], [0, 2], [1]])

    def test_tree_path_products_preserve_variances_and_are_positive(self):
        corr = np.array([[1., .8, -.1], [.8, 1., -.5], [-.1, -.5, 1.]])
        # The signed-distance tree picks A--B and A--C. The induced B--C
        # correlation is .8 * -.1 rather than its original -.5.
        scale = np.array([2., 3., 4.])
        cov = corr * np.outer(scale, scale)
        result = tree_covariance(cov)
        self.assertTrue(np.allclose(np.diag(result), scale**2))
        self.assertAlmostEqual(result[1, 2], -.08 * 3. * 4.)
        self.assertGreater(np.linalg.eigvalsh(result).min(), 0.)

    def test_invalid_matrix_is_rejected(self):
        with self.assertRaises(ValueError):
            mst_neighbors(np.array([[1., np.nan], [np.nan, 1.]]))
        with self.assertRaises(ValueError):
            tree_covariance(np.diag([1., 0.]))

    def test_identity_tree_has_no_invented_covariance(self):
        self.assertTrue(np.allclose(tree_covariance(np.eye(4)), np.eye(4)))


if __name__ == '__main__':
    unittest.main()
