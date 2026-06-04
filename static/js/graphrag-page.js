const elements = {
    refreshButton: document.getElementById("refresh-button"),
    toastElement: document.getElementById("status-toast"),
    toastBody: document.getElementById("status-toast-body"),
    buildGraphButton: document.getElementById("build-graph-button"),
    reindexVectorButton: document.getElementById("reindex-vector-button"),
    vectorBatchSize: document.getElementById("vector-batch-size"),
    indexStatus: document.getElementById("index-status"),
    keywordForm: document.getElementById("keyword-form"),
    keywordText: document.getElementById("keyword-text"),
    keywordMax: document.getElementById("keyword-max"),
    keywordSubmit: document.getElementById("keyword-submit"),
    keywordResults: document.getElementById("keyword-results"),
    graphSearchForm: document.getElementById("graph-search-form"),
    graphQuery: document.getElementById("graph-query"),
    graphLimit: document.getElementById("graph-limit"),
    graphSearchSubmit: document.getElementById("graph-search-submit"),
    graphResults: document.getElementById("graph-results"),
    vectorSearchForm: document.getElementById("vector-search-form"),
    vectorQuery: document.getElementById("vector-query"),
    vectorLimit: document.getElementById("vector-limit"),
    vectorSearchSubmit: document.getElementById("vector-search-submit"),
    vectorResults: document.getElementById("vector-results"),
    askForm: document.getElementById("ask-form"),
    askQuestion: document.getElementById("ask-question"),
    askLimit: document.getElementById("ask-limit"),
    askSubmit: document.getElementById("ask-submit"),
    answerPanel: document.getElementById("answer-panel"),
    sourceCount: document.getElementById("source-count"),
    sourceList: document.getElementById("source-list"),
    warningCount: document.getElementById("warning-count"),
    warningList: document.getElementById("warning-list"),
};

const toast = new bootstrap.Toast(elements.toastElement, { delay: 2800 });

init();

function init() {
    bindEvents();
    renderKeywords([]);
    renderGraphResults({ expanded_keywords: [], results: [] });
    renderVectorResults([]);
    renderSources([]);
    renderWarnings([]);
    renderIcons();
}

function bindEvents() {
    elements.refreshButton?.addEventListener("click", () => {
        elements.indexStatus.textContent = "控制台已重新整理。";
        showToast("控制台已重新整理。", "success");
    });

    elements.buildGraphButton?.addEventListener("click", handleBuildGraph);
    elements.reindexVectorButton?.addEventListener("click", handleReindexVector);
    elements.keywordForm?.addEventListener("submit", handleExtractKeywords);
    elements.graphSearchForm?.addEventListener("submit", handleGraphSearch);
    elements.vectorSearchForm?.addEventListener("submit", handleVectorSearch);
    elements.askForm?.addEventListener("submit", handleAsk);
}

async function handleBuildGraph() {
    setButtonLoading(elements.buildGraphButton, "建立中...");
    elements.indexStatus.innerHTML = renderLoadingInline("正在建立 Neo4j 圖譜...");

    try {
        const result = await fetchJson("/api/graph/build/", { method: "POST" });
        elements.indexStatus.innerHTML = renderIndexSummary(result.data || {});
        showToast(result.message || "Neo4j 圖譜已建立。", "success");
    } catch (error) {
        elements.indexStatus.innerHTML = renderErrorBlock(error.message);
        showToast(error.message, "error");
    } finally {
        restoreButton(elements.buildGraphButton, '<i data-lucide="share-2"></i><span>建立 Neo4j 圖譜</span>');
    }
}

async function handleReindexVector() {
    const batchSize = Math.max(parseInt(elements.vectorBatchSize.value || "64", 10) || 64, 1);
    setButtonLoading(elements.reindexVectorButton, "重建中...");
    elements.indexStatus.innerHTML = renderLoadingInline("正在重建 Qdrant 向量索引...");

    try {
        const result = await fetchJson("/api/vector/reindex/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ batch_size: batchSize }),
        });
        elements.indexStatus.innerHTML = renderIndexSummary(result.data || {});
        showToast(result.message || "Qdrant 索引已重建。", "success");
    } catch (error) {
        elements.indexStatus.innerHTML = renderErrorBlock(error.message);
        showToast(error.message, "error");
    } finally {
        restoreButton(elements.reindexVectorButton, '<i data-lucide="database-zap"></i><span>重建 Qdrant 索引</span>');
    }
}

