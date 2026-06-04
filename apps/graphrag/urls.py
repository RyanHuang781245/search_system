from django.urls import path

from .views import GraphRagAskView


urlpatterns = [
    path("graphrag/ask/", GraphRagAskView.as_view(), name="graphrag-ask"),
]
