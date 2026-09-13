"""
tests/test_evaluate.py — Comprehensive unit tests for evaluate.py.
"""

from __future__ import annotations

import io
import json
import unittest
from unittest.mock import MagicMock, patch

from evaluate import (
    CANDIDATE,
    ai_evaluate,
    display_evaluation,
    local_evaluate,
)


class TestLocalEvaluateLocation(unittest.TestCase):
    def test_uk_work_auth_blocked(self):
        res = local_evaluate("Applicant must have right to work in UK.")
        self.assertEqual(res["local_verdict"], "SKIP")
        self.assertTrue(any("UK work authorization" in b for b in res["hard_blocks"]))

    def test_australia_work_auth_blocked(self):
        res = local_evaluate("Must be eligible to work in Australia without visa assistance.")
        self.assertEqual(res["local_verdict"], "SKIP")
        self.assertTrue(any("Australian work authorization" in b for b in res["hard_blocks"]))

    def test_us_only_blocked(self):
        res = local_evaluate("Candidate must be based in the US.")
        self.assertEqual(res["local_verdict"], "SKIP")
        self.assertTrue(any("US-only" in b for b in res["hard_blocks"]))

    def test_us_citizens_only_blocked(self):
        res = local_evaluate("Security clearance required. US citizens only.")
        self.assertEqual(res["local_verdict"], "SKIP")
        self.assertTrue(any("US citizens only" in b for b in res["hard_blocks"]))

    def test_northern_ireland_blocked(self):
        res = local_evaluate("Role open strictly to applicants within northern ireland.")
        self.assertEqual(res["local_verdict"], "SKIP")
        self.assertTrue(any("Northern Ireland" in b for b in res["hard_blocks"]))

    def test_eu_work_permit_blocked(self):
        res = local_evaluate("Must hold a valid EU work permit.")
        self.assertEqual(res["local_verdict"], "SKIP")
        self.assertTrue(any("EU work permit" in b for b in res["hard_blocks"]))


class TestLocalEvaluateStack(unittest.TestCase):
    def test_csharp_blocked(self):
        res = local_evaluate("We are hiring a C# Developer to maintain legacy ASP applications.")
        self.assertEqual(res["local_verdict"], "SKIP")
        self.assertTrue(any("C#" in b for b in res["hard_blocks"]))

    def test_dotnet_blocked(self):
        res = local_evaluate("Looking for a .NET developer with Azure experience.")
        self.assertEqual(res["local_verdict"], "SKIP")
        self.assertTrue(any(".NET" in b for b in res["hard_blocks"]))

    def test_rust_blocked(self):
        res = local_evaluate("We need an experienced Rust developer for blockchain systems.")
        self.assertEqual(res["local_verdict"], "SKIP")
        self.assertTrue(any("Rust" in b for b in res["hard_blocks"]))

    def test_golang_blocked(self):
        res = local_evaluate("Golang developer needed for cloud infrastructure.")
        self.assertEqual(res["local_verdict"], "SKIP")
        self.assertTrue(any("Go" in b for b in res["hard_blocks"]))

    def test_mobile_dev_blocked(self):
        res_ios = local_evaluate("Hiring an iOS developer with Swift expertise.")
        self.assertEqual(res_ios["local_verdict"], "SKIP")
        self.assertTrue(any("iOS" in b for b in res_ios["hard_blocks"]))

        res_android = local_evaluate("Seeking an Android developer for tablet apps.")
        self.assertEqual(res_android["local_verdict"], "SKIP")
        self.assertTrue(any("Android" in b for b in res_android["hard_blocks"]))


class TestLocalEvaluateDomain(unittest.TestCase):
    def test_hardware_fpga_blocked(self):
        res = local_evaluate("Design FPGA controllers and write Verilog modules.")
        self.assertEqual(res["local_verdict"], "SKIP")
        self.assertTrue(any("Hardware" in b for b in res["hard_blocks"]))

    def test_oracle_fusion_blocked(self):
        res = local_evaluate("Seeking an Oracle Fusion ERP consultant for implementation.")
        self.assertEqual(res["local_verdict"], "SKIP")
        self.assertTrue(any("Oracle ERP" in b for b in res["hard_blocks"]))

    def test_data_science_blocked(self):
        res = local_evaluate("Join us as a Data Scientist conducting predictive analytics.")
        self.assertEqual(res["local_verdict"], "SKIP")
        self.assertTrue(any("Data Science" in b for b in res["hard_blocks"]))

    def test_machine_learning_blocked(self):
        res = local_evaluate("Hiring a Machine Learning Engineer to train diffusion models.")
        self.assertEqual(res["local_verdict"], "SKIP")
        self.assertTrue(any("ML Engineering" in b for b in res["hard_blocks"]))


