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


class BackupConfiguration(models.Model):
    """Singleton model configuring automated GFS database backups and storage targets."""
    STORAGE_CHOICES = [
        ('LOCAL', 'Local Container Volume (/backups)'),
        ('S3', 'Amazon S3 / S3-Compatible Object Storage'),
        ('CIFS', 'CIFS / SMB Windows Network Share'),
        ('NFS', 'Direct Userspace NFS Export'),
    ]

    WEEKDAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]

    # Master Schedule & GFS Retention
    is_enabled = models.BooleanField(default=False, help_text="Enable scheduled automated backups.")
    backup_time = models.CharField(max_length=5, default="02:00", help_text="UTC time of daily execution (HH:MM in 24hr format).")
    weekly_day = models.IntegerField(choices=WEEKDAY_CHOICES, default=6, help_text="Day of the week for weekly promotion (default: Sunday).")
    monthly_day = models.PositiveSmallIntegerField(default=1, help_text="Day of the month (1-28) for monthly promotion.")
    keep_daily = models.PositiveIntegerField(default=7, help_text="Number of daily backups to retain.")
    keep_weekly = models.PositiveIntegerField(default=4, help_text="Number of weekly backups to retain.")
    keep_monthly = models.PositiveIntegerField(default=3, help_text="Number of monthly backups to retain.")
    preserve_config_on_restore = models.BooleanField(
        default=True,
        help_text="Preserve active backup schedule and storage credentials when restoring an older database snapshot."
    )

    # Storage Backend Target
    storage_type = models.CharField(max_length=10, choices=STORAGE_CHOICES, default='LOCAL')
    local_path = models.CharField(max_length=255, default="/backups", help_text="Local directory path inside the container.")

    # S3 Settings
    s3_endpoint_url = models.CharField(max_length=255, blank=True, null=True, help_text="Optional custom endpoint (e.g., https://minio.local or Cloudflare R2).")
    s3_bucket = models.CharField(max_length=100, blank=True, default='')
    s3_region = models.CharField(max_length=50, blank=True, default='us-east-1')
    s3_access_key = models.CharField(max_length=255, blank=True, default='')
    s3_secret_key = models.CharField(max_length=255, blank=True, default='')
    s3_prefix = models.CharField(max_length=100, blank=True, default='beveragelab/')

    # CIFS / SMB Settings
    cifs_server = models.CharField(max_length=255, blank=True, default='', help_text="Hostname or IP address of SMB server.")
    cifs_share = models.CharField(max_length=100, blank=True, default='', help_text="Name of the SMB share.")
    cifs_subpath = models.CharField(max_length=255, blank=True, default='', help_text="Subfolder within the share.")
    cifs_username = models.CharField(max_length=100, blank=True, default='')
    cifs_password = models.CharField(max_length=255, blank=True, default='')
    cifs_domain = models.CharField(max_length=100, blank=True, default='')

    # Direct Userspace NFS Settings
    nfs_server = models.CharField(max_length=255, blank=True, default='', help_text="Hostname or IP of NFS server.")
    nfs_export = models.CharField(max_length=255, blank=True, default='', help_text="Export path (e.g. /volume1/backups).")
    nfs_subpath = models.CharField(max_length=255, blank=True, default='', help_text="Subfolder within export.")

    # Security & Alerts
    encryption_passphrase = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Optional passphrase to encrypt backups with AES-256-GCM before transmission/storage."
    )
    webhook_url = models.URLField(
        blank=True,
        default='',
        help_text="Webhook URL (Discord, Slack, Gotify, ntfy) to notify if scheduled backups fail."
    )

    # Runtime Telemetry
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=20, blank=True, default='')
    last_error = models.TextField(blank=True, default='')

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_config(cls):
        config, created = cls.objects.get_or_create(pk=1)
        return config

    class Meta:
        verbose_name_plural = "Backup Configurations"


class BackupRecord(models.Model):
    """Catalog of all generated database backups and storage locations."""
    TIER_CHOICES = [
        ('MANUAL', 'Manual'),
        ('DAILY', 'Daily'),
        ('WEEKLY', 'Weekly'),
        ('MONTHLY', 'Monthly'),
    ]

    STATUS_CHOICES = [
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
    ]

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    filename = models.CharField(max_length=255, db_index=True)
    tier = models.CharField(max_length=10, choices=TIER_CHOICES, default='MANUAL')
    storage_type = models.CharField(max_length=10, choices=BackupConfiguration.STORAGE_CHOICES, default='LOCAL')
    file_size = models.BigIntegerField(default=0, help_text="File size in bytes.")
    is_encrypted = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='SUCCESS')
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.filename} ({self.tier} - {self.storage_type})"

