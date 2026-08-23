import unittest

from update_deadlines import extract, remove_field, replace_field, visible_text


class DeadlineUpdaterTests(unittest.TestCase):
    def test_extract_labeled_date(self):
        rule = {"pattern": r"Paper deadline (?P<date>[A-Z][a-z]+ \d+, \d{4})", "formats": ["%b %d, %Y"]}
        self.assertEqual(extract("Paper deadline Sep 25, 2026 AOE", rule, 2027), "2026-09-25 23:59:59")

    def test_rejects_unrelated_year(self):
        rule = {"pattern": r"Paper deadline (?P<date>[A-Z][a-z]+ \d+, \d{4})", "formats": ["%b %d, %Y"]}
        with self.assertRaises(ValueError):
            extract("Paper deadline Sep 25, 2024", rule, 2027)

    def test_replaces_only_requested_entry(self):
        data = "- title: A\n  id: a27\n  deadline: TBA\n- title: B\n  id: b27\n  deadline: TBA\n"
        changed = replace_field(data, "b27", "deadline", "2026-09-25 23:59:59")
        self.assertIn("id: a27\n  deadline: TBA", changed)
        self.assertIn("id: b27\n  deadline: '2026-09-25 23:59:59'", changed)

    def test_visible_text(self):
        self.assertEqual(visible_text("<p>Paper&nbsp;deadline <b>Sep 25</b></p>"), "Paper deadline Sep 25")

    def test_inserts_optional_field_and_removes_previous_value(self):
        data = "- title: A\n  id: a27\n  deadline: TBA\n  previous_deadline: old\n"
        changed = replace_field(data, "a27", "abstract_deadline", "2026-09-18 23:59:59")
        changed = remove_field(changed, "a27", "previous_deadline")
        self.assertIn("abstract_deadline: '2026-09-18 23:59:59'", changed)
        self.assertNotIn("previous_deadline", changed)


if __name__ == "__main__":
    unittest.main()
