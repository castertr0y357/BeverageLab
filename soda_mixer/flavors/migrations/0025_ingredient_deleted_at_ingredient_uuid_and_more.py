import uuid
from django.db import migrations, models


def gen_uuids(apps, schema_editor):
    for model_name in ['Ingredient', 'Recipe', 'MixHistory', 'RecipeCategory']:
        Model = apps.get_model('flavors', model_name)
        for obj in Model.objects.all():
            obj.uuid = uuid.uuid4()
            obj.save(update_fields=['uuid'])


class Migration(migrations.Migration):

    dependencies = [
        ('flavors', '0024_seed_default_provider'),
    ]

    operations = [
        # 1. Add deleted_at fields
        migrations.AddField(
            model_name='ingredient',
            name='deleted_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='mixhistory',
            name='deleted_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='recipe',
            name='deleted_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='recipecategory',
            name='deleted_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),

        # 2. Add uuid fields as nullable, non-unique
        migrations.AddField(
            model_name='ingredient',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, null=True),
        ),
        migrations.AddField(
            model_name='mixhistory',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, null=True),
        ),
        migrations.AddField(
            model_name='recipe',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, null=True),
        ),
        migrations.AddField(
            model_name='recipecategory',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, null=True),
        ),

        # 3. Populate unique UUIDs for existing entries
        migrations.RunPython(gen_uuids, elidable=True),

        # 4. Alter fields to make them unique and non-nullable
        migrations.AlterField(
            model_name='ingredient',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name='mixhistory',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name='recipe',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name='recipecategory',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