class TestLocalEvaluateExperienceAndSeniority(unittest.TestCase):
    def test_five_plus_years_blocked(self):
        res = local_evaluate("Requires 5+ years of experience in backend development.")
        self.assertEqual(res["local_verdict"], "SKIP")
        self.assertTrue(any("Requires 5+ years" in b for b in res["hard_blocks"]))

    def test_minimum_three_years_blocked(self):
        res = local_evaluate("Minimum 3 years of full-time software engineering experience.")
        self.assertEqual(res["local_verdict"], "SKIP")
        self.assertTrue(any("Requires 3+ years" in b for b in res["hard_blocks"]))

    def test_zero_to_two_years_allowed(self):
        res = local_evaluate("Java developer with at least 1 years experience or fresh graduate in India.")
        self.assertEqual(res["local_verdict"], "APPLY")
        self.assertEqual(res["hard_blocks"], [])

    def test_senior_signals_blocked(self):
        res = local_evaluate("Lead the team, set technical direction, and mentor junior engineers.")
        self.assertEqual(res["local_verdict"], "SKIP")
        self.assertTrue(any("mentoring junior engineers" in b for b in res["hard_blocks"]))
        self.assertTrue(any("setting technical direction" in b for b in res["hard_blocks"]))
        self.assertTrue(any("Leadership role" in b for b in res["hard_blocks"]))

    def test_staff_principal_engineer_blocked(self):
        res = local_evaluate("Position: Staff Engineer - Core Platform")
        self.assertEqual(res["local_verdict"], "SKIP")
        self.assertTrue(any("Staff level role" in b for b in res["hard_blocks"]))


class TestLocalEvaluateWarningsAndFlags(unittest.TestCase):
    def test_typescript_only_warning(self):
        res = local_evaluate("Role requires TypeScript for our services.")
        self.assertTrue(any("TypeScript-only" in w for w in res["warnings"]))

    def test_nestjs_warning(self):
        res = local_evaluate("Building backend with NestJS and PostgreSQL.")
        self.assertTrue(any("NestJS" in w for w in res["warnings"]))

    def test_python_primary_warning(self):
        res = local_evaluate("Seeking developer proficient in Python scripting.")
        self.assertTrue(any("Python-primary" in w for w in res["warnings"]))

    def test_multiple_warnings_borderline(self):
        res = local_evaluate("Role uses TypeScript, NestJS, and Python for tooling.")
        self.assertEqual(res["local_verdict"], "BORDERLINE")

    def test_green_flags_and_apply(self):
        res = local_evaluate(
            "Hiring a fresher or 2027 batch graduate for Java and Spring Boot role in India. "
            "Experience with React and REST APIs is a plus. Remote worldwide options available."
        )
        self.assertEqual(res["local_verdict"], "APPLY")
        self.assertTrue(any("Java" in f for f in res["green_flags_found"]))
        self.assertTrue(any("Spring Boot" in f for f in res["green_flags_found"]))
        self.assertTrue(any("India" in f for f in res["green_flags_found"]))


class TestDisplayEvaluation(unittest.TestCase):
    def test_display_evaluation_runs_cleanly(self):
        local_res = {
            "hard_blocks": ["❌ LOCATION: Requires UK work authorization"],
            "warnings": ["⚠️  TypeScript-only role"],
            "green_flags_found": ["✅ Java", "✅ Spring Boot"],
            "local_verdict": "SKIP",
        }
        ai_res = {
            "verdict": "SKIP",
            "score": 25,
            "company": "Acme UK",
            "role": "Backend Engineer",
            "one_line_reason": "Role requires UK visa authorization not held by candidate",
            "missing_skills": ["C#", ".NET"],
            "matched_skills": ["Java", "SQL"],
            "warnings": ["Requires UK relocation"],
            "apply_action": "Do not apply; search for India or remote worldwide roles",
            "resume_version": "java_backend",
        }

        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            display_evaluation(local_res, ai_res)
            output = fake_out.getvalue()
            self.assertIn("JD EVALUATION REPORT", output)
            self.assertIn("Acme UK", output)
            self.assertIn("25/100", output)
            self.assertIn("SKIP", output)


class TestAIEvaluate(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_ai_evaluate_parses_json(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_payload = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "verdict": "APPLY",
                        "score": 92,
                        "company": "TechCorp",
                        "role": "Java Developer",
                        "location_ok": True,
                        "experience_ok": True,
                        "stack_match_pct": 95,
                        "matched_skills": ["Java", "Spring Boot", "React"],
                        "missing_skills": [],
                        "hard_blocks": [],
                        "warnings": [],
                        "green_flags": ["Java", "Entry level"],
                        "resume_version": "java_backend",
                        "one_line_reason": "Excellent match for Java/Spring Boot stack",
                        "apply_action": "Tailor resume and apply immediately"
                    })
                }
            }]
        }
        mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = ai_evaluate("Hiring Java Developer in India", api_key="test_key_123")
        self.assertIsNotNone(result)
        self.assertEqual(result["verdict"], "APPLY")
        self.assertEqual(result["company"], "TechCorp")
        self.assertEqual(result["score"], 92)


if __name__ == "__main__":
    unittest.main()
