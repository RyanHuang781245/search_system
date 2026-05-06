from pathlib import Path

from django.conf import settings
from rest_framework.exceptions import ValidationError


DANGEROUS_EXTENSIONS = {".exe", ".bat", ".sh", ".cmd", ".msi", ".com", ".scr"}


def validate_file_extension(file_obj):
    extension = Path(file_obj.name).suffix.lower()
    if extension in DANGEROUS_EXTENSIONS:
        raise ValidationError("Dangerous file types are not allowed.")
    if extension not in settings.ALLOWED_FILE_EXTENSIONS:
        raise ValidationError("Only PDF and DOCX files are allowed.")
    return extension


def validate_file_size(file_obj):
    if file_obj.size > settings.MAX_UPLOAD_SIZE:
        raise ValidationError("File size exceeds the 50MB limit.")


def validate_file_not_empty(file_obj):
    if file_obj.size <= 0:
        raise ValidationError("Empty files are not allowed.")
