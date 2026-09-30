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
from .validators import TriageValidationError, validate_report_draft, validate_triage_result


VALID_RESULT = {
    "category": "Pothole",
    "priority": "HIGH",
    "department": "Road Maintenance",
    "summary": "A pothole is reported near the library.",
    "confidence": 0.91,
}
VALID_REPORT_RESULT = {
    **VALID_RESULT,
    "generated_title": "Large pothole near the library",
    "generated_description": "A pothole is visible in the roadway near the library.",
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

    def test_valid_report_draft_has_validated_editable_text(self):
        validated = validate_report_draft(json.dumps(VALID_REPORT_RESULT))
        self.assertEqual(validated["generated_title"], VALID_REPORT_RESULT["generated_title"])
        self.assertEqual(validated["generated_description"], VALID_REPORT_RESULT["generated_description"])

    def test_valid_report_draft_accepts_json_code_fence_and_surrounding_whitespace(self):
        response = "  ```json\n" + json.dumps(VALID_REPORT_RESULT) + "\n```  "
        validated = validate_report_draft(response)
        self.assertEqual(validated["generated_title"], VALID_REPORT_RESULT["generated_title"])
        self.assertEqual(validated["generated_description"], VALID_REPORT_RESULT["generated_description"])

    def test_invalid_generated_report_fields_are_rejected(self):
        for field, value in (("generated_title", " "), ("generated_description", "x" * 2001)):
            with self.subTest(field=field):
                with self.assertRaises(TriageValidationError):
                    validate_report_draft({**VALID_REPORT_RESULT, field: value})


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

    @override_settings(AI_API_KEY="test-key")
    @patch("ai_engine.services.generate_with_gemini", return_value=json.dumps(VALID_REPORT_RESULT))
    def test_report_generation_returns_validated_draft(self, provider):
        result = triage_issue(title="", description="", image=object(), generate_report=True)
        self.assertEqual(result["generated_title"], VALID_REPORT_RESULT["generated_title"])
        provider.assert_called_once()
        self.assertTrue(provider.call_args.kwargs["generate_report"])

    @override_settings(AI_API_KEY="test-key")
    @patch("ai_engine.services.generate_with_gemini", side_effect=TimeoutError)
    def test_report_generation_timeout_uses_fallback_without_fabricated_draft(self, provider):
        result = triage_issue(title="", description="", image=object(), generate_report=True)
        self.assertEqual(result["category"], "Other")
        self.assertNotIn("generated_title", result)

    @override_settings(AI_API_KEY="test-key")
    @patch("ai_engine.services.generate_with_gemini")
    def test_report_generation_marks_exhausted_provider_quota(self, provider):
        class QuotaExceeded(Exception):
            code = 429

        provider.side_effect = QuotaExceeded("free_tier_requests quota exceeded")
        result = triage_issue(title="", description="", image=object(), generate_report=True)
        self.assertEqual(result["_draft_error"], "free_tier_quota_exhausted")
        self.assertNotIn("generated_title", result)

    @override_settings(AI_API_KEY="")
    @patch("ai_engine.services.generate_with_gemini")
    def test_missing_key_does_not_fabricate_image_only_report_text(self, provider):
        result = triage_issue(title="", description="", image=object(), generate_report=True)
        provider.assert_not_called()
        self.assertEqual(result["_draft_error"], "missing_api_key")
        self.assertNotIn("generated_title", result)
        self.assertNotIn("generated_description", result)

    @override_settings(AI_API_KEY="test-key")
    @patch("ai_engine.services.generate_with_gemini", return_value=json.dumps({
        **VALID_REPORT_RESULT, "generated_title": "x" * 256,
    }))
    def test_invalid_generated_text_uses_fallback_without_draft(self, provider):
        result = triage_issue(title="", description="", image=object(), generate_report=True)
        self.assertNotIn("generated_title", result)
        self.assertEqual(result["category"], "Other")


class GeminiProviderAdapterTests(TestCase):
    @override_settings(AI_API_KEY="test-key", AI_MODEL="test-model", AI_TIMEOUT_SECONDS=3)
    @patch("google.genai.Client")
    def test_provider_uses_configured_model_timeout_and_single_attempt(self, client_factory):
        client = client_factory.return_value.__enter__.return_value
        client.models.generate_content.return_value.text = json.dumps(VALID_RESULT)

        response = generate_with_gemini(title="Pothole", description="Near the library")

        self.assertEqual(response, json.dumps(VALID_RESULT))
        self.assertEqual(client.models.generate_content.call_args.kwargs["model"], "test-model")
        contents = client.models.generate_content.call_args.kwargs["contents"]
        self.assertEqual(contents.role, "user")
        self.assertEqual(len(contents.parts), 1)
        self.assertIn("Pothole", contents.parts[0].text)
        self.assertIn("Near the library", contents.parts[0].text)
        config = client.models.generate_content.call_args.kwargs["config"]
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertEqual(config.thinking_config.thinking_level.value, "MEDIUM")
        options = client_factory.call_args.kwargs["http_options"]
        self.assertEqual(options.timeout, 3000)
        self.assertEqual(options.retry_options.attempts, 1)

    @override_settings(AI_API_KEY="test-key", AI_MODEL="test-model", AI_TIMEOUT_SECONDS=3)
    @patch("ai_engine.providers.time.sleep")
    @patch("google.genai.Client")
    def test_provider_retries_one_transient_503(self, client_factory, sleep):
        from google.genai.errors import ServerError

        client_factory.return_value.__enter__.return_value.models.generate_content.side_effect = [
            ServerError(503, {"error": {"message": "temporarily unavailable"}}),
            type("GeminiResponse", (), {"text": json.dumps(VALID_RESULT)})(),
        ]

        response = generate_with_gemini(title="Pothole", description="Near the library")

        self.assertEqual(response, json.dumps(VALID_RESULT))
        self.assertEqual(client_factory.call_count, 2)
        sleep.assert_called_once_with(0.25)

    @override_settings(AI_API_KEY="test-key", AI_MODEL="test-model", AI_TIMEOUT_SECONDS=3)
    @patch("google.genai.Client")
    def test_provider_sends_text_and_image_bytes_in_one_multimodal_user_content(self, client_factory):
        image_bytes = self.make_image_bytes("PNG")
        upload = SimpleUploadedFile("report.png", image_bytes, content_type="image/png")
        upload.seek(4)
        client = client_factory.return_value.__enter__.return_value
        client.models.generate_content.return_value.text = json.dumps(VALID_RESULT)

        generate_with_gemini(title="There is a problem here", description="Near the library", image=upload)

        contents = client.models.generate_content.call_args.kwargs["contents"]
        self.assertEqual(contents.role, "user")
        self.assertEqual(len(contents.parts), 2)
        self.assertIn("There is a problem here", contents.parts[0].text)
        self.assertIn("Near the library", contents.parts[0].text)
        self.assertEqual(contents.parts[1].inline_data.mime_type, "image/png")
        self.assertEqual(contents.parts[1].inline_data.data, image_bytes)
        # The provider rewinds before reading and leaves the upload ready for
        # Django's later Issue.save() call.
        self.assertEqual(upload.tell(), 0)
        self.assertEqual(upload.read(), image_bytes)

    @override_settings(AI_API_KEY="test-key", AI_MODEL="test-model", AI_TIMEOUT_SECONDS=3)
    @patch("google.genai.Client")
    def test_provider_sends_all_photos_with_combined_evidence_instructions(self, client_factory):
        raw_images = [self.make_image_bytes("PNG"), self.make_image_bytes("JPEG")]
        uploads = [
            SimpleUploadedFile(f"angle-{index}.png", raw, content_type="image/png")
            for index, raw in enumerate(raw_images)
        ]
        client = client_factory.return_value.__enter__.return_value
        client.models.generate_content.return_value.text = json.dumps(VALID_REPORT_RESULT)

        generate_with_gemini(title="", description="", images=uploads, generate_report=True)

        contents = client.models.generate_content.call_args.kwargs["contents"]
        self.assertEqual(len(contents.parts), 3)
        self.assertIn("different angles", contents.parts[0].text)
        self.assertIn("generated_title", contents.parts[0].text)
        for part, raw in zip(contents.parts[1:], raw_images):
            self.assertEqual(part.inline_data.data, raw)
        self.assertTrue(all(upload.tell() == 0 for upload in uploads))

    @override_settings(AI_API_KEY="test-key", AI_MODEL="test-model", AI_TIMEOUT_SECONDS=3)
    @patch("google.genai.Client")
    def test_provider_uses_mime_type_from_validated_image_format(self, client_factory):
        for image_format, mime_type in (
            ("JPEG", "image/jpeg"),
            ("PNG", "image/png"),
            ("GIF", "image/gif"),
            ("WEBP", "image/webp"),
        ):
            with self.subTest(image_format=image_format):
                image_bytes = self.make_image_bytes(image_format)
                upload = SimpleUploadedFile(
                    f"report.{image_format.lower()}", image_bytes,
                    content_type="application/octet-stream",
                )
                generate_with_gemini(title="Report", description="Details", image=upload)
                contents = client_factory.return_value.__enter__.return_value.models.generate_content.call_args.kwargs["contents"]
                self.assertEqual(contents.parts[1].inline_data.mime_type, mime_type)
                self.assertEqual(contents.parts[1].inline_data.data, image_bytes)
                self.assertEqual(upload.tell(), 0)

    @override_settings(AI_API_KEY="test-key", AI_MODEL="test-model", AI_TIMEOUT_SECONDS=3)
    @patch("google.genai.Client")
    def test_report_generation_prompt_requests_draft_and_normalizes_jpeg_orientation(self, client_factory):
        original = PillowImage.new("RGB", (4, 2), color="red")
        exif = original.getexif()
        exif[274] = 6
        buffer = BytesIO()
        original.save(buffer, format="JPEG", exif=exif)
        original_bytes = buffer.getvalue()
        upload = SimpleUploadedFile("rotated.jpg", original_bytes, content_type="image/jpeg")
        client = client_factory.return_value.__enter__.return_value
        client.models.generate_content.return_value.text = json.dumps(VALID_REPORT_RESULT)

        generate_with_gemini(
            title="", description="", image=upload, generate_report=True,
        )

        contents = client.models.generate_content.call_args.kwargs["contents"]
        self.assertIn("generated_title", contents.parts[0].text)
        self.assertIn("Identify the visible civic problem", contents.parts[0].text)
        self.assertEqual(contents.parts[1].inline_data.mime_type, "image/jpeg")
        config = client.models.generate_content.call_args.kwargs["config"]
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertEqual(config.thinking_config.thinking_level.value, "LOW")
        normalized_bytes = contents.parts[1].inline_data.data
        with PillowImage.open(BytesIO(normalized_bytes)) as normalized:
            self.assertEqual(normalized.size, (2, 4))
            self.assertEqual(normalized.getexif().get(274, 1), 1)
        self.assertEqual(upload.tell(), 0)
        self.assertEqual(upload.read(), original_bytes)

    @staticmethod
    def make_image_bytes(image_format):
        buffer = BytesIO()
        PillowImage.new("RGB", (2, 2), color="red").save(buffer, format=image_format)
        return buffer.getvalue()


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

    @override_settings(AI_API_KEY="test-key", AI_MODEL="test-model", AI_TIMEOUT_SECONDS=3)
    @patch("google.genai.Client")
    def test_uploaded_image_reaches_gemini_with_report_text(self, client_factory):
        buffer = BytesIO()
        PillowImage.new("RGB", (2, 2), color="red").save(buffer, format="JPEG")
        image_bytes = buffer.getvalue()
        client = client_factory.return_value.__enter__.return_value
        client.models.generate_content.return_value.text = json.dumps(VALID_RESULT)

        response = self.client.post(reverse("issues:create"), {
            "title": "There is a problem here",
            "description": "Near the library",
            "image": SimpleUploadedFile("report.jpg", image_bytes, content_type="image/jpeg"),
        })

        self.assertEqual(response.status_code, 302)
        contents = client.models.generate_content.call_args.kwargs["contents"]
        self.assertEqual(contents.role, "user")
        self.assertIn("There is a problem here", contents.parts[0].text)
        self.assertIn("Near the library", contents.parts[0].text)
        self.assertEqual(contents.parts[1].inline_data.mime_type, "image/jpeg")
        self.assertEqual(contents.parts[1].inline_data.data, image_bytes)
        issue = Issue.objects.get()
        with issue.image.open("rb") as saved_image:
            self.assertEqual(saved_image.read(), image_bytes)

    @override_settings(AI_API_KEY="test-key", AI_MODEL="test-model", AI_TIMEOUT_SECONDS=3)
    @patch("google.genai.Client")
    def test_analyze_endpoint_sends_selected_image_and_text_to_gemini(self, client_factory):
        buffer = BytesIO()
        PillowImage.new("RGB", (3, 2), color="blue").save(buffer, format="PNG")
        image_bytes = buffer.getvalue()
        client = client_factory.return_value.__enter__.return_value
        client.models.generate_content.return_value.text = json.dumps(VALID_REPORT_RESULT)

        response = self.client.post(reverse("issues:analyze_photo"), {
            "title": "There is a problem here",
            "description": "Near the library entrance",
            "image": SimpleUploadedFile("report.png", image_bytes, content_type="image/png"),
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], VALID_REPORT_RESULT["generated_title"])
        contents = client.models.generate_content.call_args.kwargs["contents"]
        self.assertEqual(contents.role, "user")
        self.assertIn("There is a problem here", contents.parts[0].text)
        self.assertIn("Near the library entrance", contents.parts[0].text)
        self.assertEqual(contents.parts[1].inline_data.mime_type, "image/png")
        self.assertEqual(contents.parts[1].inline_data.data, image_bytes)
        self.assertFalse(Issue.objects.exists())

    @override_settings(AI_API_KEY="test-key", AI_MODEL="test-model", AI_TIMEOUT_SECONDS=3)
    @patch("google.genai.Client")
    def test_image_only_analyze_endpoint_allows_blank_text_and_sends_image(self, client_factory):
        image_bytes = GeminiProviderAdapterTests.make_image_bytes("JPEG")
        client = client_factory.return_value.__enter__.return_value
        client.models.generate_content.return_value.text = json.dumps(VALID_REPORT_RESULT)

        response = self.client.post(reverse("issues:analyze_photo"), {
            "title": "", "description": "",
            "image": SimpleUploadedFile("pothole.jpg", image_bytes, content_type="image/jpeg"),
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], VALID_REPORT_RESULT["generated_title"])
        self.assertEqual(response.json()["description"], VALID_REPORT_RESULT["generated_description"])
        contents = client.models.generate_content.call_args.kwargs["contents"]
        self.assertIn("treat it as primary visual evidence", contents.parts[0].text)
        self.assertIn("Citizen report title:\n\n", contents.parts[0].text)
        self.assertIn("Citizen report description:\n\n", contents.parts[0].text)
        self.assertEqual(contents.parts[1].inline_data.mime_type, "image/jpeg")
        self.assertEqual(contents.parts[1].inline_data.data, image_bytes)
        self.assertFalse(Issue.objects.exists())

    @override_settings(AI_API_KEY="test-key", AI_MODEL="test-model", AI_TIMEOUT_SECONDS=3)
    @patch("google.genai.Client")
    def test_image_only_gemini_draft_is_saved_and_seeds_incident(self, client_factory):
        image_bytes = GeminiProviderAdapterTests.make_image_bytes("PNG")
        client = client_factory.return_value.__enter__.return_value
        client.models.generate_content.return_value.text = json.dumps(VALID_REPORT_RESULT)

        response = self.client.post(reverse("issues:create"), {
            "title": "", "description": "",
            "image": SimpleUploadedFile("pothole.png", image_bytes, content_type="image/png"),
        })

        self.assertEqual(response.status_code, 302)
        issue = Issue.objects.get()
        self.assertEqual(issue.title, VALID_REPORT_RESULT["generated_title"])
        self.assertEqual(issue.description, VALID_REPORT_RESULT["generated_description"])
        self.assertEqual(issue.ai_category, VALID_RESULT["category"])
        self.assertEqual(issue.ai_priority, VALID_RESULT["priority"])
        self.assertEqual(issue.ai_department.name, VALID_RESULT["department"])
        self.assertEqual(issue.incident.category, VALID_RESULT["category"])
        self.assertEqual(issue.incident.priority, VALID_RESULT["priority"])
        self.assertEqual(issue.incident.department.name, VALID_RESULT["department"])
        with issue.image.open("rb") as saved_image:
            self.assertEqual(saved_image.read(), image_bytes)
        contents = client.models.generate_content.call_args.kwargs["contents"]
        self.assertEqual(contents.parts[1].inline_data.data, image_bytes)
        self.assertEqual(contents.parts[1].inline_data.mime_type, "image/png")

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
