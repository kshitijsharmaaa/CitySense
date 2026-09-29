# Generated for ordered multi-photo issue evidence.
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("issues", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="IssueImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to="issues/images/%Y/%m/related/")),
                ("position", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("issue", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="images", to="issues.issue")),
            ],
            options={
                "ordering": ["position", "created_at", "pk"],
            },
        ),
    ]