async function handleExtractKeywords(event) {
    event.preventDefault();
    const text = elements.keywordText.value.trim();
    if (!text) {
        showToast("請輸入要抽取的文字。", "error");
        return;
    }

    const maxKeywords = Math.max(parseInt(elements.keywordMax.value || "12", 10) || 12, 1);
    setButtonLoading(elements.keywordSubmit, "抽取中...");
    elements.keywordResults.innerHTML = renderLoadingInline("正在抽取關鍵字...");

    try {
        const result = await fetchJson("/api/graph/keywords/extract/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, max_keywords: maxKeywords }),
        });
        renderKeywords(result.data?.keywords || []);
        showToast(`抽取完成，共 ${result.data?.keyword_count || 0} 個關鍵字。`, "success");
    } catch (error) {
        elements.keywordResults.innerHTML = renderErrorBlock(error.message);
        showToast(error.message, "error");
    } finally {
        restoreButton(elements.keywordSubmit, '<i data-lucide="sparkles"></i><span>抽取</span>');
    }
}

async function handleGraphSearch(event) {
    event.preventDefault();
    const query = elements.graphQuery.value.trim();
    if (!query) {
        showToast("請輸入 Graph 查詢詞。", "error");
        return;
    }

    const limit = Math.max(parseInt(elements.graphLimit.value || "10", 10) || 10, 1);
    setButtonLoading(elements.graphSearchSubmit, "");
    elements.graphResults.innerHTML = renderLoadingInline("正在查詢 Neo4j...");

    try {
        const result = await fetchJson(`/api/graph/search/?q=${encodeURIComponent(query)}&limit=${limit}`);
        renderGraphResults(result.data || {});
    } catch (error) {
        elements.graphResults.innerHTML = renderErrorBlock(error.message);
        showToast(error.message, "error");
    } finally {
        restoreButton(elements.graphSearchSubmit, '<i data-lucide="search"></i>');
    }
}

async function handleVectorSearch(event) {
    event.preventDefault();
    const query = elements.vectorQuery.value.trim();
    if (!query) {
        showToast("請輸入 Vector 查詢句。", "error");
        return;
    }

    const limit = Math.max(parseInt(elements.vectorLimit.value || "10", 10) || 10, 1);
    setButtonLoading(elements.vectorSearchSubmit, "");
    elements.vectorResults.innerHTML = renderLoadingInline("正在查詢 Qdrant...");

    try {
        const result = await fetchJson(`/api/vector/search/?q=${encodeURIComponent(query)}&limit=${limit}`);
        renderVectorResults(result.data?.results || []);
    } catch (error) {
        elements.vectorResults.innerHTML = renderErrorBlock(error.message);
        showToast(error.message, "error");
    } finally {
        restoreButton(elements.vectorSearchSubmit, '<i data-lucide="search"></i>');
    }
}

async function handleAsk(event) {
    event.preventDefault();
    const question = elements.askQuestion.value.trim();
    if (!question) {
        showToast("請輸入問題。", "error");
        return;
    }

    const limit = Math.max(parseInt(elements.askLimit.value || "5", 10) || 5, 1);
    setButtonLoading(elements.askSubmit, "生成中...");
    elements.answerPanel.innerHTML = renderLoadingInline("正在產生 GraphRAG 回答...");
    renderSources([]);
    renderWarnings([]);

    try {
        const result = await fetchJson("/api/graphrag/ask/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question, limit }),
        });
        const data = result.data || {};
        renderAnswer(data);
        renderSources(data.sources || []);
        renderWarnings(data.warnings || []);
        showToast(result.message || "GraphRAG 回答已生成。", "success");
    } catch (error) {
        elements.answerPanel.innerHTML = renderErrorBlock(error.message);
        showToast(error.message, "error");
    } finally {
        restoreButton(elements.askSubmit, '<i data-lucide="send"></i><span>詢問</span>');
    }
}

