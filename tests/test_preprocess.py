from __future__ import annotations

import unittest

import cv2
import numpy as np

from app.preprocess import auto_correct_orientation, iter_document_orientations


class PreprocessOrientationTests(unittest.TestCase):
    def test_auto_correct_orientation_for_rotated_text_bars(self):
        h, w = 200, 400
        upright = np.full((h, w), 255, dtype=np.uint8)
        for y in (60, 100, 140):
            cv2.line(upright, (30, y), (w - 30, y), 0, 2)
        upright_bgr = cv2.cvtColor(upright, cv2.COLOR_GRAY2BGR)
        rotated = cv2.rotate(upright_bgr, cv2.ROTATE_90_CLOCKWISE)

        corrected, angle = auto_correct_orientation(rotated)
        self.assertIn(angle, (270, 90))
        self.assertGreater(corrected.shape[1], corrected.shape[0])


if __name__ == "__main__":
    unittest.main()
