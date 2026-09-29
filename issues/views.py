from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.decorators import admin_required, citizen_or_admin_required
from incidents.models import Incident, IncidentStatus
from incidents.services import update_incident_intelligence
from ai_engine.services import triage_issue

from .forms import IssueAdminFilterForm, IssueCreateForm
from .models import Issue, IssueImage, Priority
from incidents.presentation import complaint_age, complaint_progress
from .services import create_issue_with_incident


@citizen_or_admin_required
@require_GET
def issue_list(request):
    issues = Issue.objects.select_related(
        "incident__department", "incident__assigned_to", "ai_department"
    )
    if request.user.is_citizen:
        issues = issues.filter(reported_by=request.user)
        return render(request, "issues/list.html", {
            "issues": issues,
            "selected_status": "",
        })

    filters = IssueAdminFilterForm(request.GET or None)
    if filters.is_valid():
        values = filters.cleaned_data
        selected_status = values["status"]
        if selected_status == IncidentStatus.REPORTED:
            issues = issues.filter(
                Q(incident__isnull=True) | Q(incident__status=IncidentStatus.REPORTED)
            )
        elif selected_status:
            issues = issues.filter(incident__status=selected_status)

        priority = values["priority"]
        if priority:
            issues = issues.filter(
                Q(incident__priority=priority)
                | Q(incident__isnull=True, ai_priority=priority)
            )

        category = values["category"]
        if category:
            issues = issues.filter(
                Q(incident__category=category)
                | Q(incident__isnull=True, ai_category=category)
            )

        if values["department"]:
            issues = issues.filter(incident__department=values["department"])

        if values["assignment"] == "unassigned":
            issues = issues.filter(
                Q(incident__isnull=True)
                | Q(incident__department__isnull=True)
                | Q(incident__assigned_to__isnull=True)
            )
        elif values["assignment"] == "assigned":
            issues = issues.filter(
                incident__department__isnull=False,
                incident__assigned_to__isnull=False,
            )

        query = values["search"].strip()
        if query:
            issues = issues.filter(
                Q(issue_code__icontains=query)
                | Q(title__icontains=query)
                | Q(incident__incident_code__icontains=query)
                | Q(incident__title__icontains=query)
                | Q(incident__category__icontains=query)
                | Q(ai_category__icontains=query)
            )

        if values["sort"] == "oldest":
            issues = issues.order_by("created_at", "pk")
        elif values["sort"] == "priority":
            issues = issues.annotate(
                priority_rank=Case(
                    When(Q(incident__priority=Priority.CRITICAL) | Q(incident__isnull=True, ai_priority=Priority.CRITICAL), then=Value(0)),
                    When(Q(incident__priority=Priority.HIGH) | Q(incident__isnull=True, ai_priority=Priority.HIGH), then=Value(1)),
                    When(Q(incident__priority=Priority.MEDIUM) | Q(incident__isnull=True, ai_priority=Priority.MEDIUM), then=Value(2)),
                    When(Q(incident__priority=Priority.LOW) | Q(incident__isnull=True, ai_priority=Priority.LOW), then=Value(3)),
                    default=Value(4),
                    output_field=IntegerField(),
                )
            ).order_by("priority_rank", "-created_at", "-pk")
        else:
            issues = issues.order_by("-created_at", "-pk")
    else:
        selected_status = ""

    issues = issues.distinct()
    page_obj = Paginator(issues, 20).get_page(request.GET.get("page"))
    page_issues = list(page_obj.object_list)
    for issue in page_issues:
        incident = issue.incident
        status = incident.status if incident else IncidentStatus.REPORTED
        priority = incident.priority if incident else issue.ai_priority
        issue.display_category = (
            incident.get_category_display()
            if incident
            else (issue.get_ai_category_display() or "Not yet categorized")
        )
        issue.display_priority = priority
        issue.is_high_priority_open = (
            status not in (IncidentStatus.RESOLVED, IncidentStatus.REJECTED)
            and priority in (Priority.HIGH, Priority.CRITICAL)
        )
        issue.age = complaint_age(incident.created_at if incident else issue.created_at, priority, status=status)
        issue.is_unassigned = not incident or not incident.department or not incident.assigned_to

    base = Issue.objects.all()
    report_counts = {
        "total": base.count(),
        "open": base.filter(
            Q(incident__isnull=True)
            | ~Q(incident__status__in=(IncidentStatus.RESOLVED, IncidentStatus.REJECTED))
        ).count(),
        "assigned": base.filter(incident__status=IncidentStatus.ASSIGNED).count(),
        "in_progress": base.filter(incident__status=IncidentStatus.IN_PROGRESS).count(),
        "resolved": base.filter(incident__status=IncidentStatus.RESOLVED).count(),
        "closed": base.filter(incident__status=IncidentStatus.REJECTED).count(),
    }
    query_params = request.GET.copy()
    query_params.pop("page", None)
    return render(request, "issues/list.html", {
        "issues": page_issues,
        "page_obj": page_obj,
        "filter_query": query_params.urlencode(),
        "filters": filters,
        "selected_status": selected_status,
        "report_counts": report_counts,
    })