function renderKeywords(keywords) {
    if (!keywords.length) {
        elements.keywordResults.innerHTML = renderEmptyBlock("尚無關鍵字。");
        renderIcons();
        return;
    }

    elements.keywordResults.innerHTML = keywords.map((keyword) => `
        <article class="keyword-result-card">
            <div class="keyword-name">${escapeHtml(keyword.name || "-")}</div>
            <div class="keyword-meta">
                <span>${escapeHtml(keyword.type || "unknown")}</span>
                <span>score ${formatScore(keyword.score)}</span>
            </div>
            <div class="keyword-method">${escapeHtml(keyword.method || "unknown")}</div>
        </article>
    `).join("");
}

function renderGraphResults(payload) {
    const expanded = payload.expanded_keywords || [];
    const results = payload.results || [];
    const expandedHtml = expanded.length
        ? `<div class="related-reasons mb-3">${expanded.map((keyword) => `<span class="search-chip">${escapeHtml(keyword)}</span>`).join("")}</div>`
        : '<div class="related-empty mb-3">沒有擴展關鍵字。</div>';

    if (!results.length) {
        elements.graphResults.innerHTML = `${expandedHtml}${renderEmptyBlock("沒有 Graph 查詢結果。")}`;
        renderIcons();
        return;
    }

    elements.graphResults.innerHTML = expandedHtml + results.map((item) => `
        <article class="related-card related-card-static">
            <div class="related-title">${escapeHtml(item.matched_keyword || "-")}</div>
            <div class="related-meta">
                ${escapeHtml(item.match_type || "-")} | ${escapeHtml(item.matched_field || "-")} | graph ${formatScore(item.graph_score)}
            </div>
            <div class="related-body">${escapeHtml(item.content || item.meeting_name || "-")}</div>
            <div class="related-reasons">
                <span class="search-chip">${escapeHtml(item.meeting_id || "-")}</span>
                <span class="search-chip">${escapeHtml(item.item_id || "-")}</span>
                <span class="search-chip">${escapeHtml(item.keyword_method || "unknown")}</span>
            </div>
        </article>
    `).join("");
    renderIcons();
}

function renderVectorResults(results) {
    if (!results.length) {
        elements.vectorResults.innerHTML = renderEmptyBlock("沒有 Vector 查詢結果。");
        renderIcons();
        return;
    }

    elements.vectorResults.innerHTML = results.map((item) => `
        <article class="related-card related-card-static">
            <div class="related-title">${escapeHtml(item.meeting_name || item.item_id || "-")}</div>
            <div class="related-meta">
                semantic ${formatScore(item.semantic_score)} | ${escapeHtml(item.meeting_date || "-")} | ${escapeHtml(item.owner || "-")}
            </div>
            <div class="related-body">${escapeHtml(item.content || "-")}</div>
            <div class="related-reasons">
                <span class="search-chip">${escapeHtml(item.meeting_id || "-")}</span>
                <span class="search-chip">${escapeHtml(item.item_id || "-")}</span>
            </div>
        </article>
    `).join("");
    renderIcons();
}

function renderAnswer(data) {
    elements.answerPanel.innerHTML = `
        <div class="answer-title">${escapeHtml(data.question || "-")}</div>
        <div class="answer-body">${escapeHtml(data.answer || "-").replaceAll("\n", "<br>")}</div>
        <div class="score-grid score-grid-inline mt-3">
            <div class="score-pill"><span class="score-pill-label">Structured</span><span class="score-pill-value">${escapeHtml(String(data.contexts?.structured?.length || 0))}</span></div>
            <div class="score-pill"><span class="score-pill-label">Graph</span><span class="score-pill-value">${escapeHtml(String(data.contexts?.graph?.paths?.length || 0))}</span></div>
            <div class="score-pill"><span class="score-pill-label">Semantic</span><span class="score-pill-value">${escapeHtml(String(data.contexts?.semantic?.length || 0))}</span></div>
        </div>
    `;
}

