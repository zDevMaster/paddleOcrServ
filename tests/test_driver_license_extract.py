from __future__ import annotations

import unittest

import cv2
import numpy as np

from app.extractors.driver_license import extract_driver_license
from app.preprocess import auto_correct_orientation


def _lines_from_text(text: str) -> list[dict]:
    return [{"text": line.strip(), "bbox": [], "score": 0.9} for line in text.splitlines() if line.strip()]


class DriverLicenseExtractTests(unittest.TestCase):
    def test_validity_end_long_term(self):
        text = """有效期限
2020-06-02至长期
姓名
张三"""
        fields, validation, _, _ = extract_driver_license(_lines_from_text(text))
        self.assertEqual(fields["有效期开始"]["value"], "2020-06-02")
        self.assertEqual(fields["有效期结束"]["value"], "长期")
        self.assertTrue(validation["rules"]["有效期结束合法"])

    def test_validity_range_on_one_line(self):
        text = """有效期限2025-11-06至长期
证号
110101199001011234"""
        fields, _, _, _ = extract_driver_license(_lines_from_text(text))
        self.assertEqual(fields["有效期结束"]["value"], "长期")

    def test_address_from_zhi_line(self):
        text = """住址
址河北省石家庄市裕华区某路1号
准驾车型
C1"""
        fields, _, _, _ = extract_driver_license(_lines_from_text(text))
        self.assertIn("石家庄", fields["住址"]["value"])


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
