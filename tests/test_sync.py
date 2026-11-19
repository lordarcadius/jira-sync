import contextlib
import importlib.util
import io
import json
import re
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync = load("sync", ROOT / "scripts" / "sync.py")

WORK = {"timezone": "Asia/Kolkata", "start": "10:00", "end": "19:00", "days": [0, 1, 2, 3, 4]}
KOLKATA = ZoneInfo("Asia/Kolkata")


class WorkingHoursTest(unittest.TestCase):
    def test_counts_only_working_hours(self):
        monday_early = datetime(2026, 11, 16, 9, 0, tzinfo=KOLKATA)
        monday_late = datetime(2026, 11, 16, 20, 0, tzinfo=KOLKATA)
        self.assertEqual(sync.working_hours(monday_early, monday_late, WORK), 9)

    def test_skips_the_weekend(self):
        friday = datetime(2026, 11, 13, 18, 0, tzinfo=KOLKATA)
        monday = datetime(2026, 11, 16, 11, 0, tzinfo=KOLKATA)
        self.assertEqual(sync.working_hours(friday, monday, WORK), 2)

    def test_workday_length(self):
        self.assertEqual(sync.workday_hours(WORK), 9)


class ResolveSinceTest(unittest.TestCase):
    config = {"workHours": WORK, "overlapDays": 7, "firstRunLookbackDays": 7}

    def test_days(self):
        since = sync.resolve_since("3d", "org", self.config, {"lastSync": {}})
        expected = datetime.now(timezone.utc) - timedelta(days=3)
        self.assertLess(abs((since - expected).total_seconds()), 5)

    def test_date_is_read_in_the_work_time_zone(self):
        since = sync.resolve_since("2026-11-01", "org", self.config, {"lastSync": {}})
        self.assertEqual(since, datetime(2026, 11, 1, tzinfo=KOLKATA))

    def test_last_sync_minus_overlap(self):
        state = {"lastSync": {"org": "2026-11-18T13:51:07Z"}}
        since = sync.resolve_since(None, "org", self.config, state)
        self.assertEqual(since, datetime(2026, 11, 11, 13, 51, 7, tzinfo=timezone.utc))


class PatchHashTest(unittest.TestCase):
    def files(self, hunk, line):
        return [{"filename": "a.py", "status": "modified", "additions": 1, "deletions": 0, "patch": f"{hunk}\n+{line}"}]

    def test_same_change_at_other_line_numbers_matches(self):
        self.assertEqual(sync.patch_hash(self.files("@@ -1,2 +1,3 @@", "x")),
                         sync.patch_hash(self.files("@@ -40,2 +41,3 @@", "x")))

    def test_different_changes_differ(self):
        self.assertNotEqual(sync.patch_hash(self.files("@@ -1 +1 @@", "x")),
                            sync.patch_hash(self.files("@@ -1 +1 @@", "y")))


class JiraReferenceTest(unittest.TestCase):
    key = re.compile(r"\b(ABC)-\d+\b")

    def test_commit_message(self):
        self.assertEqual(sync.jira_reference(self.key, "ABC-12 fix login", ["main"], []),
                         "references ABC-12 in commit message")

    def test_pull_request(self):
        pulls = [{"number": 3, "title": "ABC-9 new page", "head": {"ref": "feature"}}]
        self.assertIn("PR #3", sync.jira_reference(self.key, "new page", ["main"], pulls))

    def test_ticket_branch_counts_only_when_no_other_branch_has_the_commit(self):
        self.assertIsNotNone(sync.jira_reference(self.key, "fix", ["ABC-7-login"], []))
        self.assertIsNone(sync.jira_reference(self.key, "fix", ["ABC-7-login", "main"], []))


class ConfigTest(unittest.TestCase):
    example = {"a": "", "b": [], "c": False, "d": {"e": "", "f": 7}, "g": {}}

    def test_new_config_gets_defaults_and_reports_placeholders(self):
        config = {}
        _, missing = sync.sync_config(config, self.example)
        self.assertEqual(missing, ["a", "b", "d.e"])
        self.assertEqual(config["d"]["f"], 7)

    def test_set_values_are_kept_and_null_means_unused(self):
        config = {"a": "x", "b": None, "c": True, "d": {"e": "y", "f": 1}, "g": {"k": 1}}
        self.assertEqual(sync.sync_config(config, self.example), ([], []))
        self.assertTrue(config["c"])

    def test_defaults_added_by_a_new_version(self):
        config = {"a": "x", "b": ["y"], "d": {"e": "y"}}
        added, missing = sync.sync_config(config, self.example)
        self.assertEqual(added, ["c", "d.f", "g"])
        self.assertEqual(missing, [])


