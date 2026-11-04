import uuid
from datetime import date
from typing import List, Optional
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

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


class QuickDrinkCacheConfiguration(models.Model):
    """Singleton model configuring automated nightly Quick Drink cache pre-generation."""
    MODE_CHOICES = [
        ('EXPERIMENTAL', 'Experimental Mode Only'),
        ('STANDARD', 'Standard Mode Only'),
        ('BOTH', 'Both (Experimental First, Then Standard)'),
    ]

    is_enabled = models.BooleanField(default=True, help_text="Enable scheduled nightly Quick Drink cache replenishment.")
    schedule_time = models.CharField(max_length=5, default="02:00", help_text="UTC time of daily execution (HH:MM in 24hr format).")
    cache_modes = models.CharField(max_length=20, choices=MODE_CHOICES, default='BOTH')
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=20, blank=True, default='')
    last_summary = models.TextField(blank=True, default='')

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_config(cls):
        config, created = cls.objects.get_or_create(pk=1)
        return config

    class Meta:
        verbose_name_plural = "Quick Drink Cache Configurations"


MONTH_ABBRS = {
    1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
    7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec',
}

DEFAULT_HOLIDAY_THEMES = [
    {
        'name': 'Spooky Synthesis',
        'slug': 'spooky-synthesis',
        'start_month': 10,
        'start_day': 1,
        'end_month': 11,
        'end_day': 1,
        'icon_class': 'bi-moon-stars-fill',
        'accent_color': '#a855f7',
        'target_pool_size': 15,
        'flavor_directives': (
            'Select dark, brooding berries (Blackberry, Wild Grape, Cherry) contrasted with sharp green '
            'citrus (Kiwi, Lime) or smoky caramelized accents (Toasted Marshmallow, Spiced Brown Sugar). '
            'Give the recipe an eerie, gothic, or Halloween laboratory name.'
        ),
    },
    {
        'name': 'Autumn Harvest',
        'slug': 'autumn-harvest',
        'start_month': 11,
        'start_day': 2,
        'end_month': 11,
        'end_day': 30,
        'icon_class': 'bi-tree-fill',
        'accent_color': '#f97316',
        'target_pool_size': 15,
        'flavor_directives': (
            'Select warm, comforting autumn reagents such as Cinnamon, Spiced Brown Sugar, Desert Pear, '
            'Toasted Marshmallow, Vanilla, and rich orchard fruits. '
            'Give the recipe a cozy, harvest, or hearth-inspired laboratory name.'
        ),
    },
    {
        'name': 'Winter Wonderland',
        'slug': 'winter-wonderland',
        'start_month': 12,
        'start_day': 1,
        'end_month': 1,
        'end_day': 5,
        'icon_class': 'bi-snow2',
        'accent_color': '#38bdf8',
        'target_pool_size': 15,
        'flavor_directives': (
            'Select festive winter reagents such as Peppermint, Frosted Mint, Chocolate Fudge, Cherry, '
            'Cinnamon, Orange, and creamy Vanilla. '
            'Give the recipe a festive winter, frost, or holiday laboratory name.'
        ),
    },
    {
        'name': "Valentine's Reserve",
        'slug': 'valentines-reserve',
        'start_month': 2,
        'start_day': 1,
        'end_month': 2,
        'end_day': 15,
        'icon_class': 'bi-suit-heart-fill',
        'accent_color': '#f43f5e',
        'target_pool_size': 15,
        'flavor_directives': (
            'Select romantic crimson fruits (Cherry, Strawberry, Raspberry) layered with indulgent '
            'Chocolate Fudge, Toasted Marshmallow, or creamy Vanilla. '
            'Give the recipe an elegant, romantic, ruby-toned laboratory name.'
        ),
    },
    {
        'name': 'Emerald Alchemy',
        'slug': 'emerald-alchemy',
        'start_month': 3,
        'start_day': 1,
        'end_month': 3,
        'end_day': 20,
        'icon_class': 'bi-flower1',
        'accent_color': '#10b981',
        'target_pool_size': 15,
        'flavor_directives': (
            'Select vibrant green and botanical reagents such as Frosted Mint, Peppermint, Kiwi, Lime, '
            'Green Apple, and creamy Vanilla. '
            'Give the recipe an emerald, shamrock, or botanical laboratory name.'
        ),
    },
    {
        'name': 'Summer Solstice',
        'slug': 'summer-solstice',
        'start_month': 5,
        'start_day': 15,
        'end_month': 8,
        'end_day': 31,
        'icon_class': 'bi-brightness-high-fill',
        'accent_color': '#facc15',
        'target_pool_size': 15,
        'flavor_directives': (
            'Select sun-drenched, refreshing reagents such as Watermelon, Pineapple, Guava, Coconut, '
            'Strawberry, Lemon, and Lime. '
            'Give the recipe a radiant summer, solar, or coastal laboratory name.'
        ),
    },
]


