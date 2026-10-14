from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """The project's user model.

    Django's documentation recommends starting every project with a custom user
    model, because swapping it in after the first migration is painful. It adds
    nothing yet except a required, unique, lower-cased email (used for password
    reset), but profile fields can now be added later with a normal migration.
    """

    email = models.EmailField("email address", unique=True)

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)
