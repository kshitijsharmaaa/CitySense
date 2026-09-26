from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from accounts.decorators import citizen_or_admin_required, citizen_required
from ai_engine.services import triage_issue

from .forms import IssueCreateForm
from .models import Issue
from .services import create_issue_with_incident


@citizen_or_admin_required
@require_GET
def issue_list(request):
    issues = Issue.objects.select_related("incident")
    if request.user.is_citizen:
        issues = issues.filter(reported_by=request.user)
    return render(request, "issues/list.html", {"issues": issues})


@citizen_required
@require_http_methods(["GET", "POST"])
def create(request):
    form = IssueCreateForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        issue = form.save(commit=False)
        triage_result = triage_issue(
            title=issue.title,
            description=issue.description,
            image=form.cleaned_data.get("image"),
        )
        issue = create_issue_with_incident(
            issue=issue,
            reported_by=request.user,
            triage_result=triage_result,
        )
        return redirect("issues:detail", pk=issue.pk)
    return render(request, "issues/form.html", {"form": form})


@citizen_or_admin_required
@require_GET
def detail(request, pk):
    issues = Issue.objects.select_related("incident__department")
    if request.user.is_citizen:
        issues = issues.filter(reported_by=request.user)
    issue = get_object_or_404(issues, pk=pk)
    return render(request, "issues/detail.html", {"issue": issue})
