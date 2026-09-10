"""Unit tests for classify.py -- no live API calls."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import unittest
from job_tracker.classify import classify_response, status_label
from tests.fixtures.sample_emails import (
    RESPONSE_INTERVIEW, RESPONSE_ASSESSMENT,
    RESPONSE_REJECTION, RESPONSE_SHORTLISTED,
    APPLIED_GREENHOUSE,
)


class TestClassifyResponse(unittest.TestCase):
    def test_interview(self):
        self.assertEqual(classify_response(RESPONSE_INTERVIEW), "interview_invited")

    def test_assessment(self):
        self.assertEqual(classify_response(RESPONSE_ASSESSMENT), "assessment_invited")

    def test_rejection(self):
        self.assertEqual(classify_response(RESPONSE_REJECTION), "rejected")

    def test_shortlisted(self):
        self.assertEqual(classify_response(RESPONSE_SHORTLISTED), "shortlisted")

    def test_no_response_for_application_email(self):
        # Application confirmation should NOT be classified as a response
        status = classify_response(APPLIED_GREENHOUSE)
        self.assertEqual(status, "no_response")

    def test_offer(self):
        msg = {"subject": "Offer Letter - Software Engineer", "snippet": "We are pleased to offer you", "body": "Welcome aboard!"}
        self.assertEqual(classify_response(msg), "offer")


class TestStatusLabel(unittest.TestCase):
    def test_all_statuses(self):
        for s in ["offer","interview_invited","assessment_invited","shortlisted","rejected","no_response"]:
            label = status_label(s)
            self.assertIsInstance(label, str)
            self.assertTrue(len(label) > 0)


if __name__ == "__main__":
    unittest.main()
