from pathlib import Path
import os

from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-document-mvp-secret-key")
DEBUG = os.getenv("DJANGO_DEBUG", "True")
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.documents",
    "apps.meetings",
    "apps.graph",
    "apps.search.apps.SearchConfig",
    "apps.vector",
    "apps.graphrag",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {}

LANGUAGE_CODE = "zh-hant"
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "Asia/Taipei")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_AUTHENTICATION_CLASSES": [],
}

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "document_retrieval_system")

NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "meeting_items")
QDRANT_VECTOR_DIMENSION = int(os.getenv("QDRANT_VECTOR_DIMENSION", "768"))

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost")
OLLAMA_PORT = int(os.getenv("OLLAMA_PORT", "10000"))
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
OLLAMA_INFERENCE_MODEL = os.getenv("OLLAMA_INFERENCE_MODEL", "qwen2.5:3b")
GRAPHRAG_QUERY_ROUTER_LLM_ENABLED = os.getenv("GRAPHRAG_QUERY_ROUTER_LLM_ENABLED", "1").lower() in {"1", "true", "yes", "on"}
GRAPHRAG_QUERY_ROUTER_LLM_TIMEOUT = int(os.getenv("GRAPHRAG_QUERY_ROUTER_LLM_TIMEOUT", "8"))
GRAPHRAG_EVIDENCE_SELECTOR_ENABLED = os.getenv("GRAPHRAG_EVIDENCE_SELECTOR_ENABLED", "1").lower() in {"1", "true", "yes", "on"}
GRAPHRAG_EVIDENCE_SELECTOR_TIMEOUT = int(os.getenv("GRAPHRAG_EVIDENCE_SELECTOR_TIMEOUT", "20"))
GRAPH_INTENT_LLM_TIMEOUT = int(os.getenv("GRAPH_INTENT_LLM_TIMEOUT", "12"))
TEXT2CYPHER_LLM_TIMEOUT = int(os.getenv("TEXT2CYPHER_LLM_TIMEOUT", "45"))
TEXT2CYPHER_MAX_LIMIT = int(os.getenv("TEXT2CYPHER_MAX_LIMIT", "50"))
TEXT2CYPHER_ENABLE_NODE_EXPANSION = os.getenv("TEXT2CYPHER_ENABLE_NODE_EXPANSION", "false").lower() == "true"
TEXT2CYPHER_EXPANSION_PER_NODE_LIMIT = int(os.getenv("TEXT2CYPHER_EXPANSION_PER_NODE_LIMIT", "10"))

KEYWORD_LLM_ENABLED = os.getenv("KEYWORD_LLM_ENABLED", "True").lower() == "true"
KEYWORD_LLM_TIMEOUT = int(os.getenv("KEYWORD_LLM_TIMEOUT", "12"))
KEYWORD_LLM_MAX_INPUT_CHARS = int(os.getenv("KEYWORD_LLM_MAX_INPUT_CHARS", "1800"))
KEYWORD_EMBEDDING_RERANK_ENABLED = os.getenv("KEYWORD_EMBEDDING_RERANK_ENABLED", "True").lower() == "true"
KEYWORD_EMBEDDING_RERANK_LIMIT = int(os.getenv("KEYWORD_EMBEDDING_RERANK_LIMIT", "18"))
KEYWORD_EMBEDDING_MAX_INPUT_CHARS = int(os.getenv("KEYWORD_EMBEDDING_MAX_INPUT_CHARS", "1800"))
KEYWORD_EMBEDDING_TIMEOUT = int(os.getenv("KEYWORD_EMBEDDING_TIMEOUT", "10"))

UPLOAD_ROOT = BASE_DIR / "uploads"
MAX_UPLOAD_SIZE = 50 * 1024 * 1024
ALLOWED_FILE_EXTENSIONS = [".pdf", ".docx"]

UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
