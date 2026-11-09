from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fools", "0006_lobbysettings_fill_with_bots"),
    ]

    operations = [
        migrations.AddField(
            model_name="lobbysettings",
            name="share_hand_signals",
            field=models.BooleanField(default=True),
        ),
    ]
