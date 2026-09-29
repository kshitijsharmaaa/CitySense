# Generated for citizen-visible evidence of completed incident work.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("incidents", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="incident",
            name="resolution_image",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="incidents/resolutions/%Y/%m/",
                verbose_name="Resolution photo",
            ),
        ),
    ]
