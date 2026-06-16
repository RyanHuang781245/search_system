from django.urls import path

from .views import GraphRagAskView, GraphRagEvalRunView, GraphRagEvalSaveView, GraphRagEvalSeedView


urlpatterns = [
    path("graphrag/ask/", GraphRagAskView.as_view(), name="graphrag-ask"),
    path("graphrag/eval/seed/", GraphRagEvalSeedView.as_view(), name="graphrag-eval-seed"),
    path("graphrag/eval/run/", GraphRagEvalRunView.as_view(), name="graphrag-eval-run"),
    path("graphrag/eval/save/", GraphRagEvalSaveView.as_view(), name="graphrag-eval-save"),
]
