from django.db import models
from django.urls import reverse
from django.contrib.auth import get_user_model

import misaka

from groups.models import Group

User = get_user_model()


class Post(models.Model):
    user = models.ForeignKey(User, related_name="posts", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    message = models.TextField()
    message_html = models.TextField(editable=False, blank=True, default="")

    group = models.ForeignKey(
        Group,
        related_name="posts",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    def __str__(self):
        # Avoid returning huge strings in admin/logs
        return self.message[:50]

    def save(self, *args, **kwargs):
        self.message_html = misaka.html(self.message)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse(
            "posts:single",
            kwargs={"username": self.user.username, "pk": self.pk},
        )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "message"], name="unique_user_message")
        ]