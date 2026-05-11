from django.urls import path

from .views import MeetingMinutesSearchView, SearchClickLogView


urlpatterns = [
    path("search/meeting-minutes/", MeetingMinutesSearchView.as_view(), name="meeting-minutes-search"),
    path("search/click/", SearchClickLogView.as_view(), name="search-click-log"),
]