class HolidayTheme(models.Model):
    """Customizable seasonal or holiday theme for Quick Drinks & Nightly Cache."""
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True, db_index=True)
    start_month = models.IntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(12)])
    start_day = models.IntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(31)])
    end_month = models.IntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(12)])
    end_day = models.IntegerField(default=31, validators=[MinValueValidator(1), MaxValueValidator(31)])
    flavor_directives = models.TextField(
        blank=True,
        default='',
        help_text="Positive mixology instructions guiding ingredient selection and thematic naming."
    )
    icon_class = models.CharField(max_length=50, default="bi-stars")
    accent_color = models.CharField(max_length=30, default="#00f2fe")
    is_enabled = models.BooleanField(default=True, db_index=True)
    force_active = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Force this holiday active in Quick Drinks and Nightly Cache regardless of current date."
    )
    target_pool_size = models.IntegerField(
        default=15,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
        help_text="Target number of cached recipes per lab for this holiday (default 15)."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_month', 'start_day', 'name']
        verbose_name = "Holiday Theme"
        verbose_name_plural = "Holiday Themes"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or f"holiday-{uuid.uuid4().hex[:6]}"
            slug_candidate = base_slug
            counter = 1
            while HolidayTheme.objects.filter(slug=slug_candidate).exclude(pk=self.pk).exists():
                counter += 1
                slug_candidate = f"{base_slug}-{counter}"
            self.slug = slug_candidate
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.date_window_display})"

    @property
    def date_window_display(self) -> str:
        sm = MONTH_ABBRS.get(self.start_month, str(self.start_month))
        em = MONTH_ABBRS.get(self.end_month, str(self.end_month))
        return f"{sm} {self.start_day} – {em} {self.end_day}"

    def is_currently_active(self, check_date: Optional[date] = None) -> bool:
        """Return True if enabled and either forced active or check_date falls within the start..end window."""
        if not self.is_enabled:
            return False
        if self.force_active:
            return True
        d = check_date or timezone.now().date()
        cur = (d.month, d.day)
        start = (self.start_month, self.start_day)
        end = (self.end_month, self.end_day)
        if start <= end:
            return start <= cur <= end
        # Year-boundary wrap (e.g. Dec 1 to Jan 5)
        return cur >= start or cur <= end

    @classmethod
    def ensure_default_themes(cls) -> None:
        """Seed the default holiday calendar if the table is completely empty."""
        if cls.objects.exists():
            return
        for item in DEFAULT_HOLIDAY_THEMES:
            cls.objects.get_or_create(slug=item['slug'], defaults=item)

    @classmethod
    def get_active_themes(cls, check_date: Optional[date] = None) -> List['HolidayTheme']:
        """Return all currently active HolidayTheme instances."""
        themes = list(cls.objects.filter(is_enabled=True))
        return [t for t in themes if t.is_currently_active(check_date)]