@citizen_or_admin_required
@require_http_methods(["GET", "POST"])
def create(request):
    form = IssueCreateForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        title = form.cleaned_data.get("title", "").strip()
        description = form.cleaned_data.get("description", "").strip()
        needs_generated_text = not title or not description
        triage_result = triage_issue(
            title=title,
            description=description,
            image=form.cleaned_data.get("image"),
            images=form.cleaned_data.get("images") or None,
            generate_report=needs_generated_text,
        )
        triage_result = dict(triage_result)
        # Citizens may edit the suggested classification. The incident service
        # validates these values and only applies them when it creates a new
        # incident; a matched incident keeps its canonical admin-controlled data.
        for field in ("category", "priority", "department"):
            citizen_value = form.cleaned_data.get(f"ai_{field}")
            if citizen_value:
                triage_result[field] = citizen_value
        if needs_generated_text:
            if not triage_result.get("generated_title") or not triage_result.get("generated_description"):
                message = (
                    "CitySense could not draft report text from this photo. "
                    "Please enter a title and description manually, then submit again."
                )
                if not title:
                    form.add_error("title", message)
                if not description:
                    form.add_error("description", message)
                return render(request, "issues/form.html", {"form": form})
            title = title or triage_result["generated_title"]
            description = description or triage_result["generated_description"]

        issue = form.save(commit=False)
        issue.title = title
        issue.description = description
        validated_triage = {
            key: triage_result[key]
            for key in ("category", "priority", "department", "summary", "confidence")
        }
        with transaction.atomic():
            issue = create_issue_with_incident(
                issue=issue,
                reported_by=request.user,
                triage_result=validated_triage,
            )
            for position, uploaded_image in enumerate(form.cleaned_data.get("images", [])):
                IssueImage.objects.create(issue=issue, image=uploaded_image, position=position)
        return redirect("issues:detail", pk=issue.pk)
    return render(request, "issues/form.html", {"form": form})


@citizen_or_admin_required
@require_POST
def analyze_photo(request):
    """Return a validated editable draft without saving or uploading the Issue."""
    form = IssueCreateForm(request.POST or None, request.FILES or None)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    image = form.cleaned_data.get("image")
    images = form.cleaned_data.get("images") or []
    if not image and not images:
        return JsonResponse({"error": "Choose a photo before asking CitySense to analyze it."}, status=400)

    result = triage_issue(
        title=form.cleaned_data.get("title", ""),
        description=form.cleaned_data.get("description", ""),
        image=image,
        images=images or None,
        generate_report=True,
    )
    if not result.get("generated_title") or not result.get("generated_description"):
        if result.get("_draft_error") == "free_tier_quota_exhausted":
            error = (
                "AI photo drafting is unavailable because Gemini's free-tier request quota is exhausted. "
                "Your photo is still attached. Enter a title and description manually now, or try again "
                "after the quota resets or is increased."
            )
        elif result.get("_draft_error") == "quota_exhausted":
            error = (
                "AI photo drafting is unavailable because Gemini's request quota is exhausted. "
                "Your photo is still attached. Enter the title and description manually, or try again "
                "after the quota resets or is increased."
            )
        elif result.get("_draft_error") == "missing_api_key":
            error = (
                "AI photo drafting is not configured right now. Your photo is still attached. "
                "Please enter the title and description manually."
            )
        elif result.get("_draft_error") == "rate_limited":
            error = (
                "AI photo drafting is temporarily rate limited. Your photo is still attached. "
                "Please wait before retrying, or enter the title and description manually."
            )
        else:
            error = (
                "CitySense could not draft report details from this photo right now. "
                "Your photo is still attached. Tap “Analyze photo with AI” to retry, or add or edit "
                "the title and description, then submit. If either is blank, enter both manually."
            )
        return JsonResponse({
            "error": error
        }, status=503)

    return JsonResponse({
        "title": result["generated_title"],
        "description": result["generated_description"],
        "category": result["category"],
        "priority": result["priority"],
        "department": result["department"],
        "summary": result["summary"],
        "confidence": result["confidence"],
    })


@citizen_or_admin_required
@require_GET
def detail(request, pk):
    issues = Issue.objects.select_related(
        "incident__department", "incident__assigned_to"
    ).prefetch_related("incident__status_history", "images")
    if request.user.is_citizen:
        issues = issues.filter(reported_by=request.user)
    issue = get_object_or_404(issues, pk=pk)
    incident = issue.incident
    status = incident.status if incident else IncidentStatus.REPORTED
    history = list(incident.status_history.all()) if incident else []
    issue_progress = complaint_progress(status, history)
    issue_age = complaint_age(
        incident.created_at if incident else issue.created_at,
        incident.priority if incident else issue.ai_priority,
        status=status,
    )
    if request.user.is_citizen and issue_age and issue_age["state"] != "overdue":
        issue_age = None
    return render(request, "issues/detail.html", {
        "issue": issue,
        "case_progress": issue_progress,
        "case_age": issue_age,
        "case_status": status,
        "case_next_action": issue_progress["next_action"],
    })


@admin_required
@require_http_methods(["POST"])
def delete_report(request, pk):
    """Delete one report and refresh its incident's derived intelligence."""
    with transaction.atomic():
        issue = get_object_or_404(
            Issue.objects.select_for_update().select_related("incident"), pk=pk
        )
        incident = issue.incident
        if incident is not None:
            incident = Incident.objects.select_for_update().get(pk=incident.pk)
        issue.delete()
        if incident is not None:
            update_incident_intelligence(incident)

    messages.success(request, "Report deleted successfully.")
    return redirect("issues:list")
