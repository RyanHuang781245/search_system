from django.urls import path

from .views import VectorReindexView, VectorSearchView


urlpatterns = [
    path("vector/reindex/", VectorReindexView.as_view(), name="vector-reindex"),
    path("vector/search/", VectorSearchView.as_view(), name="vector-search"),
]