function renderSources(sources) {
    elements.sourceCount.textContent = String(sources.length);
    elements.sourceList.innerHTML = sources.length
        ? sources.map((source) => `
            <article class="related-card related-card-static">
                <div class="related-title">${escapeHtml(source.meeting_name || source.meeting_id || "-")}</div>
                <div class="related-meta">${escapeHtml(source.meeting_date || "-")} | ${escapeHtml(source.item_id || "-")}</div>
                <div class="related-body">${escapeHtml(source.content || source.snippet || "-")}</div>
            </article>
        `).join("")
        : '<div class="related-empty">沒有來源資料。</div>';
}

function renderWarnings(warnings) {
    elements.warningCount.textContent = String(warnings.length);
    elements.warningList.innerHTML = warnings.length
        ? warnings.map((warning) => `<div class="related-empty">${escapeHtml(warning)}</div>`).join("")
        : '<div class="related-empty">沒有警告。</div>';
}

function renderIndexSummary(data) {
    const rows = Object.entries(data)
        .filter(([, value]) => typeof value !== "object" || value === null)
        .map(([key, value]) => `
            <div class="compact-list-row">
                <strong>${escapeHtml(key)}</strong>
                <span>${escapeHtml(String(value ?? "-"))}</span>
            </div>
        `)
        .join("");

    const nodeCounts = data.node_counts ? renderObjectGrid("node_counts", data.node_counts) : "";
    const relationshipCounts = data.relationship_counts ? renderObjectGrid("relationship_counts", data.relationship_counts) : "";
    return `<div class="compact-list">${rows}${nodeCounts}${relationshipCounts}</div>`;
}

function renderObjectGrid(title, payload) {
    const rows = Object.entries(payload || {})
        .map(([key, value]) => `
            <div class="compact-list-row">
                <strong>${escapeHtml(key)}</strong>
                <span>${escapeHtml(String(value ?? 0))}</span>
            </div>
        `)
        .join("");
    return `
        <details class="preview-section mt-2" open>
            <summary class="preview-section-head"><span>${escapeHtml(title)}</span></summary>
            <div class="compact-list mt-2">${rows}</div>
        </details>
    `;
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const result = await response.json();
    if (!response.ok || !result.success) {
        throw new Error(result.message || "Request failed.");
    }
    return result;
}

function setButtonLoading(button, label) {
    if (!button) {
        return;
    }
    button.dataset.originalDisabled = button.disabled ? "true" : "false";
    button.disabled = true;
    button.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>${label ? `<span>${escapeHtml(label)}</span>` : ""}`;
}

function restoreButton(button, html) {
    if (!button) {
        return;
    }
    button.disabled = button.dataset.originalDisabled === "true";
    button.innerHTML = html;
    renderIcons();
}

function showToast(message, type) {
    elements.toastBody.textContent = message;
    elements.toastElement.className = `toast align-items-center border-0 ${type === "error" ? "text-bg-danger" : "text-bg-success"}`;
    toast.show();
}

function renderLoadingInline(message) {
    return `
        <div class="empty-state-shell compact-empty">
            <div class="spinner-border text-primary mb-3" role="status"></div>
            <div class="fw-semibold">${escapeHtml(message)}</div>
        </div>
    `;
}

function renderEmptyBlock(message) {
    return `<div class="related-empty">${escapeHtml(message)}</div>`;
}

function renderErrorBlock(message) {
    return `<div class="related-empty text-danger">${escapeHtml(message)}</div>`;
}

function formatScore(value) {
    const number = Number(value || 0);
    if (Number.isNaN(number)) {
        return "0.000";
    }
    return number.toFixed(3);
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function renderIcons() {
    if (window.lucide) {
        window.lucide.createIcons();
    }
}
