import uuid
from django.db import migrations, models

def populate(apps,schema_editor):
    Sample=apps.get_model('observations','Sample')
    for row in Sample.objects.all().iterator():
        row.transfer_id=uuid.uuid4();row.save(update_fields=['transfer_id'])

class Migration(migrations.Migration):
    dependencies=[('observations','0006_alter_sample_video_url')]
    operations=[migrations.AddField(model_name='sample',name='transfer_id',field=models.UUIDField(null=True,editable=False)),migrations.RunPython(populate,migrations.RunPython.noop),migrations.AlterField(model_name='sample',name='transfer_id',field=models.UUIDField(default=uuid.uuid4,unique=True,editable=False))]
