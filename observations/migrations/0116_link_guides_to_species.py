"""Superseded by 0117 before it was published: it linked the identification guides to the species whose texts cite
them, which tied species named by the 2nd edition to the 3rd. Kept, empty, because the owner's database has applied it;
0117 removes the links it made."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('observations', '0115_issue_workflow')]
    operations = []
