import uuid
from django.db import models

class LLMProvider(models.Model):
    """Configuration for an LLM provider (Cloud or Local)."""
    PROVIDER_CHOICES = [
        ('OPENAI', 'ChatGPT (OpenAI)'),
        ('CLAUDE', 'Claude (Anthropic)'),
        ('GEMINI', 'Gemini (Google)'),
        ('OLLAMA', 'Ollama (Local)'),
        ('OPENWEBUI', 'OpenWebUI'),
        ('ANYTHINGLLM', 'AnythingLLM'),
        ('CUSTOM', 'Custom OpenAI-Compatible'),
    ]
    name = models.CharField(max_length=100)
    provider_type = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    api_key = models.CharField(max_length=255, blank=True, null=True)
    base_url = models.URLField(blank=True, null=True, help_text="e.g., http://localhost:11434")
    default_model = models.CharField(max_length=100, blank=True, null=True, help_text="e.g., gpt-4o or mistral")
    is_enabled = models.BooleanField(default=False)
    THINKING_EFFORT_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]
    enable_thinking = models.BooleanField(
        default=False,
        help_text="Enable internal model thinking/reasoning if supported by the provider/model."
    )
    thinking_effort = models.CharField(
        max_length=10,
        choices=THINKING_EFFORT_CHOICES,
        default='medium',
        help_text="Thinking/reasoning effort level (low, medium, high) if supported by provider/model."
    )
    enable_keep_warm = models.BooleanField(
        default=False,
        help_text="Enable background periodic keep-alive tasks to maintain model in VRAM."
    )
    
    def __str__(self):
        return f"{self.name} ({self.get_provider_type_display()})"


class SystemConfiguration(models.Model):
    """Singleton model for laboratory-wide settings and API credentials."""
    mealie_url = models.URLField(
        blank=True, 
        help_text="The base URL of your Mealie instance (e.g., https://mealie.local)"
    )
    mealie_api_key = models.CharField(
        max_length=255, 
        blank=True, 
        help_text="Long-lived API token generated in Mealie User Settings"
    )
    default_llm_provider = models.ForeignKey(
        LLMProvider,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='default_for_config'
    )
    
    def save(self, *args, **kwargs):
        # Enforce singleton pattern: only one config object should exist
        self.pk = 1
        super().save(*args, **kwargs)
        
    @classmethod
    def get_config(cls):
        config, created = cls.objects.get_or_create(pk=1)
        return config

    class Meta:
        verbose_name_plural = "System Configurations"


class BackgroundExecutionTask(models.Model):
    """Tracks asynchronous execution progress and status of laboratory tasks."""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RUNNING', 'Running'),
        ('SUCCESS', 'Success'),
        ('FAILURE', 'Failure'),
    ]
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    progress = models.IntegerField(default=0)  # 0 to 100
    error_message = models.TextField(blank=True, null=True)
    result_data = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.task_name} ({self.status} - {self.progress}%)"
