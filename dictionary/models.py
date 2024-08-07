from django.db import models
from storages.backends.gcloud import GoogleCloudStorage


class ProficiencyLevel(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to="category_images", null=True, blank=True)

    def __str__(self):
        return self.name


class Word(models.Model):
    text = models.CharField(max_length=255)
    translation = models.CharField(max_length=255)
    definition = models.TextField(blank=True)
    audio = models.FileField(upload_to="media_journal_bucket/dictionary/audios", null=True, blank=True, storage=GoogleCloudStorage())
    image = models.FileField(upload_to="media_journal_bucket/dictionary/images", null=True, blank=True, storage=GoogleCloudStorage())
    examples = models.JSONField(null=True, blank=True)
    level = models.ForeignKey(
        ProficiencyLevel, null=True, blank=True, on_delete=models.SET_NULL
    )
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL
    )

    def __str__(self):
        return f"{self.text} - {self.translation}"
