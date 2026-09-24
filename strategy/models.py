from django.db import models

# Create your models here.

class PickList_Data(models.Model):
    event = models.CharField(max_length=16, default="testing")
    no_pick = models.JSONField(default=list)
    first_pick = models.JSONField(default=list)
    second_pick = models.JSONField(default=list)
    third_pick = models.JSONField(default=list)
    dn_pick = models.JSONField(default=list)

    # Per-team flags, held as flat lists of team numbers rather than as part of
    # the column lists above. Keeping them separate means a flag survives a team
    # being dragged between columns, and leaves the five-column payload that
    # picklist_submit validates unchanged.
    starred = models.JSONField(default=list)   # floated to the top of its column
    struck = models.JSONField(default=list)    # drafted by someone else; kept visible
