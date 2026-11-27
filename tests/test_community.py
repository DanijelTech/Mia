"""The public repository keeps the GitHub community standards in place."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class CommunityStandardsTests(unittest.TestCase):
    REQUIRED = (
        "README.md", "README.sl.md", "LICENSE", "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md", "SECURITY.md", "SUPPORT.md", "GOVERNANCE.md",
        "ROADMAP.md", "ACCESSIBILITY.md", "CHANGELOG.md", "VERSION",
        ".github/pull_request_template.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/ISSUE_TEMPLATE/accessibility.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/workflows/ci.yml",
        "docs/COMMUNITY.md", "docs/en/COMMUNITY.md",
    )

    def test_required_files_exist(self):
        for name in self.REQUIRED:
            with self.subTest(file=name):
                self.assertTrue((ROOT / name).is_file(), name)

    def test_code_of_conduct_is_the_contributor_covenant(self):
        text = (ROOT / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8")
        self.assertIn("Contributor Covenant", text)
        self.assertIn("security/advisories/new", text)

    def test_readme_links_the_community_files(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        for name in ("CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "SECURITY.md",
                     "SUPPORT.md", "GOVERNANCE.md", "ROADMAP.md",
                     "ACCESSIBILITY.md"):
            with self.subTest(link=name):
                self.assertIn(name, text)

    def test_accessibility_has_commitment_and_reporting(self):
        text = (ROOT / "ACCESSIBILITY.md").read_text(encoding="utf-8")
        self.assertIn("commitment", text.lower())
        self.assertIn("Known limitations", text)
        self.assertIn("Reporting an accessibility barrier", text)


if __name__ == "__main__":
    unittest.main()
