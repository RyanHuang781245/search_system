from django.urls import path

from .views import (
    MeetingMinutesSearchView,
    RelatedItemsView,
    RelatedMeetingsView,
    SearchClickLogView,
    SearchStatsView,
)


urlpatterns = [
    path("search/meeting-minutes/", MeetingMinutesSearchView.as_view(), name="meeting-minutes-search"),
    path("search/click/", SearchClickLogView.as_view(), name="search-click-log"),
    path("search/related-meetings/<str:meeting_id>/", RelatedMeetingsView.as_view(), name="related-meetings"),
    path("search/related-items/<str:item_id>/", RelatedItemsView.as_view(), name="related-items"),
    path("search/stats/", SearchStatsView.as_view(), name="search-stats"),
]
