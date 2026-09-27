import json
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image as PillowImage

from incidents.models import IncidentStatus, IncidentStatusHistory
from issues.models import Issue

from .fallback import classify_fallback
from .providers import generate_with_gemini
from .services import triage_issue
from .validators import TriageValidationError, validate_triage_result


VALID_RESULT = {
    "category": "Pothole",
    "priority": "HIGH",
    "department": "Road Maintenance",
    "summary": "A pothole is reported near the library.",
    "confidence": 0.91,
}


class TriageValidationTests(TestCase):
    def test_valid_ai_response_is_parsed_and_normalized(self):
        validated = validate_triage_result(json.dumps(VALID_RESULT))
        self.assertEqual(validated["category"], "Pothole")
        self.assertEqual(validated["priority"], "HIGH")
        self.assertEqual(validated["department"], "Road Maintenance")
        self.assertEqual(validated["summary"], VALID_RESULT["summary"])
        self.assertEqual(validated["confidence"], 0.91)

    def test_allowed_enum_values_are_accepted(self):
        self.assertEqual(validate_triage_result(VALID_RESULT), VALID_RESULT)

    def test_invalid_category_is_rejected(self):
        result = {**VALID_RESULT, "category": "Traffic"}
        with self.assertRaises(TriageValidationError):
            validate_triage_result(result)

    def test_invalid_priority_is_rejected(self):
        result = {**VALID_RESULT, "priority": "URGENT"}
        with self.assertRaises(TriageValidationError):
            validate_triage_result(result)

    def test_invalid_department_is_rejected(self):
        result = {**VALID_RESULT, "department": "City Hall"}
        with self.assertRaises(TriageValidationError):
            validate_triage_result(result)

    def test_invalid_confidence_is_rejected(self):
        for confidence in (-0.1, 1.1, float("nan"), True):
            with self.subTest(confidence=confidence):
                with self.assertRaises(TriageValidationError):
                    validate_triage_result({**VALID_RESULT, "confidence": confidence})

    def test_malformed_json_is_rejected(self):
        with self.assertRaises(TriageValidationError):
            validate_triage_result('{"category":')


class TriageServiceTests(TestCase):
    @override_settings(AI_API_KEY="test-key")
    @patch("ai_engine.services.generate_with_gemini", return_value=json.dumps(VALID_RESULT))
    def test_service_returns_validated_provider_response(self, provider):
        result = triage_issue(title="Pothole", description="Near the library")
        provider.assert_called_once()
        self.assertEqual(result, VALID_RESULT)

    @override_settings(AI_API_KEY="test-key")
    @patch("ai_engine.services.generate_with_gemini", side_effect=TimeoutError)
    def test_provider_timeout_uses_fallback(self, provider):
        result = triage_issue(title="Garbage pile", description="Trash on the sidewalk")
        provider.assert_called_once()
        self.assertEqual(result["category"], "Garbage")
        self.assertEqual(result["department"], "Sanitation")

    @override_settings(AI_API_KEY="test-key")
    @patch("ai_engine.services.generate_with_gemini", return_value="not JSON")
    def test_malformed_provider_response_uses_fallback(self, provider):
        result = triage_issue(title="Broken streetlight", description="Light not working")
        self.assertEqual(result["category"], "Streetlight")
        self.assertEqual(result["department"], "Electrical")

    @override_settings(AI_API_KEY="test-key")
    @patch("ai_engine.services.generate_with_gemini", return_value=json.dumps({**VALID_RESULT, "category": "Nope"}))
    def test_invalid_provider_values_use_fallback(self, provider):
        result = triage_issue(title="Water leak", description="Leaking pipe")
        self.assertEqual(result["category"], "Water Leakage")
        self.assertEqual(result["department"], "Water Supply")

    @override_settings(AI_API_KEY="")
    @patch("ai_engine.services.generate_with_gemini")
    def test_missing_key_skips_provider_and_uses_fallback(self, provider):
        result = triage_issue(title="Unknown issue", description="Something happened")
        provider.assert_not_called()
        self.assertEqual(result["category"], "Other")
        self.assertEqual(result["department"], "General")


class GeminiProviderAdapterTests(TestCase):
    @override_settings(AI_API_KEY="test-key", AI_MODEL="test-model", AI_TIMEOUT_SECONDS=3)
    @patch("google.genai.Client")
    def test_provider_uses_configured_model_timeout_and_single_attempt(self, client_factory):
        client = client_factory.return_value.__enter__.return_value
        client.models.generate_content.return_value.text = json.dumps(VALID_RESULT)

        response = generate_with_gemini(title="Pothole", description="Near the library")

        self.assertEqual(response, json.dumps(VALID_RESULT))
        self.assertEqual(client.models.generate_content.call_args.kwargs["model"], "test-model")
        options = client_factory.call_args.kwargs["http_options"]
        self.assertEqual(options.timeout, 3000)
        self.assertEqual(options.retry_options.attempts, 1)

    @override_settings(AI_API_KEY="test-key", AI_MODEL="test-model", AI_TIMEOUT_SECONDS=3)
    @patch("google.genai.Client")
    def test_provider_includes_optional_image_and_restores_file_position(self, client_factory):
        buffer = BytesIO()
        PillowImage.new("RGB", (2, 2), color="red").save(buffer, format="PNG")
        image_bytes = buffer.getvalue()
        upload = SimpleUploadedFile("report.png", image_bytes, content_type="image/png")
        client = client_factory.return_value.__enter__.return_value
        client.models.generate_content.return_value.text = json.dumps(VALID_RESULT)

        generate_with_gemini(title="Pothole", description="Near the library", image=upload)

        contents = client.models.generate_content.call_args.kwargs["contents"]
        self.assertEqual(contents[1].inline_data.mime_type, "image/png")
        self.assertEqual(upload.read(), image_bytes)


