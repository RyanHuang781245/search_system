import os
import json
import re
import requests
from json import JSONDecodeError
from functools import lru_cache
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Union, Iterator
from dotenv import load_dotenv

load_dotenv()

# Use the new environment variable names for Ollama
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost")
OLLAMA_PORT = int(os.getenv("OLLAMA_PORT", "10000"))
OLLAMA_BASE_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
OLLAMA_INFERENCE_MODEL = os.getenv("OLLAMA_INFERENCE_MODEL", "qwen2.5:3b")
# Use OLLAMA_VECTOR_DIMENSION for this provider
VECTOR_DIMENSION = int(os.getenv("OLLAMA_VECTOR_DIMENSION", "768"))

# Define data models (same as in OpenAI processor)
class Single(BaseModel):
    """
    Represents a single relationship between two nodes in a knowledge graph.
    """
    node: str
    target_node: str
    relationship: str

class GraphComponents(BaseModel):
    """
    Represents a collection of relationships in a knowledge graph.
    """
    graph: list[Single]


def normalize_graph_entry(entry: Dict[str, Any]) -> Optional[Single]:
    """
    Normalize common malformed keys from Ollama output and keep only valid graph entries.
    """
    if not isinstance(entry, dict):
        return None

    normalized = {}
    for key, value in entry.items():
        if not isinstance(key, str):
            continue
        compact_key = re.sub(r"\s+", "", key).lower()
        if compact_key == "node":
            normalized["node"] = value
        elif compact_key in {"targetnode", "target_node", "target_mode"}:
            normalized["target_node"] = value
        elif compact_key == "relationship":
            normalized["relationship"] = value

    node = normalized.get("node")
    target_node = normalized.get("target_node")
    relationship = normalized.get("relationship")

    if not all(isinstance(v, str) for v in [node, target_node, relationship]):
        return None

    node = node.strip()
    target_node = target_node.strip()
    relationship = relationship.strip().upper()

    if not node or not target_node or not relationship:
        return None

    return Single(node=node, target_node=target_node, relationship=relationship)


def salvage_graph_components(content: str) -> GraphComponents:
    """
    Recover valid relationship objects from partially broken Ollama JSON output.
    """
    entries: List[Single] = []
    seen = set()
    candidates = []
    depth = 0
    stack = []
    in_string = False
    escaped = False

    for index, char in enumerate(content):
        if escaped:
            escaped = False
            continue

        if char == "\\" and in_string:
            escaped = True
            continue

        if char == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == "{":
            stack.append(index)
            depth += 1
        elif char == "}":
            if depth > 0:
                depth -= 1
                if stack:
                    start = stack.pop()
                    candidates.append(content[start:index + 1])

    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except JSONDecodeError:
            continue

        single = normalize_graph_entry(obj)
        if single is None:
            continue

        dedupe_key = (single.node, single.target_node, single.relationship)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        entries.append(single)

    return GraphComponents(graph=entries)


def extract_json_object(content: str) -> str:
    """
    Extract the first valid JSON object from a model response.
    Ollama models sometimes wrap JSON with explanatory text or code fences.
    """
    content = content.strip()
    if not content:
        raise ValueError("Empty response from Ollama")

    if content.startswith("```"):
        lines = content.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
            content = "\n".join(lines[1:-1]).strip()
            if content.lower().startswith("json"):
                content = content[4:].strip()

    decoder = json.JSONDecoder()
    for index, char in enumerate(content):
        if char != "{":
            continue
        try:
            _, end = decoder.raw_decode(content[index:])
            return content[index:index + end]
        except JSONDecodeError:
            continue

    raise ValueError("No valid JSON object found in Ollama response")

@lru_cache(maxsize=128)
def cached_ollama_call(prompt: str, model: Optional[str] = None) -> str:
    """
    Cached version of Ollama API call to avoid redundant calls.
    """
    if model is None:
        model = OLLAMA_INFERENCE_MODEL

    payload = {
        "model": model,
        "format": "json",
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a precise meeting-minutes graph extractor. Extract action items, owners, dates, "
                    "products, regions, specifications, and explicit discussion links from the text. "
                    "Prefer ActionItem-centric relationships over generic entity pairs. "
                    "Format the result as a JSON object with this exact structure:\n"
                    '{ "graph": [ {"node": "Person/Entity", "target_node": "Related Entity", "relationship": "Type of Relationship"}, ... ] }\n'
                    "Use concise relationship labels such as ASSIGNED_TO, DUE_ON, ABOUT, MENTIONS, "
                    "RELATED_TO, HAS_SPEC, and TARGETS_REGION when appropriate. "
                    "Every value for node, target_node, and relationship must be a plain JSON string. "
                    "Never use numbers, null, extra keys, comments, or duplicate keys. "
                    "Preserve original Chinese and English terms. Extract only relationships supported by the text. "
                    "Return only valid JSON. Do not add markdown, explanations, or any text before or after the JSON."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    }

    try:
        response = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        response.raise_for_status()
        result = response.json()
        if 'message' in result and 'content' in result['message']:
            return result['message']['content']
        else:
            print(f"Warning: Unexpected API response format: {result}")
            return """{"graph": []}"""
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to Ollama API at {OLLAMA_BASE_URL}")
        return """{"graph": []}"""
    except Exception as e:
        print(f"Error in Ollama API call: {str(e)}")
        return """{"graph": []}"""

