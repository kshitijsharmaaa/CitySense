from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from accounts.decorators import citizen_required

from .forms import IssueCreateForm
from .models import Issue
from .services import create_issue_with_incident


@citizen_required
@require_GET
def issue_list(request):
    issues = Issue.objects.filter(reported_by=request.user).select_related("incident")
    return render(request, "issues/list.html", {"issues": issues})


@citizen_required
@require_http_methods(["GET", "POST"])
def create(request):
    form = IssueCreateForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        issue = create_issue_with_incident(issue=form.save(commit=False), reported_by=request.user)
        return redirect("issues:detail", pk=issue.pk)
    return render(request, "issues/form.html", {"form": form})


@citizen_required
@require_GET
def detail(request, pk):
    issue = get_object_or_404(
        Issue.objects.select_related("incident__department"),
        pk=pk,
        reported_by=request.user,
    )
    return render(request, "issues/detail.html", {"issue": issue})
