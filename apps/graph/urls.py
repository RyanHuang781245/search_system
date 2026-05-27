from django.urls import path

from .views import GraphBuildView, GraphSearchView, RelatedKeywordView


urlpatterns = [
    path("graph/build/", GraphBuildView.as_view(), name="graph-build"),
    path("graph/keyword/<str:keyword>/related/", RelatedKeywordView.as_view(), name="graph-keyword-related"),
    path("graph/search/", GraphSearchView.as_view(), name="graph-search"),
]
