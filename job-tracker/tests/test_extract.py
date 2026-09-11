"""Unit tests for extract.py -- no live API calls."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import unittest
from job_tracker.extract import (
    extract_rule_based, _company_from_sender, _company_from_subject,
    _role_from_subject, _parse_date,
)
from tests.fixtures.sample_emails import (
    APPLIED_GREENHOUSE, APPLIED_GENERIC_SUBJECT,
)


class TestCompanyFromSender(unittest.TestCase):
    def test_greenhouse_subdomain(self):
        self.assertEqual(_company_from_sender("no-reply@stripe.greenhouse.io"), "Stripe")

    def test_lever_subdomain(self):
        self.assertEqual(_company_from_sender("jobs@acme-corp.lever.co"), "Acme Corp")

    def test_plain_domain(self):
        result = _company_from_sender("careers@razorpay.com")
        self.assertEqual(result, "Razorpay")

    def test_generic_domain_skipped(self):
        self.assertEqual(_company_from_sender("no-reply@gmail.com"), "")
        self.assertEqual(_company_from_sender("noreply@noreply.com"), "")

    def test_empty_sender(self):
        self.assertEqual(_company_from_sender(""), "")


class TestCompanyFromSubject(unittest.TestCase):
    def test_application_to(self):
        result = _company_from_subject("Application to Google for SWE")
        self.assertIn("Google", result)

    def test_no_match(self):
        self.assertEqual(_company_from_subject("Hello there"), "")


class TestRoleFromSubject(unittest.TestCase):
    def test_applied_for(self):
        r = _role_from_subject("Application received for Data Analyst at Razorpay")
        self.assertIn("Data Analyst", r)

    def test_no_match(self):
        self.assertEqual(_role_from_subject(""), "")


class TestParseDate(unittest.TestCase):
    def test_rfc2822(self):
        self.assertEqual(_parse_date("Mon, 10 Feb 2025 09:15:00 +0000"), "2025-02-10")

    def test_iso_fallback(self):
        self.assertEqual(_parse_date("2025-03-15"), "2025-03-15")

    def test_empty(self):
        result = _parse_date("")
        self.assertIsInstance(result, str)


class TestExtractRuleBased(unittest.TestCase):
    def test_greenhouse_email(self):
        info = extract_rule_based(APPLIED_GREENHOUSE)
        self.assertEqual(info["company"], "Stripe")
        self.assertEqual(info["date_applied"], "2025-02-10")

    def test_generic_subject(self):
        info = extract_rule_based(APPLIED_GENERIC_SUBJECT)
        self.assertIn("Razorpay", info["company"])

    def test_superset_submitted(self):
        msg = {
            "subject": "Application submitted: Auro Group’s Software Development Engineer",
            "sender": "Superset <notifications@joinsuperset.com>",
            "date": "2025-08-01",
        }
        info = extract_rule_based(msg)
        self.assertEqual(info["company"], "Auro Group")
        self.assertEqual(info["role"], "Software Development Engineer")

    def test_superset_by_college(self):
        msg = {
            "subject": "Application submitted by college for: TCS's Trainee Engineer",
            "sender": "Superset <notifications@joinsuperset.com>",
            "date": "2025-07-15",
        }
        info = extract_rule_based(msg)
        self.assertEqual(info["company"], "TCS")
        self.assertEqual(info["role"], "Trainee Engineer")

    def test_indeed_apply(self):
        msg = {
            "subject": "Indeed Application: Junior Backend Developer",
            "sender": "Indeed Apply <indeedapply@indeed.com>",
            "date": "2025-05-24",
        }
        info = extract_rule_based(msg)
        self.assertEqual(info["company"], "Indeed Apply")
        self.assertEqual(info["role"], "Junior Backend Developer")

    def test_uipath_application(self):
        msg = {
            "subject": "Thank you for your application to UiPath: Software Engineer 1",
            "sender": "UiPath Talent Acquisition <careers@uipath.com>",
            "date": "2025-06-01",
        }
        info = extract_rule_based(msg)
        self.assertEqual(info["company"], "UiPath")
        self.assertEqual(info["role"], "Software Engineer 1")


class TestNoiseFilter(unittest.TestCase):
    def test_linkedin_alert_is_noise(self):
        from job_tracker.extract import is_noise_email
        msg = {
            "sender": "LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>",
            "subject": "“app developer”: Jobactive NSW - Software and Application Programmer",
        }
        self.assertTrue(is_noise_email(msg))

    def test_github_oauth_is_noise(self):
        from job_tracker.extract import is_noise_email
        msg = {
            "sender": "GitHub <noreply@github.com>",
            "subject": "[GitHub] A third-party OAuth application has been added to your account",
        }
        self.assertTrue(is_noise_email(msg))

    def test_real_application_not_noise(self):
        from job_tracker.extract import is_noise_email
        msg = {
            "sender": "noreply@mail.amazon.jobs",
            "subject": "Thank you for Applying to Amazon!",
        }
        self.assertFalse(is_noise_email(msg))


if __name__ == "__main__":
    unittest.main()
