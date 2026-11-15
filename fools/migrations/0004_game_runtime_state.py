# Generated manually for Durak runtime state (phase, attacker/defender).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fools", "0003_turn_move"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="runtime_state",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
