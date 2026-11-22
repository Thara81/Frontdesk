from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sla", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="BusinessHoliday",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(unique=True)),
                ("name", models.CharField(max_length=120)),
            ],
            options={"ordering": ["date"]},
        ),
    ]
