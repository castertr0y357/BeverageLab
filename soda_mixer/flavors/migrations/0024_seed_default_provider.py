from django.db import migrations


def seed_default_provider(apps, schema_editor):
    LLMProvider = apps.get_model('flavors', 'LLMProvider')
    SystemConfiguration = apps.get_model('flavors', 'SystemConfiguration')

    # Seed Ollama provider
    ollama_provider, created = LLMProvider.objects.get_or_create(
        provider_type='OLLAMA',
        defaults={
            'name': 'Ollama',
            'base_url': 'http://localhost:11434',
            'default_model': 'gemma4:12b',
            'is_enabled': True,
            'enable_keep_warm': True,
            'enable_thinking': False,
            'thinking_effort': 'medium',
        }
    )

    # Associate with SystemConfiguration if not already set
    config, created = SystemConfiguration.objects.get_or_create(pk=1)
    if not config.default_llm_provider:
        config.default_llm_provider = ollama_provider
        config.save()


def remove_default_provider(apps, schema_editor):
    LLMProvider = apps.get_model('flavors', 'LLMProvider')
    SystemConfiguration = apps.get_model('flavors', 'SystemConfiguration')

    config = SystemConfiguration.objects.filter(pk=1).first()
    if config and config.default_llm_provider:
        config.default_llm_provider = None
        config.save()

    LLMProvider.objects.filter(provider_type='OLLAMA', name='Ollama').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('flavors', '0023_llmprovider_enable_keep_warm_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_default_provider, reverse_code=remove_default_provider),
    ]
