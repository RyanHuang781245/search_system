from django.urls import path

from apps.meetings.views import ParseMeetingMinutesView

from .views import (
    DocumentDeleteView,
    DocumentDetailView,
    DocumentDetailDeleteView,
    DocumentListView,
    DocumentUploadView,
)


urlpatterns = [
    path("upload/", DocumentUploadView.as_view(), name="document-upload"),
    path("", DocumentListView.as_view(), name="document-list"),
    path(
        "<str:document_id>/parse-meeting-minutes/",
        ParseMeetingMinutesView.as_view(),
        name="document-parse-meeting-minutes",
    ),
    path("<str:document_id>/", DocumentDetailDeleteView.as_view(), name="document-detail-delete"),
]
