"""Fixture email dicts for unit tests (no live API calls)."""

APPLIED_GREENHOUSE = {
    "id": "msg001",
    "threadId": "thread001",
    "subject": "Your application to Stripe (Software Engineer, Backend)",
    "sender": "no-reply@stripe.greenhouse.io",
    "to": "chinmaymaheshwari.it27@gmail.com",
    "date": "Mon, 10 Feb 2025 09:15:00 +0000",
    "snippet": "Thank you for applying to Stripe. We have received your application for Software Engineer, Backend.",
    "body": "Thank you for applying to Stripe. We have received your application for the Software Engineer, Backend position.",
}

APPLIED_GENERIC_SUBJECT = {
    "id": "msg002",
    "threadId": "thread002",
    "subject": "Application received for Data Analyst at Razorpay",
    "sender": "careers@razorpay.com",
    "to": "chinmaymaheshwari.it27@gmail.com",
    "date": "Tue, 11 Feb 2025 10:00:00 +0000",
    "snippet": "We have received your application for Data Analyst.",
    "body": "",
}

RESPONSE_INTERVIEW = {
    "id": "msg101",
    "threadId": "thread101",
    "subject": "Interview invitation - Software Engineer at Stripe",
    "sender": "recruiter@stripe.com",
    "to": "chinmaymaheshwari.it27@gmail.com",
    "date": "Wed, 12 Feb 2025 14:00:00 +0000",
    "snippet": "We would like to invite you for a technical interview for the Software Engineer role.",
    "body": "We are pleased to invite you for a technical interview.",
}

RESPONSE_ASSESSMENT = {
    "id": "msg102",
    "threadId": "thread102",
    "subject": "Online Assessment - Razorpay Data Analyst",
    "sender": "noreply@hackerrank.com",
    "to": "chinmaymaheshwari.it27@gmail.com",
    "date": "Thu, 13 Feb 2025 09:00:00 +0000",
    "snippet": "You have been invited to complete a coding assessment.",
    "body": "Please complete the online test within 72 hours.",
}

RESPONSE_REJECTION = {
    "id": "msg103",
    "threadId": "thread103",
    "subject": "Update on your application",
    "sender": "no-reply@lever.co",
    "to": "chinmaymaheshwari.it27@gmail.com",
    "date": "Fri, 14 Feb 2025 16:00:00 +0000",
    "snippet": "Unfortunately, we will not be moving forward with your application at this time.",
    "body": "After careful consideration, unfortunately we will not be moving forward with other candidates.",
}

RESPONSE_SHORTLISTED = {
    "id": "msg104",
    "threadId": "thread104",
    "subject": "Congratulations! You have been shortlisted",
    "sender": "placement@college.edu",
    "to": "chinmaymaheshwari.it27@gmail.com",
    "date": "Sat, 15 Feb 2025 10:30:00 +0000",
    "snippet": "We are pleased to inform you that you have been shortlisted for the next round.",
    "body": "You have been shortlisted for the next round of selections.",
}
