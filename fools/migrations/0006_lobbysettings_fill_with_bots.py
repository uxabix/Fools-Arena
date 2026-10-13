from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fools", "0005_rename_game_relation_to_fools"),
    ]

    operations = [
        migrations.AddField(
            model_name="lobbysettings",
            name="fill_with_bots",
            field=models.BooleanField(default=False),
        ),
    ]
