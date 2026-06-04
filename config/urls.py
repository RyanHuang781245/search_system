from django.urls import include, path
from django.views.generic import RedirectView, TemplateView


urlpatterns = [
    path("", RedirectView.as_view(pattern_name="documents-page", permanent=False)),
    path(
        "documents/",
        TemplateView.as_view(template_name="documents.html", extra_context={"active_page": "documents"}),
        name="documents-page",
    ),
    path(
        "meetings/",
        TemplateView.as_view(template_name="meetings.html", extra_context={"active_page": "meetings"}),
        name="meetings-page",
    ),
    path(
        "search/",
        TemplateView.as_view(template_name="search.html", extra_context={"active_page": "search"}),
        name="search-page",
    ),
    path(
        "graphrag/",
        TemplateView.as_view(template_name="graphrag.html", extra_context={"active_page": "graphrag"}),
        name="graphrag-page",
    ),
    path("api/documents/", include("apps.documents.urls")),
    path("api/", include("apps.meetings.urls")),
    path("api/", include("apps.graph.urls")),
    path("api/", include("apps.search.urls")),
    path("api/", include("apps.vector.urls")),
    path("api/", include("apps.graphrag.urls")),
]
