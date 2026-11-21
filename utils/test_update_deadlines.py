import re
import unittest

import yaml

from update_deadlines import DATA_FILE, SOURCES_FILE, extract, remove_field, replace_field, visible_text


class UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        keys = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in keys:
                raise ValueError(f"Duplicate YAML key {key!r} at {key_node.start_mark}")
            keys.add(key)
        return super().construct_mapping(node, deep=deep)


class DeadlineUpdaterTests(unittest.TestCase):
    def test_source_configuration(self):
        conferences = yaml.load(DATA_FILE.read_text(), Loader=UniqueKeyLoader)
        sources = yaml.load(SOURCES_FILE.read_text(), Loader=UniqueKeyLoader)["sources"]
        conference_ids = [entry["id"] for entry in conferences]
        source_ids = [source["id"] for source in sources]
        self.assertEqual(len(conference_ids), len(set(conference_ids)), "Duplicate conference id")
        self.assertEqual(len(source_ids), len(set(source_ids)), "Duplicate deadline source id")
        for source in sources:
            with self.subTest(source=source["id"]):
                self.assertIn(source["id"], conference_ids)
                self.assertIn("deadline", source, "The updater requires a full-paper rule")
                for field in ("abstract_deadline", "deadline"):
                    if field in source:
                        rule = source[field]
                        self.assertIn("date", re.compile(rule["pattern"]).groupindex)
                        self.assertIsInstance(rule["formats"], list)
                        self.assertTrue(rule["formats"])

    def assert_source_dates(self, conference_id, raw_html, abstract, paper):
        sources = yaml.safe_load(SOURCES_FILE.read_text())["sources"]
        source = next(rule for rule in sources if rule["id"] == conference_id)
        text = visible_text(raw_html)
        self.assertEqual(extract(text, source["abstract_deadline"], 2027), abstract)
        self.assertEqual(extract(text, source["deadline"], 2027), paper)

    def test_cvpr_official_table_dates(self):
        self.assert_source_dates(
            "cvpr27",
            "<table>"
            "<tr><td><a>Paper Registration Deadline</a></td><td>Nov 10 '26 (Anywhere on Earth)</td></tr>"
            "<tr><td><a>Submission Deadline</a></td><td>Nov 16 '26 (Anywhere on Earth)</td></tr>"
            "<tr><td>Supplementary Materials Deadline</td><td>Nov 23 '26</td></tr>"
            "</table>",
            "2026-11-10 23:59:59",
            "2026-11-16 23:59:59",
        )

    def test_isca_official_table_dates_use_main_track(self):
        self.assert_source_dates(
            "isca27",
            "<table>"
            "<tr><th></th><th>Main Track</th><th>Industry Track</th></tr>"
            "<tr><td>Abstract Deadline</td><td>November 9, 2026</td><td>December 6, 2026</td></tr>"
            "<tr><td>Full Paper Deadline</td><td>November 16, 2026</td><td>December 13, 2026</td></tr>"
            "</table>",
            "2026-11-09 23:59:59",
            "2026-11-16 23:59:59",
        )

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