class VersionTest(unittest.TestCase):
    def test_reads_the_front_matter_version_only(self):
        text = '---\nname: x\nmetadata:\n  version: "1.2.3"\n---\n# Body\n  version: 9\n'
        self.assertEqual(sync.skill_version(text), "1.2.3")

    def test_unknown_without_a_version(self):
        self.assertEqual(sync.skill_version("---\nname: x\n---\nbody"), "unknown")

    def test_this_skill_has_a_semantic_version(self):
        self.assertRegex(sync.current_version(), r"^\d+\.\d+\.\d+$")


class SecretTest(unittest.TestCase):
    # Fake secrets are assembled at runtime, so no secret-shaped text is stored in the repository.
    def file(self, name, added_line, status="added"):
        return {"filename": name, "status": status, "patch": "@@ -0,0 +1 @@\n+" + added_line}

    def test_finds_tokens_and_keys(self):
        token = "gh" + "p_" + "A1b2" * 9
        key = "-----BEGIN " + "RSA PRIVATE KEY-----"
        findings = sync.secret_findings([
            self.file("config/app.json", '{"token": "' + token + '"}'),
            self.file("deploy/id.txt", key),
        ])
        self.assertIn("GitHub token", findings[0])
        self.assertIn("private key", findings[1])
        self.assertNotIn(token, " ".join(findings))

    def test_finds_sensitive_file_names(self):
        findings = sync.secret_findings([self.file(".env", "DEBUG=1"), self.file("build/keys/app.json", "{}")])
        self.assertEqual(len(findings), 2)

    def test_ignores_placeholders_examples_ordinary_code_and_removed_files(self):
        findings = sync.secret_findings([
            self.file("app/config.py", 'password = "${DB_PASSWORD}"'),
            self.file(".env.example", "API_KEY=changeme"),
            self.file("src/PasswordField.kt", 'val label = "Password"'),
            self.file("old/secrets.json", '{"password": "' + "x" * 12 + '"}', status="removed"),
        ])
        self.assertEqual(findings, [])


class RunAndStateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        paths = {
            "STATE_PATH": root / "state.json",
            "CACHE_DIR": root / ".cache",
            "RUN_LOCK_PATH": root / ".cache" / "run.lock",
            "STATE_LOCK_PATH": root / ".cache" / "state.lock",
        }
        self.patches = [mock.patch.object(sync, name, value) for name, value in paths.items()]
        for patch in self.patches:
            patch.start()
        self.now = datetime(2026, 11, 19, 10, 0, tzinfo=timezone.utc)
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()

    def tearDown(self):
        self.quiet.__exit__(None, None, None)
        for patch in self.patches:
            patch.stop()
        self.tmp.cleanup()

    def write_fetch(self, fetch_id):
        change = {"id": "c1", "repo": "o/r", "commits": ["abc1234def"], "patch_hash": "h1"}
        sync.save_json(sync.fetch_path(fetch_id), {"id": fetch_id, "target": "o", "until": "2026-11-19T10:00:00Z",
                                                   "changes": [change]})

    def test_a_second_run_is_refused_while_one_is_open(self):
        sync.acquire_run_lock("a", self.now)
        with self.assertRaises(SystemExit):
            sync.acquire_run_lock("b", self.now + timedelta(minutes=5))

    def test_an_abandoned_run_is_replaced(self):
        sync.acquire_run_lock("a", self.now - timedelta(hours=13))
        sync.acquire_run_lock("b", self.now)
        self.assertEqual(sync.read_run_lock()["id"], "b")

    def test_a_run_only_releases_its_own_lock(self):
        sync.acquire_run_lock("a", self.now)
        self.assertIsNone(sync.release_run_lock("b"))
        self.assertEqual(sync.release_run_lock("a")["id"], "a")
        self.assertIsNone(sync.read_run_lock())

    def test_record_and_finish(self):
        self.write_fetch("x")
        sync.acquire_run_lock("x", self.now)
        sync.cmd_record(Namespace(fetch="x", ticket="ABC-1", change_ids=["c1"]))
        sync.cmd_finish(Namespace(fetch="x"))
        state = json.loads(sync.STATE_PATH.read_text())
        self.assertEqual(state["commits"], {"abc1234def": "ABC-1"})
        self.assertEqual(state["patches"], {"h1": "ABC-1"})
        self.assertEqual(state["lastSync"], {"o": "2026-11-19T10:00:00Z"})
        self.assertIsNone(sync.read_run_lock())
        self.assertFalse(sync.STATE_LOCK_PATH.exists())

    def test_unknown_fetch_or_change_is_refused(self):
        self.write_fetch("x")
        with self.assertRaises(SystemExit):
            sync.cmd_record(Namespace(fetch="y", ticket="ABC-1", change_ids=["c1"]))
        with self.assertRaises(SystemExit):
            sync.cmd_record(Namespace(fetch="x", ticket="ABC-1", change_ids=["c9"]))
        self.assertFalse(sync.STATE_PATH.exists())


if __name__ == "__main__":
    unittest.main()
