from django.urls import path

from .views import (
    GraphBuildView,
    GraphNodeExpandView,
    GraphSearchView,
    KeywordExtractView,
    RelatedKeywordView,
    Text2CypherView,
)


urlpatterns = [
    path("graph/build/", GraphBuildView.as_view(), name="graph-build"),
    path("graph/keywords/extract/", KeywordExtractView.as_view(), name="graph-keyword-extract"),
    path("graph/keyword/<str:keyword>/related/", RelatedKeywordView.as_view(), name="graph-keyword-related"),
    path("graph/search/", GraphSearchView.as_view(), name="graph-search"),
    path("graph/text2cypher/", Text2CypherView.as_view(), name="graph-text2cypher"),
    path("graph/node/expand/", GraphNodeExpandView.as_view(), name="graph-node-expand"),
]
