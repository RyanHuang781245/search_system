from django.urls import include, path
from django.views.generic import TemplateView


urlpatterns = [
    path("", TemplateView.as_view(template_name="index.html"), name="dashboard"),
    path("api/documents/", include("apps.documents.urls")),
]