class FallbackClassifierTests(TestCase):
    def test_keyword_categories_departments_and_priority(self):
        cases = (
            ("Road hole", "Potholes on the road", "Pothole", "Road Maintenance", "MEDIUM"),
            ("Waste", "Trash and garbage", "Garbage", "Sanitation", "MEDIUM"),
            ("Lamp", "Street lamp is not working", "Streetlight", "Electrical", "MEDIUM"),
            ("Pipe", "Water leaking from pipe", "Water Leakage", "Water Supply", "MEDIUM"),
            ("Drain", "Drainage is blocked", "Drainage", "Drainage", "MEDIUM"),
            ("Road", "Damaged road by intersection", "Road Damage", "Road Maintenance", "MEDIUM"),
            ("Wire", "Exposed wire is dangerous", "Other", "General", "HIGH"),
            ("Fire", "Fire near road", "Other", "General", "CRITICAL"),
        )
        for title, description, category, department, priority in cases:
            with self.subTest(description=description):
                result = classify_fallback(title=title, description=description)
                self.assertEqual(result["category"], category)
                self.assertEqual(result["department"], department)
                self.assertEqual(result["priority"], priority)


class IssueTriageIntegrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="triage@example.com", name="Triage Citizen", password="CivicPass!2719"
        )
        self.client.force_login(self.user)

    @override_settings(AI_API_KEY="test-key")
    @patch("ai_engine.services.generate_with_gemini", side_effect=TimeoutError)
    def test_issue_submission_succeeds_when_ai_fails(self, provider):
        response = self.client.post(reverse("issues:create"), {
            "title": "Pothole near school",
            "description": "A dangerous pothole in the road.",
        })

        issue = Issue.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(issue.ai_category, "Pothole")
        self.assertEqual(issue.ai_priority, "HIGH")
        self.assertEqual(issue.ai_department.name, "Road Maintenance")
        self.assertIsNotNone(issue.incident)
        self.assertEqual(issue.incident.category, "Pothole")
        self.assertEqual(issue.incident.priority, "HIGH")
        self.assertEqual(issue.incident.department.name, "Road Maintenance")
        self.assertEqual(issue.incident.status, IncidentStatus.REPORTED)
        history = IncidentStatusHistory.objects.get(incident=issue.incident)
        self.assertEqual(history.old_status, "")
        self.assertEqual(history.new_status, IncidentStatus.REPORTED)
        self.assertEqual(history.changed_by, self.user)

    @override_settings(AI_API_KEY="test-key")
    @patch("ai_engine.services.generate_with_gemini", return_value=json.dumps(VALID_RESULT))
    def test_valid_ai_recommendation_is_saved_on_issue_and_new_incident(self, provider):
        response = self.client.post(reverse("issues:create"), {
            "title": "Report title",
            "description": "Report description",
        })

        issue = Issue.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(issue.ai_category, "Pothole")
        self.assertEqual(issue.ai_priority, "HIGH")
        self.assertEqual(issue.ai_department.name, "Road Maintenance")
        self.assertEqual(issue.ai_summary, VALID_RESULT["summary"])
        self.assertAlmostEqual(issue.ai_confidence, 0.91)
        self.assertEqual(issue.incident.category, "Pothole")
        self.assertEqual(issue.incident.priority, "HIGH")
        self.assertEqual(issue.incident.department.name, "Road Maintenance")
        self.assertEqual(issue.incident.status, IncidentStatus.REPORTED)

    @override_settings(AI_API_KEY="test-key")
    @patch(
        "ai_engine.services.generate_with_gemini",
        return_value=json.dumps({**VALID_RESULT, "priority": "URGENT"}),
    )
    def test_invalid_ai_output_uses_fallback_for_new_incident(self, provider):
        response = self.client.post(reverse("issues:create"), {
            "title": "Dangerous pothole near school",
            "description": "A dangerous pothole is blocking the road.",
        })

        issue = Issue.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(issue.ai_category, "Pothole")
        self.assertEqual(issue.ai_priority, "HIGH")
        self.assertEqual(issue.ai_department.name, "Road Maintenance")
        self.assertEqual(issue.incident.category, issue.ai_category)
        self.assertEqual(issue.incident.priority, issue.ai_priority)
        self.assertEqual(issue.incident.department, issue.ai_department)
        self.assertEqual(issue.incident.status, IncidentStatus.REPORTED)
