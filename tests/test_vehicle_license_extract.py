from __future__ import annotations

import unittest

from app.extractors.vehicle_license import extract_vehicle_license


def _lines_from_text(text: str) -> list[dict]:
    return [{"text": line.strip(), "bbox": [], "score": 0.9} for line in text.splitlines() if line.strip()]


class VehicleLicenseExtractTests(unittest.TestCase):
    def test_brand_model_after_use_character_noise(self):
        text = """品牌型号
货运
欧曼牌BJ4259Y6DHL-05
车辆识别代号
LRDS6PEB0MT060767"""
        fields, _, _, _ = extract_vehicle_license(_lines_from_text(text))
        self.assertEqual(fields["品牌型号"]["value"], "欧曼牌BJ4259Y6DHL-05")

    def test_brand_model_on_same_line_as_typo_anchor(self):
        text = """做型号东风牌DFH4250D4
车辆识别代号
LGAG4DY31L8027932"""
        fields, _, _, _ = extract_vehicle_license(_lines_from_text(text))
        self.assertEqual(fields["品牌型号"]["value"], "东风牌DFH4250D4")

    def test_vin_skips_label_line(self):
        text = """车辆识别代号
VIN
LRDS6PEB0MT060767
发动机号码
76969769"""
        fields, _, _, _ = extract_vehicle_license(_lines_from_text(text))
        self.assertEqual(fields["车辆识别代号"]["value"], "LRDS6PEB0MT060767")

    def test_address_from_zhi_prefix_line(self):
        text = """住
址河北省石家庄市井泾县南峪镇贵泉村冯家路264号
使用性质货运"""
        fields, _, _, _ = extract_vehicle_license(_lines_from_text(text))
        self.assertIn("井泾县", fields["住址"]["value"])

    def test_owner_split_lines(self):
        text = """所有
人
冯志国
住址
河北省石家庄市"""
        fields, _, _, _ = extract_vehicle_license(_lines_from_text(text))
        self.assertEqual(fields["所有人"]["value"], "冯志国")

    def test_issuing_authority_merge_fragments(self):
        text = """河北省石家
庄市公安局
交通管理局
注册日期
2023-09-01"""
        fields, _, _, _ = extract_vehicle_license(_lines_from_text(text))
        self.assertIn("公安局", fields["发证单位"]["value"])
        self.assertIn("交通", fields["发证单位"]["value"])

    def test_engine_skips_inspection_line(self):
        text = """发动机号码
检验有效期至2023年03月冀B
76969769"""
        fields, _, _, _ = extract_vehicle_license(_lines_from_text(text))
        self.assertEqual(fields["发动机号码"]["value"], "76969769")

    def test_dates_with_typo_anchors(self):
        text = """注册日期
2023-09-01
发证扫期
2025-05-21"""
        fields, _, _, _ = extract_vehicle_license(_lines_from_text(text))
        self.assertEqual(fields["注册日期"]["value"], "2023-09-01")
        self.assertEqual(fields["发证日期"]["value"], "2025-05-21")


if __name__ == "__main__":
    unittest.main()