def ollama_llm_parser(prompt: str) -> GraphComponents:
    """
    Parse text into graph components using Ollama.
    """
    content = cached_ollama_call(prompt)
    try:
        return GraphComponents.model_validate_json(content)
    except Exception as e:
        try:
            extracted_json = extract_json_object(content)
            return GraphComponents.model_validate_json(extracted_json)
        except Exception as fallback_error:
            salvaged = salvage_graph_components(content)
            if salvaged.graph:
                print(
                    f"Warning: recovered {len(salvaged.graph)} relationships from malformed Ollama JSON."
                )
                return salvaged
            print(f"Error parsing JSON: {str(e)}")
            print(f"Raw Ollama response: {content}")
            print(f"Fallback JSON extraction failed: {str(fallback_error)}")
            return GraphComponents(graph=[])

def ollama_embeddings(text: str) -> List[float]:
    """
    Generate embeddings for a single text string using Ollama.
    """
    try:
        payload = {
            "model": OLLAMA_EMBEDDING_MODEL,
            "prompt": text
        }
        response = requests.post(f"{OLLAMA_BASE_URL}/api/embeddings", json=payload)
        response.raise_for_status()
        result = response.json()
        return result.get("embedding", [0] * VECTOR_DIMENSION)
    except Exception as e:
        print(f"Error generating embedding: {str(e)}")
        return [0] * VECTOR_DIMENSION

def ollama_embeddings_batch(texts: List[str], batch_size: int = 20) -> List[List[float]]:
    """
    Get embeddings for a list of texts in batches.
    """
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        batch_embeddings = []
        try:
            for text in batch:
                embedding = ollama_embeddings(text)
                batch_embeddings.append(embedding)
            all_embeddings.extend(batch_embeddings)
            print(f"Processed batch {i//batch_size + 1}/{(len(texts) + batch_size - 1)//batch_size}")
        except Exception as e:
            print(f"Error in batch {i//batch_size + 1}: {str(e)}")
            all_embeddings.extend([[0] * VECTOR_DIMENSION] * len(batch))
    return all_embeddings

def graphrag_query(graph_context: Dict[str, List[str]], user_query: str,
                   model: Optional[str] = None, stream: bool = True) -> Union[str, Iterator[str]]:
    """
    Run RAG with the graph context using Ollama.
    """
    if model is None:
        model = OLLAMA_INFERENCE_MODEL

    nodes_str = ", ".join(graph_context["nodes"])
    edges_str = "; ".join(graph_context["edges"])
    prompt = (
        f"You are an intelligent assistant with access to the following knowledge graph:\n\n"
        f"Nodes: {nodes_str}\n\n"
        f"Edges: {edges_str}\n\n"
        f"Using this graph, answer the following question:\n\n"
        f'User Query: "{user_query}"'
    )

    try:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Provide the answer for the following question:"},
                {"role": "user", "content": prompt}
            ],
            "stream": stream,
        }
        if stream:
            response = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, stream=True)
        else:
            response = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        response.raise_for_status()

        if stream:
            def response_generator():
                for chunk in response.iter_lines():
                    if chunk:
                        try:
                            json_chunk = json.loads(chunk.decode('utf-8'))
                            if 'message' in json_chunk and 'content' in json_chunk['message']:
                                content = json_chunk['message']['content']
                                if content.strip():
                                    yield content
                        except json.JSONDecodeError:
                            raw_text = chunk.decode('utf-8')
                            if raw_text.strip():
                                yield raw_text
            return response_generator()
        else:
            result = response.json()
            if 'message' in result and 'content' in result['message']:
                return result['message']['content']
            else:
                return f"Error: Unexpected API response format: {result}"
    except Exception as e:
        error_msg = f"Error querying LLM: {str(e)}"
        if stream:
            def error_generator():
                yield error_msg
            return error_generator()
        else:
            return error_msg
