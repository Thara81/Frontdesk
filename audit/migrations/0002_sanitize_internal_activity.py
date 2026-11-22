from django.db import migrations


def sanitize_internal_note_bodies(apps, schema_editor):
    TicketActivity = apps.get_model("audit", "TicketActivity")
    TicketActivity.objects.filter(action="internal_note").update(new_value="Internal note added")


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [migrations.RunPython(sanitize_internal_note_bodies, migrations.RunPython.noop)]
