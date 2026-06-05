from __future__ import annotations

import unittest

from app.extractors import extract_idcard


def _lines_from_text(text: str) -> list[dict]:
    return [{"text": line.strip(), "bbox": [], "score": 0.9} for line in text.splitlines() if line.strip()]


class IdCardExtractTests(unittest.TestCase):
    def test_split_gender_ethnicity_from_merged_line(self):
        text = """公民身份号码
住址沈阳市辽中区大黑岗子镇
出生1978年11月20
性别女民族汉
姓名姚红杰
马家岗子村3组38号
210122197811206323"""
        fields, _, missing, _ = extract_idcard(_lines_from_text(text))
        self.assertEqual(fields["性别"]["value"], "女")
        self.assertEqual(fields["民族"]["value"], "汉")
        self.assertNotIn("民族", fields["性别"]["value"])
        self.assertIn("马家岗子村3组38号", fields["住址"]["value"])
        self.assertEqual(fields["姓名"]["value"], "姚红杰")
        self.assertEqual(fields["身份证号"]["value"], "210122197811206323")
        self.assertNotIn("性别", missing)

    def test_multiline_address_with_split_anchor(self):
        text = """崔建池
姓名
性别男民族汉
出生
1967年9月18日
住址
1
河北省沧州市东光县大单
镇孙营盘村582号
公民身份号码
13292719670918057X"""
        fields, _, _, _ = extract_idcard(_lines_from_text(text))
        self.assertEqual(fields["性别"]["value"], "男")
        self.assertEqual(fields["民族"]["value"], "汉")
        self.assertIn("东光县", fields["住址"]["value"])
        self.assertIn("582号", fields["住址"]["value"])
        self.assertNotEqual(fields["住址"]["value"], "1")

    def test_name_fallback_when_anchor_line_empty(self):
        text = """住址 山东省无棣县棣丰街道杨
出生1965年3月8日
性别男民族汉
姓名
公民身份号码
杨希山
白杨村74号
372324196503087217"""
        fields, _, _, _ = extract_idcard(_lines_from_text(text))
        self.assertEqual(fields["姓名"]["value"], "杨希山")
        self.assertIn("白杨村74号", fields["住址"]["value"])


if __name__ == "__main__":
    unittest.main()
