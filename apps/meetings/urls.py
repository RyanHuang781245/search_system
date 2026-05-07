from django.urls import path

from .views import MeetingItemsListView, MeetingMinutesDetailView, MeetingMinutesListView


urlpatterns = [
    path("meeting-minutes/", MeetingMinutesListView.as_view(), name="meeting-minutes-list"),
    path("meeting-minutes/<str:meeting_id>/", MeetingMinutesDetailView.as_view(), name="meeting-minutes-detail"),
    path("meeting-items/", MeetingItemsListView.as_view(), name="meeting-items-list"),
]
