from django.urls import path

from .views import GraphBuildView, GraphSearchView, KeywordExtractView, RelatedKeywordView


urlpatterns = [
    path("graph/build/", GraphBuildView.as_view(), name="graph-build"),
    path("graph/keywords/extract/", KeywordExtractView.as_view(), name="graph-keyword-extract"),
    path("graph/keyword/<str:keyword>/related/", RelatedKeywordView.as_view(), name="graph-keyword-related"),
    path("graph/search/", GraphSearchView.as_view(), name="graph-search"),
]
