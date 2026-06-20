const elements = {
    refreshButton: document.getElementById("refresh-button"),
    advancedToggle: document.getElementById("advanced-toggle"),
    advancedClose: document.getElementById("advanced-close"),
    advancedPanel: document.getElementById("advanced-panel"),
    advancedBackdrop: document.getElementById("advanced-backdrop"),
    graphFitButton: document.getElementById("graph-fit-button"),
    graphLayoutButton: document.getElementById("graph-layout-button"),
    graphZoomInButton: document.getElementById("graph-zoom-in-button"),
    graphZoomOutButton: document.getElementById("graph-zoom-out-button"),
    graphLayoutSelect: document.getElementById("graph-layout-select"),
    graphLabelToggle: document.getElementById("graph-label-toggle"),
    graphKicker: document.getElementById("graph-kicker"),
    graphTitle: document.getElementById("graph-title"),
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
    text2cypherForm: document.getElementById("text2cypher-form"),
    text2cypherQuestion: document.getElementById("text2cypher-question"),
    text2cypherLimit: document.getElementById("text2cypher-limit"),
    text2cypherSubmit: document.getElementById("text2cypher-submit"),
    text2cypherResults: document.getElementById("text2cypher-results"),
    evalQuestions: document.getElementById("eval-questions"),
    evalLimit: document.getElementById("eval-limit"),
    evalSeedButton: document.getElementById("eval-seed-button"),
    evalRunButton: document.getElementById("eval-run-button"),
    evalSaveButton: document.getElementById("eval-save-button"),
    evalSummary: document.getElementById("eval-summary"),
    evalResults: document.getElementById("eval-results"),
    askForm: document.getElementById("ask-form"),
    askQuestion: document.getElementById("ask-question"),
    askLimit: document.getElementById("ask-limit"),
    askSubmit: document.getElementById("ask-submit"),
    answerPanel: document.getElementById("answer-panel"),
    answerReader: document.getElementById("answer-reader"),
    answerReaderBackdrop: document.getElementById("answer-reader-backdrop"),
    answerReaderClose: document.getElementById("answer-reader-close"),
    answerReaderQuestion: document.getElementById("answer-reader-question"),
    answerReaderBody: document.getElementById("answer-reader-body"),
    sourceCount: document.getElementById("source-count"),
    sourceList: document.getElementById("source-list"),
    warningCount: document.getElementById("warning-count"),
    warningList: document.getElementById("warning-list"),
    diagnosticStatus: document.getElementById("diagnostic-status"),
    diagnosticPanel: document.getElementById("diagnostic-panel"),
};

const toast = new bootstrap.Toast(elements.toastElement, { delay: 2800 });
let evidenceCy = null;
let evidenceGraphData = { nodes: [], edges: [], summary: {} };
let graphLabelsVisible = false;
let currentAnswerData = null;
let currentEvalCases = [];

init();

function init() {
    bindEvents();
    renderKeywords([]);
    renderGraphResults({ expanded_keywords: [], results: [] });
    renderVectorResults([]);
    renderText2CypherResults(null);
    renderEvalCases([]);
    renderSources([]);
    renderWarnings([]);
    renderDiagnostics(null);
    renderEvidenceGraph({ nodes: [], edges: [] }, {
        kicker: "證據圖譜",
        title: "證據圖譜",
        emptyText: "尚未有圖譜證據。",
    });
    renderIcons();
}

function bindEvents() {
    elements.refreshButton?.addEventListener("click", () => {
        elements.indexStatus.textContent = "已就緒";
        showToast("已就緒。", "success");
    });

    elements.buildGraphButton?.addEventListener("click", handleBuildGraph);
    elements.advancedToggle?.addEventListener("click", openAdvancedPanel);
    elements.advancedClose?.addEventListener("click", closeAdvancedPanel);
    elements.advancedBackdrop?.addEventListener("click", closeAdvancedPanel);
    elements.graphFitButton?.addEventListener("click", fitEvidenceGraph);
    elements.graphLayoutButton?.addEventListener("click", relayoutEvidenceGraph);
    elements.graphZoomInButton?.addEventListener("click", () => zoomEvidenceGraph(1.18));
    elements.graphZoomOutButton?.addEventListener("click", () => zoomEvidenceGraph(0.84));
    elements.graphLayoutSelect?.addEventListener("change", relayoutEvidenceGraph);
    elements.graphLabelToggle?.addEventListener("click", toggleGraphLabels);
    elements.answerPanel?.addEventListener("click", handleAnswerPanelClick);
    elements.answerReaderBody?.addEventListener("click", handleAnswerNodeClick);
    elements.answerReaderClose?.addEventListener("click", closeAnswerReader);
    elements.answerReaderBackdrop?.addEventListener("click", closeAnswerReader);
    document.addEventListener("keydown", handleDocumentKeydown);
    elements.reindexVectorButton?.addEventListener("click", handleReindexVector);
    elements.keywordForm?.addEventListener("submit", handleExtractKeywords);
    elements.graphSearchForm?.addEventListener("submit", handleGraphSearch);
    elements.vectorSearchForm?.addEventListener("submit", handleVectorSearch);
    elements.text2cypherForm?.addEventListener("submit", handleText2Cypher);
    elements.evalSeedButton?.addEventListener("click", handleEvalSeed);
    elements.evalRunButton?.addEventListener("click", handleEvalRun);
    elements.evalSaveButton?.addEventListener("click", handleEvalSave);
    elements.evalResults?.addEventListener("change", handleEvalCaseChange);
    elements.askForm?.addEventListener("submit", handleAsk);
}

function openAdvancedPanel() {
    elements.advancedPanel?.classList.remove("d-none");
    elements.advancedBackdrop?.classList.remove("d-none");
    elements.advancedPanel?.setAttribute("aria-hidden", "false");
}

function closeAdvancedPanel() {
    elements.advancedPanel?.classList.add("d-none");
    elements.advancedBackdrop?.classList.add("d-none");
    elements.advancedPanel?.setAttribute("aria-hidden", "true");
}

function handleAnswerPanelClick(event) {
    const readerTrigger = event.target.closest("[data-answer-reader-open]");
    if (readerTrigger) {
        event.preventDefault();
        openAnswerReader();
        return;
    }
    handleAnswerNodeClick(event);
}

function openAnswerReader() {
    if (!currentAnswerData || !elements.answerReader || !elements.answerReaderBody) {
        return;
    }
    const graph = currentAnswerData.contexts?.graph || {};
    if (elements.answerReaderQuestion) {
        elements.answerReaderQuestion.textContent = currentAnswerData.question || "-";
    }
    elements.answerReaderBody.innerHTML = renderMarkdownAnswer(currentAnswerData.answer || "-", graph.nodes || []);
    elements.answerReaderBackdrop?.classList.remove("d-none");
    elements.answerReader.classList.remove("d-none");
    elements.answerReader.setAttribute("aria-hidden", "false");
    document.body.classList.add("answer-reader-opened");
    renderIcons();
}

function closeAnswerReader() {
    elements.answerReaderBackdrop?.classList.add("d-none");
    elements.answerReader?.classList.add("d-none");
    elements.answerReader?.setAttribute("aria-hidden", "true");
    document.body.classList.remove("answer-reader-opened");
}

function handleDocumentKeydown(event) {
    if (event.key === "Escape" && !elements.answerReader?.classList.contains("d-none")) {
        closeAnswerReader();
    }
}

function fitEvidenceGraph() {
    if (evidenceCy) {
        evidenceCy.fit(undefined, 44);
        evidenceCy.center();
    }
}

function relayoutEvidenceGraph() {
    if (!evidenceCy) {
        return;
    }
    evidenceCy.layout(makeEvidenceLayout(true)).run();
}

function zoomEvidenceGraph(factor) {
    if (!evidenceCy) {
        return;
    }
    evidenceCy.zoom({
        level: evidenceCy.zoom() * factor,
        renderedPosition: {
            x: evidenceCy.width() / 2,
            y: evidenceCy.height() / 2,
        },
    });
}

function toggleGraphLabels() {
    graphLabelsVisible = !graphLabelsVisible;
    elements.graphLabelToggle?.classList.toggle("active", graphLabelsVisible);
    if (evidenceCy) {
        evidenceCy.edges().toggleClass("labels-hidden", !graphLabelsVisible);
    }
}

function handleAnswerNodeClick(event) {
    const trigger = event.target.closest("[data-graph-node-id]");
    if (!trigger) {
        return;
    }
    event.preventDefault();
    focusGraphNode(trigger.dataset.graphNodeId);
}

async function handleBuildGraph() {
    setButtonLoading(elements.buildGraphButton, "建立中...");
    elements.indexStatus.innerHTML = renderLoadingInline("正在建立 Neo4j 圖譜...");

    try {
        const result = await fetchJson("/api/graph/build/", { method: "POST" });
        elements.indexStatus.innerHTML = renderIndexSummary(result.data || {});
        showToast(result.message || "Neo4j 圖譜建立完成。", "success");
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
    elements.indexStatus.innerHTML = renderLoadingInline("正在重建 Qdrant 索引...");

    try {
        const result = await fetchJson("/api/vector/reindex/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ batch_size: batchSize }),
        });
        elements.indexStatus.innerHTML = renderIndexSummary(result.data || {});
        showToast(result.message || "Qdrant 索引重建完成。", "success");
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
        showToast("請輸入文字。", "error");
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
        showToast(`關鍵字抽取完成：${result.data?.keyword_count || 0} 個`, "success");
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
        showToast("請輸入 Graph 查詢。", "error");
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
        showToast("請輸入 Vector 查詢。", "error");
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

async function handleText2Cypher(event) {
    event.preventDefault();
    const question = elements.text2cypherQuestion.value.trim();
    if (!question) {
        showToast("請輸入 Text2Cypher 探索問題。", "error");
        return;
    }
    const limit = Math.max(parseInt(elements.text2cypherLimit.value || "20", 10) || 20, 1);
    setButtonLoading(elements.text2cypherSubmit, "探索中...");
    elements.text2cypherResults.innerHTML = renderLoadingInline("正在產生並檢查 Cypher...");

    try {
        const result = await fetchJson("/api/graph/text2cypher/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question, limit }),
        });
        const data = result.data || {};
        renderText2CypherResults(data);
        renderEvidenceGraph(data.graph || {}, {
            kicker: "Text2Cypher 圖譜",
            title: "Text2Cypher 探索圖譜",
            emptyText: "Text2Cypher 結果列沒有可視覺化的圖譜節點。",
        });
        showToast(result.message || "Text2Cypher 探索完成。", "success");
    } catch (error) {
        elements.text2cypherResults.innerHTML = renderErrorBlock(error.message);
        showToast(error.message, "error");
    } finally {
        restoreButton(elements.text2cypherSubmit, '<i data-lucide="search-code"></i><span>探索</span>');
    }
}

async function handleAsk(event) {
    event.preventDefault();
    const question = elements.askQuestion.value.trim();
    if (!question) {
        showToast("請輸入問題。", "error");
        return;
    }

    const limit = elements.askLimit.value || "auto";
    setButtonLoading(elements.askSubmit, "回答中...");
    elements.answerPanel.innerHTML = renderLoadingInline("正在產生 GraphRAG 回答...");
    renderSources([]);
    renderWarnings([]);
    renderDiagnostics(null, "running");
    renderEvidenceGraph({ nodes: [], edges: [] }, {
        kicker: "證據圖譜",
        title: "證據圖譜",
        emptyText: "正在建立回答證據圖...",
    });

    try {
        const result = await fetchJson("/api/graphrag/ask/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question, limit }),
        });
        const data = result.data || {};
        renderEvidenceGraph(data.contexts?.graph || {}, {
            kicker: "證據圖譜",
            title: "證據圖譜",
            emptyText: "本次回答沒有圖譜證據。",
        });
        renderAnswer(data);
        renderSources(data.sources || []);
        renderWarnings(data.warnings || []);
        renderDiagnostics(data);
        showToast(result.message || "GraphRAG 回答完成。", "success");
    } catch (error) {
        elements.answerPanel.innerHTML = renderErrorBlock(error.message);
        renderDiagnostics(null, "error");
        showToast(error.message, "error");
    } finally {
        restoreButton(elements.askSubmit, '<i data-lucide="send"></i><span>詢問</span>');
    }
}

async function handleEvalSeed() {
    const questions = (elements.evalQuestions?.value || "")
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);
    if (!questions.length) {
        showToast("請輸入評估問題。", "error");
        return;
    }

    const limit = elements.evalLimit?.value || "auto";
    setButtonLoading(elements.evalSeedButton, "產生中...");
    elements.evalSummary.innerHTML = renderLoadingInline("正在產生 golden cases...");
    elements.evalResults.innerHTML = "";

    try {
        const result = await fetchJson("/api/graphrag/eval/seed/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ questions, limit }),
        });
        currentEvalCases = result.data?.cases || [];
        renderEvalCases(currentEvalCases);
        showToast(result.message || "評估案例已產生。", "success");
    } catch (error) {
        elements.evalSummary.innerHTML = renderErrorBlock(error.message);
        showToast(error.message, "error");
    } finally {
        restoreButton(elements.evalSeedButton, '<i data-lucide="list-plus"></i><span>產生案例</span>');
    }
}

async function handleEvalRun() {
    if (!currentEvalCases.length) {
        showToast("請先產生評估案例。", "error");
        return;
    }
    setButtonLoading(elements.evalRunButton, "評估中...");
    elements.evalSummary.innerHTML = renderLoadingInline("正在執行 GraphRAG 評估...");

    try {
        const result = await fetchJson("/api/graphrag/eval/run/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cases: currentEvalCases.map(normalizeEvalCaseForRun) }),
        });
        renderEvalReport(result.data || {});
        showToast(result.message || "評估完成。", "success");
    } catch (error) {
        elements.evalSummary.innerHTML = renderErrorBlock(error.message);
        showToast(error.message, "error");
    } finally {
        restoreButton(elements.evalRunButton, '<i data-lucide="play"></i><span>執行評估</span>');
    }
}

async function handleEvalSave() {
    const approvedCases = currentEvalCases.filter((caseItem) => caseItem.enabled || caseItem.review_status === "approved");
    if (!approvedCases.length) {
        showToast("請至少核准一個案例。", "error");
        return;
    }
    setButtonLoading(elements.evalSaveButton, "儲存中...");
    elements.evalSummary.innerHTML = renderLoadingInline(`正在儲存 ${approvedCases.length} 筆 golden cases...`);

    try {
        const result = await fetchJson("/api/graphrag/eval/save/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cases: approvedCases }),
        });
        const data = result.data || {};
        elements.evalSummary.innerHTML = renderSaveSummary(data);
        showToast(result.message || "黃金測試案例已儲存。", "success");
    } catch (error) {
        elements.evalSummary.innerHTML = renderErrorBlock(error.message);
        showToast(error.message, "error");
    } finally {
        restoreButton(elements.evalSaveButton, '<i data-lucide="save"></i><span>儲存核准案例</span>');
    }
}

function handleEvalCaseChange(event) {
    const checkbox = event.target.closest("[data-eval-approve]");
    if (!checkbox) {
        return;
    }
    const index = Number(checkbox.dataset.evalApprove);
    if (!Number.isInteger(index) || !currentEvalCases[index]) {
        return;
    }
    currentEvalCases[index] = {
        ...currentEvalCases[index],
        enabled: checkbox.checked,
        review_status: checkbox.checked ? "approved" : "needs_review",
    };
    renderEvalCases(currentEvalCases);
}

function normalizeEvalCaseForRun(caseItem) {
    return {
        ...caseItem,
        enabled: true,
        review_status: caseItem.review_status || "needs_review",
    };
}

function renderKeywords(keywords) {
    if (!keywords.length) {
        elements.keywordResults.innerHTML = renderEmptyBlock("尚未執行關鍵字抽取。");
        renderIcons();
        return;
    }

    elements.keywordResults.innerHTML = keywords.map((keyword) => `
        <article class="keyword-result-card">
            <div class="keyword-name">${escapeHtml(keyword.name || "-")}</div>
            <div class="keyword-meta">
                <span>${escapeHtml(keyword.type || "未知")}</span>
                <span>score ${formatScore(keyword.score)}</span>
            </div>
            <div class="keyword-method">${escapeHtml(keyword.method || "未知")}</div>
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
                <span class="search-chip">${escapeHtml(item.keyword_method || "未知")}</span>
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

function renderText2CypherResults(payload) {
    if (!elements.text2cypherResults) {
        return;
    }
    if (!payload) {
        elements.text2cypherResults.innerHTML = renderEmptyBlock("尚未執行 Text2Cypher 探索。");
        renderIcons();
        return;
    }
    const warnings = payload.warnings || [];
    const rows = payload.rows || [];
    const statusClass = payload.blocked ? "text-danger" : "text-success";
    elements.text2cypherResults.innerHTML = `
        <article class="related-card related-card-static text2cypher-card">
            <div class="related-title ${statusClass}">
                ${payload.blocked ? "已阻擋" : "唯讀"} ${escapeHtml(String(payload.row_count ?? rows.length))} 筆結果
            </div>
            <div class="related-meta">
                ${escapeHtml(payload.question || "-")} | 產生方式 ${escapeHtml(payload.generated_by || "-")}
            </div>
            <pre class="cypher-preview"><code>${escapeHtml(payload.cypher || "-")}</code></pre>
            ${warnings.length ? `
            <div class="diagnostic-subtitle">警告</div>
                ${warnings.map((warning) => `<div class="diagnostic-warning-text">${escapeHtml(warning)}</div>`).join("")}
            ` : ""}
            <div class="diagnostic-subtitle">結果列</div>
            ${renderText2CypherRows(rows)}
        </article>
    `;
    renderIcons();
}

function renderText2CypherRows(rows) {
    if (!rows.length) {
        return '<div class="related-empty">沒有結果列。</div>';
    }
    const columns = Array.from(rows.reduce((set, row) => {
        Object.keys(row || {}).forEach((key) => set.add(key));
        return set;
    }, new Set())).slice(0, 12);
    return `
        <div class="text2cypher-table-wrap">
            <table class="text2cypher-table">
                <thead>
                    <tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>
                </thead>
                <tbody>
                    ${rows.map((row) => `
                        <tr>
                            ${columns.map((column) => `<td>${escapeHtml(formatCellValue(row?.[column]))}</td>`).join("")}
                        </tr>
                    `).join("")}
                </tbody>
            </table>
        </div>
    `;
}

function formatCellValue(value) {
    if (value === null || value === undefined) {
        return "-";
    }
    if (typeof value === "object") {
        return truncateText(JSON.stringify(value), 140);
    }
    return truncateText(String(value), 140);
}

function renderEvalCases(cases) {
    if (!elements.evalSummary || !elements.evalResults) {
        return;
    }
    if (!cases.length) {
        elements.evalSummary.innerHTML = "尚未有評估案例。";
        elements.evalResults.innerHTML = renderEmptyBlock("沒有評估案例。");
        renderIcons();
        return;
    }
    const consistentCount = cases.filter((item) => item.observed?.evidence_consistency?.is_consistent).length;
    const approvedCount = cases.filter((item) => item.enabled || item.review_status === "approved").length;
    elements.evalSummary.innerHTML = `
        <div class="compact-list">
            <div class="compact-list-row"><strong>評估案例</strong><span>${cases.length}</span></div>
            <div class="compact-list-row"><strong>一致案例</strong><span>${consistentCount}/${cases.length}</span></div>
            <div class="compact-list-row"><strong>已核准案例</strong><span>${approvedCount}/${cases.length}</span></div>
        </div>
    `;
    elements.evalResults.innerHTML = cases.map((caseItem, index) => renderEvalCaseCard(caseItem, index)).join("");
    renderIcons();
}

function renderEvalCaseCard(caseItem, index) {
    const consistency = caseItem.observed?.evidence_consistency || {};
    const expectedItems = caseItem.expected_item_ids || [];
    const expectedMeetings = caseItem.expected_meeting_ids || [];
    const expectedRelations = caseItem.expected_relations || [];
    const route = caseItem.observed?.route?.query_type || "-";
    const checked = caseItem.enabled || caseItem.review_status === "approved";
    return `
        <article class="related-card related-card-static">
            <label class="d-flex align-items-start gap-2 mb-2">
                <input class="form-check-input mt-1" type="checkbox" data-eval-approve="${index}" ${checked ? "checked" : ""}>
                <span>
                    <span class="related-title d-block">${escapeHtml(caseItem.question || "-")}</span>
                    <span class="related-meta d-block">${checked ? "已核准" : "待檢查"}</span>
                </span>
            </label>
            <div class="related-meta">
                ${escapeHtml(caseItem.id || "-")} | 路由 ${escapeHtml(route)} | ${consistency.is_consistent ? "一致" : "不一致"}
            </div>
            <div class="related-body">${escapeHtml(truncateText(caseItem.observed?.answer || "-", 220))}</div>
            <div class="related-reasons">
                ${renderChipGroup("項目", expectedItems)}
                ${renderChipGroup("會議", expectedMeetings)}
                ${renderChipGroup("關係", expectedRelations)}
            </div>
        </article>
    `;
}

function renderEvalReport(report) {
    const summary = report.summary || {};
    const results = report.results || [];
    elements.evalSummary.innerHTML = `
        <div class="compact-list">
            <div class="compact-list-row"><strong>通過</strong><span>${escapeHtml(String(summary.passed || 0))}</span></div>
            <div class="compact-list-row"><strong>失敗</strong><span>${escapeHtml(String(summary.failed || 0))}</span></div>
            <div class="compact-list-row"><strong>略過</strong><span>${escapeHtml(String(summary.skipped || 0))}</span></div>
            <div class="compact-list-row"><strong>已啟用</strong><span>${escapeHtml(String(summary.enabled || 0))}</span></div>
        </div>
    `;
    elements.evalResults.innerHTML = results.length
        ? results.map(renderEvalResultCard).join("")
        : renderEmptyBlock("沒有評估結果。");
    renderIcons();
}

function renderSaveSummary(data) {
    return `
        <div class="compact-list">
            <div class="compact-list-row"><strong>已儲存</strong><span>${escapeHtml(String(data.saved || 0))}</span></div>
            <div class="compact-list-row"><strong>已建立</strong><span>${escapeHtml(String(data.created || 0))}</span></div>
            <div class="compact-list-row"><strong>已更新</strong><span>${escapeHtml(String(data.updated || 0))}</span></div>
            <div class="compact-list-row"><strong>已略過</strong><span>${escapeHtml(String(data.skipped || 0))}</span></div>
            <div class="compact-list-row"><strong>檔案</strong><span>${escapeHtml(data.path || "-")}</span></div>
        </div>
    `;
}

function renderEvalResultCard(result) {
    const failures = result.failures || [];
    const observed = result.observed || {};
    const statusClass = result.status === "passed" ? "text-success" : result.status === "skipped" ? "text-muted" : "text-danger";
    return `
        <article class="related-card related-card-static">
            <div class="related-title ${statusClass}">${escapeHtml(String(result.status || "-").toUpperCase())} ${escapeHtml(result.id || "-")}</div>
            <div class="related-meta">
                ${escapeHtml((observed.route || {}).query_type || "-")} | graph ${escapeHtml(String((observed.graph_item_ids || []).length))} items
            </div>
            ${failures.length ? `<div class="related-body">${failures.map((failure) => escapeHtml(failure)).join("<br>")}</div>` : '<div class="related-body">無失敗項目。</div>'}
            <div class="related-reasons">
                ${renderChipGroup("source items", observed.source_item_ids || [])}
                ${renderChipGroup("relations", observed.graph_relations || [])}
            </div>
        </article>
    `;
}

function renderChipGroup(label, values) {
    if (!values.length) {
        return `<span class="search-chip">${escapeHtml(label)}: -</span>`;
    }
    return values.map((value) => `<span class="search-chip">${escapeHtml(label)}: ${escapeHtml(value)}</span>`).join("");
}

function renderAnswer(data) {
    currentAnswerData = data;
    const graph = data.contexts?.graph || {};
    elements.answerPanel.innerHTML = `
        <div class="answer-title-row">
            <div class="answer-title">${escapeHtml(data.question || "-")}</div>
            <button class="btn btn-light btn-sm border answer-reader-open" type="button" data-answer-reader-open title="展開閱讀">
                <i data-lucide="maximize-2"></i>
                <span>展開</span>
        </div>
        <div class="answer-body">${renderMarkdownAnswer(data.answer || "-", graph.nodes || [])}</div>
        <div class="score-grid score-grid-inline mt-3">
            <div class="score-pill"><span class="score-pill-label">結構</span><span class="score-pill-value">${escapeHtml(String(data.contexts?.structured?.length || 0))}</span></div>
            <div class="score-pill"><span class="score-pill-label">圖譜</span><span class="score-pill-value">${escapeHtml(formatGraphEvidenceCount(data.contexts?.graph || {}))}</span></div>
            <div class="score-pill"><span class="score-pill-label">語意</span><span class="score-pill-value">${escapeHtml(String(data.contexts?.semantic?.length || 0))}</span></div>
            <div class="score-pill"><span class="score-pill-label">範圍</span><span class="score-pill-value">${escapeHtml(formatAnswerScope(data))}</span></div>
        </div>
        ${renderTraceSummary(data.trace)}
    `;
}

function formatAnswerScope(data) {
    const limit = data.limit || "-";
    const mode = String(data.limit_mode || "").replace("auto:", "");
    return mode ? `${limit} ${mode}` : String(limit);
}

function renderEvidenceGraph(graph, options = {}) {
    const graphElement = document.getElementById("evidence-graph");
    const emptyElement = document.getElementById("evidence-graph-empty");
    const countElement = document.getElementById("evidence-graph-count");
    const legendElement = document.getElementById("graph-legend");
    const detailElement = document.getElementById("graph-detail-panel");
    const nodes = graph.nodes || [];
    const edges = graph.edges || [];
    const summary = graph.summary || {};
    evidenceGraphData = { nodes, edges, summary };
    if (elements.graphKicker) {
        elements.graphKicker.textContent = options.kicker || "證據圖譜";
    }
    if (elements.graphTitle) {
        elements.graphTitle.textContent = options.title || "證據圖譜";
    }
    if (countElement) {
        countElement.textContent = formatGraphEvidenceCount(graph);
        countElement.title = graphEvidenceTitle(summary, nodes, edges);
    }

    if (evidenceCy) {
        evidenceCy.destroy();
        evidenceCy = null;
    }
    if (detailElement) {
        detailElement.classList.add("d-none");
        detailElement.innerHTML = "";
    }

    if (!graphElement || !emptyElement) {
        return;
    }

    if (!nodes.length) {
        graphElement.classList.add("d-none");
        emptyElement.classList.remove("d-none");
        emptyElement.textContent = options.emptyText || "本次回答沒有圖譜證據。";
        if (countElement) {
            countElement.textContent = formatGraphEvidenceCount(graph);
        }
        renderGraphLegend([], legendElement);
        return;
    }

    if (!window.cytoscape) {
        graphElement.classList.add("d-none");
        emptyElement.classList.remove("d-none");
        emptyElement.textContent = "Cytoscape.js is not available.";
        renderGraphLegend([], legendElement);
        return;
    }

    emptyElement.classList.add("d-none");
    graphElement.classList.remove("d-none");
    renderGraphLegend(nodes, legendElement);

    evidenceCy = cytoscape({
        container: graphElement,
        elements: [
            ...nodes.map((node) => ({
                data: {
                    id: node.id,
                    label: node.label || node.id,
                    title: node.title || node.label || node.id,
                    type: node.type || "Entity",
                },
            })),
            ...edges.map((edge) => ({
                data: {
                    id: edge.id,
                    source: edge.source,
                    target: edge.target,
                    label: edge.label || "",
                    evidenceSource: edge.evidence_source || "neo4j",
                    title: `${edge.source} -[${edge.label || ""}]-> ${edge.target}`,
                },
            })),
        ],
        style: [
            {
                selector: "node",
                style: {
                    "background-color": "#64748b",
                    "border-color": "#0f172a",
                    "border-width": 1.5,
                    "color": "#f8fafc",
                    "font-size": 10,
                    "font-weight": 800,
                    "label": "data(label)",
                    "text-background-opacity": 0,
                    "text-max-width": 92,
                    "text-outline-color": "#111827",
                    "text-outline-width": 2,
                    "text-valign": "center",
                    "text-wrap": "wrap",
                    "width": 38,
                    "height": 38,
                },
            },
            {
                selector: 'node[type = "Meeting"]',
                style: {
                    "background-color": "#4f7dd4",
                    "shape": "round-rectangle",
                    "width": 72,
                    "height": 42,
                    "font-size": 9,
                },
            },
            {
                selector: 'node[type = "MeetingItem"]',
                style: {
                    "background-color": "#22c55e",
                    "shape": "round-rectangle",
                    "width": 58,
                    "height": 42,
                    "font-size": 11,
                },
            },
            { selector: 'node[type = "Person"]', style: { "background-color": "#ef4444", "width": 42, "height": 42 } },
            {
                selector: 'node[type = "Keyword"]',
                style: {
                    "background-color": "#f59e0b",
                    "shape": "ellipse",
                    "width": 34,
                    "height": 34,
                    "font-size": 9,
                    "text-valign": "bottom",
                    "text-margin-y": 4,
                },
            },
            { selector: 'node[type = "Product"]', style: { "background-color": "#a855f7", "shape": "hexagon" } },
            { selector: 'node[type = "Regulation"]', style: { "background-color": "#f97316", "shape": "hexagon" } },
            { selector: 'node[type = "Date"]', style: { "background-color": "#14b8a6", "shape": "tag", "width": 48 } },
            { selector: 'node[type = "ActionItem"]', style: { "background-color": "#06b6d4", "shape": "round-tag", "width": 64, "height": 38 } },
            { selector: 'node[type = "Decision"]', style: { "background-color": "#8b5cf6", "shape": "vee", "width": 46, "height": 46 } },
            { selector: 'node[type = "Risk"]', style: { "background-color": "#e11d48", "shape": "triangle", "width": 48, "height": 48 } },
            { selector: 'node[type = "Issue"]', style: { "background-color": "#0f766e", "shape": "round-diamond", "width": 54, "height": 54 } },
            {
                selector: "edge",
                style: {
                    "curve-style": "bezier",
                    "line-color": "#94a3b8",
                    "target-arrow-color": "#94a3b8",
                    "target-arrow-shape": "triangle",
                    "opacity": 0.64,
                    "width": 1.5,
                    "label": "data(label)",
                    "font-size": 9,
                    "color": "#e5e7eb",
                    "text-background-color": "#20242c",
                    "text-background-opacity": 0.85,
                    "text-background-padding": 2,
                    "text-rotation": "autorotate",
                },
            },
            {
                selector: ".faded",
                style: {
                    "opacity": 0.12,
                    "text-opacity": 0.12,
                },
            },
            {
                selector: "node.selected",
                style: {
                    "border-color": "#f8fafc",
                    "border-width": 4,
                    "underlay-color": "#60a5fa",
                    "underlay-opacity": 0.24,
                    "underlay-padding": 8,
                    "z-index": 10,
                },
            },
            {
                selector: "edge.selected",
                style: {
                    "line-color": "#f8fafc",
                    "target-arrow-color": "#f8fafc",
                    "width": 4,
                    "opacity": 1,
                    "label": "data(label)",
                    "z-index": 10,
                },
            },
            {
                selector: "edge.labels-hidden",
                style: {
                    "label": "",
                    "text-opacity": 0,
                },
            },
            {
                selector: "edge.selected.labels-hidden",
                style: {
                    "label": "data(label)",
                    "text-opacity": 1,
                },
            },
        ],
        layout: makeEvidenceLayout(false),
        minZoom: 0.35,
        maxZoom: 1.8,
        wheelSensitivity: 0.18,
    });
    evidenceCy.edges().toggleClass("labels-hidden", !graphLabelsVisible);

    bindEvidenceGraphInteractions(evidenceCy, detailElement);
}

function formatGraphEvidenceCount(graph) {
    const summary = graph?.summary || {};
    if (summary.projection === "text2cypher_rows") {
        const nodeCount = Number(summary.node_count ?? graph?.nodes?.length ?? 0);
        const edgeCount = Number(summary.edge_count ?? graph?.edges?.length ?? 0);
        return `${nodeCount}/${edgeCount}`;
    }
    const visible = Number(summary.visible_paths ?? graph?.paths?.length ?? 0);
    const total = Number(summary.total_paths ?? graph?.paths?.length ?? visible);
    if (!Number.isFinite(total) || total <= 0) {
        return "0";
    }
    return visible === total ? String(total) : `${visible}/${total}`;
}

function graphEvidenceTitle(summary, nodes, edges) {
    if (summary?.projection === "text2cypher_rows") {
        return `${nodes.length} 個節點，${edges.length} 條關係，Text2Cypher row 投影`;
    }
    const total = Number(summary?.total_paths || 0);
    const visible = Number(summary?.visible_paths || 0);
    const hidden = Number(summary?.hidden_paths || 0);
    const mode = summary?.selection_mode || "unknown";
    return `${visible}/${total || visible} 條證據路徑，隱藏 ${hidden} 條，${nodes.length} 個節點，${edges.length} 條關係，${mode}`;
}

function renderTraceSummary(trace) {
    if (!trace) {
        return "";
    }
    const route = trace.route?.query_type || "-";
    const routeSource = trace.route?.route_source || "-";
    const retrievers = trace.retrievers || [];
    const contextCounts = trace.context_counts || {};
    const chips = [
        `route: ${route}`,
        `source: ${routeSource}`,
        ...retrievers.map((retriever) => `${retriever.name}: ${retriever.enabled === false ? "skip" : retriever.count ?? 0}`),
        `ctx: ${contextCounts.structured || 0}/${contextCounts.graph_paths || 0}/${contextCounts.semantic || 0}`,
    ];
    return `
        <div class="related-reasons trace-summary mt-3">
            ${chips.map((chip) => `<span class="search-chip">${escapeHtml(chip)}</span>`).join("")}
        </div>
    `;
}

function makeEvidenceLayout(animate) {
    const selectedLayout = elements.graphLayoutSelect?.value || "cose";
    if (selectedLayout === "breadthfirst") {
        return {
            name: "breadthfirst",
            animate,
            fit: true,
            padding: 44,
            directed: true,
            spacingFactor: 1.25,
        };
    }
    if (selectedLayout === "circle") {
        return {
            name: "circle",
            animate,
            fit: true,
            padding: 44,
        };
    }
    return {
        name: "cose",
        animate,
        fit: true,
        padding: 44,
        nodeRepulsion: 9000,
        idealEdgeLength: 120,
    };
}

function bindEvidenceGraphInteractions(cy, detailElement) {
    cy.on("mouseover", "node", (event) => highlightNeighborhood(cy, event.target));
    cy.on("mouseout", "node", () => clearGraphHighlight(cy));
    cy.on("tap", "node", (event) => {
        selectGraphElement(cy, event.target);
        renderGraphDetail(detailElement, {
            heading: event.target.data("label"),
            type: event.target.data("type"),
            nodeId: event.target.id(),
            expandable: true,
            rows: {
                id: event.target.id(),
                title: event.target.data("title"),
            },
        });
    });
    cy.on("tap", "edge", (event) => {
        selectGraphElement(cy, event.target);
        renderGraphDetail(detailElement, {
            heading: event.target.data("label"),
            type: "關係",
            rows: {
                source: event.target.data("source"),
                target: event.target.data("target"),
                relation: event.target.data("label"),
                source_type: event.target.data("evidenceSource"),
            },
        });
    });
    cy.on("tap", (event) => {
        if (event.target === cy) {
            clearGraphHighlight(cy);
            detailElement?.classList.add("d-none");
        }
    });
}

function highlightNeighborhood(cy, node) {
    const neighborhood = node.closedNeighborhood();
    cy.elements().addClass("faded");
    neighborhood.removeClass("faded");
    node.connectedEdges().addClass("selected");
}

function clearGraphHighlight(cy) {
    cy.elements().removeClass("faded selected");
}

function selectGraphElement(cy, element) {
    cy.elements().removeClass("selected");
    element.addClass("selected");
    if (element.group && element.group() === "nodes") {
        element.connectedEdges().addClass("selected");
    }
}

function focusGraphNode(nodeId) {
    if (!evidenceCy || !nodeId) {
        return;
    }
    const node = evidenceCy.getElementById(nodeId);
    if (!node.length) {
        return;
    }
    clearGraphHighlight(evidenceCy);
    selectGraphElement(evidenceCy, node);
    highlightNeighborhood(evidenceCy, node);
    evidenceCy.animate(
        {
            center: { eles: node },
            zoom: Math.max(evidenceCy.zoom(), 1.15),
        },
        { duration: 260 }
    );
    renderGraphDetail(document.getElementById("graph-detail-panel"), {
        heading: node.data("label"),
        type: node.data("type"),
        rows: {
            id: node.id(),
            title: node.data("title"),
        },
    });
}

function renderGraphDetail(container, detail) {
    if (!container) {
        return;
    }
    container.classList.remove("d-none");
    container.innerHTML = `
        <div class="graph-detail-head">
            <span>${escapeHtml(detail.type || "細節")}</span>
            <button class="btn btn-light btn-sm border" type="button" data-graph-detail-close>
                <i data-lucide="x"></i>
            </button>
        </div>
        <div class="graph-detail-title">${escapeHtml(detail.heading || "-")}</div>
        <div class="graph-detail-list">
            ${Object.entries(detail.rows || {}).map(([key, value]) => `
                <div class="graph-detail-row">
                    <strong>${escapeHtml(key)}</strong>
                    <span>${escapeHtml(value || "-")}</span>
                </div>
            `).join("")}
        </div>
        ${detail.expandable && detail.nodeId ? renderGraphExpandControls(detail) : ""}
    `;
    container.querySelector("[data-graph-detail-close]")?.addEventListener("click", () => {
        container.classList.add("d-none");
    });
    container.querySelectorAll("[data-graph-expand-node]").forEach((button) => {
        button.addEventListener("click", handleGraphNodeExpand);
    });
    renderIcons();
}

function renderGraphExpandControls(detail) {
    const nodeId = escapeHtml(detail.nodeId);
    if (detail.type === "MeetingItem") {
        const scopes = [
            ["meeting", "會議"],
            ["owner", "負責人"],
            ["dates", "日期"],
            ["product_regulation", "產品/法規"],
            ["keyword", "關鍵字"],
            ["semantic", "語意"],
        ];
        return `
            <div class="graph-expand-grid">
                ${scopes.map(([scope, label]) => `
                    <button class="btn btn-light btn-sm border graph-expand-button" type="button" data-graph-expand-node="${nodeId}" data-graph-expand-scope="${escapeHtml(scope)}">
                        ${escapeHtml(label)}
                    </button>
                `).join("")}
            </div>
        `;
    }
    return `
        <button class="btn btn-primary btn-primary-custom btn-sm graph-expand-button" type="button" data-graph-expand-node="${nodeId}" data-graph-expand-scope="default">
            <i data-lucide="plus"></i><span>展開一層</span>
        </button>
    `;
}

async function handleGraphNodeExpand(event) {
    const button = event.currentTarget;
    const nodeId = button?.dataset?.graphExpandNode;
    const relationScope = button?.dataset?.graphExpandScope || "default";
    if (!nodeId) {
        return;
    }
    button.disabled = true;
    const originalHtml = button.innerHTML;
    button.innerHTML = '<span class="spinner-border spinner-border-sm"></span><span>展開中</span>';
    try {
        const result = await fetchJson("/api/graph/node/expand/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ node_id: nodeId, relation_scope: relationScope, limit: 10 }),
        });
        const data = result.data || {};
        mergeGraphIntoEvidence(data.graph || {});
        (data.warnings || []).forEach((warning) => showToast(warning, "error"));
        showToast(result.message || "節點已展開。", "success");
    } catch (error) {
        showToast(error.message, "error");
    } finally {
        button.disabled = false;
        button.innerHTML = originalHtml;
        renderIcons();
    }
}

function mergeGraphIntoEvidence(graph) {
    if (!evidenceCy || !graph) {
        return;
    }
    const incomingNodes = graph.nodes || [];
    const incomingEdges = graph.edges || [];
    const newElements = [];

    for (const node of incomingNodes) {
        if (!node?.id || evidenceCy.getElementById(node.id).length) {
            continue;
        }
        newElements.push({
            group: "nodes",
            data: {
                id: node.id,
                label: node.label || node.id,
                title: node.title || node.label || node.id,
                type: node.type || "Entity",
            },
        });
    }

    for (const edge of incomingEdges) {
        if (!edge?.id || !edge.source || !edge.target || evidenceCy.getElementById(edge.id).length) {
            continue;
        }
        newElements.push({
            group: "edges",
            data: {
                id: edge.id,
                source: edge.source,
                target: edge.target,
                label: edge.label || "",
                evidenceSource: edge.evidence_source || "manual_expansion",
                title: `${edge.source} -[${edge.label || ""}]-> ${edge.target}`,
            },
        });
    }

    if (!newElements.length) {
        return;
    }
    evidenceCy.add(newElements);
    evidenceCy.edges().toggleClass("labels-hidden", !graphLabelsVisible);
    evidenceGraphData.nodes = mergeGraphItemsById(evidenceGraphData.nodes || [], incomingNodes);
    evidenceGraphData.edges = mergeGraphItemsById(evidenceGraphData.edges || [], incomingEdges);
    updateGraphCountFromCurrentCy();
    renderGraphLegend(evidenceGraphData.nodes, document.getElementById("graph-legend"));
    relayoutEvidenceGraph();
}

function mergeGraphItemsById(existingItems, incomingItems) {
    const byId = new Map();
    for (const item of existingItems || []) {
        if (item?.id) {
            byId.set(item.id, item);
        }
    }
    for (const item of incomingItems || []) {
        if (item?.id && !byId.has(item.id)) {
            byId.set(item.id, item);
        }
    }
    return Array.from(byId.values());
}

function updateGraphCountFromCurrentCy() {
    const countElement = document.getElementById("evidence-graph-count");
    if (!countElement || !evidenceCy) {
        return;
    }
    const nodeCount = evidenceCy.nodes().length;
    const edgeCount = evidenceCy.edges().length;
    countElement.textContent = `${nodeCount}/${edgeCount}`;
    countElement.title = `${nodeCount} 個節點，${edgeCount} 條關係`;
}

function renderGraphLegend(nodes, container) {
    if (!container) {
        return;
    }
    const types = [...new Set(nodes.map((node) => node.type || "Entity"))];
    if (!types.length) {
        container.innerHTML = "";
        return;
    }
    container.innerHTML = types.map((type) => `
        <span class="graph-legend-item" data-legend-type="${escapeHtml(type)}">
            <span class="graph-legend-dot"></span>
            ${escapeHtml(type)}
        </span>
    `).join("");
}

function renderMarkdownAnswer(answer, graphNodes) {
    const source = String(answer || "-");
    const markdownHtml = window.marked
        ? marked.parse(source, { breaks: true, gfm: true })
        : escapeHtml(source).replaceAll("\n", "<br>");
    const cleanHtml = window.DOMPurify
        ? DOMPurify.sanitize(markdownHtml, {
            ALLOWED_TAGS: [
                "p", "br", "strong", "em", "ul", "ol", "li", "code", "pre",
                "blockquote", "hr", "table", "thead", "tbody", "tr", "th", "td",
                "h1", "h2", "h3", "h4", "a",
            ],
            ALLOWED_ATTR: ["href", "title", "target", "rel"],
        })
        : markdownHtml;
    return linkGraphTermsInHtml(cleanHtml, graphNodes);
}

function linkGraphTermsInHtml(html, graphNodes) {
    const template = document.createElement("template");
    template.innerHTML = html;
    const terms = buildGraphLinkTerms(graphNodes);
    if (!terms.length) {
        return template.innerHTML;
    }
    linkTermsInNode(template.content, terms);
    return template.innerHTML;
}

function linkTermsInNode(root, terms) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
            const parent = node.parentElement;
            if (!parent || ["CODE", "PRE", "SCRIPT", "STYLE", "BUTTON", "A"].includes(parent.tagName)) {
                return NodeFilter.FILTER_REJECT;
            }
            return NodeFilter.FILTER_ACCEPT;
        },
    });
    const textNodes = [];
    while (walker.nextNode()) {
        textNodes.push(walker.currentNode);
    }
    for (const textNode of textNodes) {
        const fragment = linkTermsInText(textNode.nodeValue || "", terms);
        if (fragment) {
            textNode.replaceWith(fragment);
        }
    }
}

function linkTermsInText(text, terms) {
    let cursor = 0;
    const matches = [];
    while (cursor < text.length) {
        const match = findNextGraphTerm(text, terms, cursor);
        if (!match) {
            break;
        }
        matches.push(match);
        cursor = match.index + match.text.length;
    }
    if (!matches.length) {
        return null;
    }
    const fragment = document.createDocumentFragment();
    let lastIndex = 0;
    for (const match of matches) {
        if (match.index > lastIndex) {
            fragment.append(document.createTextNode(text.slice(lastIndex, match.index)));
        }
        const button = document.createElement("button");
        button.className = "answer-node-link";
        button.type = "button";
        button.dataset.graphNodeId = match.nodeId;
        button.textContent = match.text;
        fragment.append(button);
        lastIndex = match.index + match.text.length;
    }
    if (lastIndex < text.length) {
        fragment.append(document.createTextNode(text.slice(lastIndex)));
    }
    return fragment;
}

function findNextGraphTerm(text, terms, startIndex) {
    let best = null;
    for (const term of terms) {
        const index = text.indexOf(term.text, startIndex);
        if (index < 0 || !isGraphTermBoundary(text, index, term.text.length)) {
            continue;
        }
        if (!best || index < best.index || (index === best.index && term.text.length > best.text.length)) {
            best = { ...term, index };
        }
    }
    return best;
}

function isGraphTermBoundary(text, index, length) {
    const before = index > 0 ? text[index - 1] : "";
    const after = index + length < text.length ? text[index + length] : "";
    return !/[A-Za-z0-9_:-]/.test(before) && !/[A-Za-z0-9_:-]/.test(after);
}

function buildGraphLinkTerms(graphNodes) {
    const seen = new Set();
    const terms = [];
    for (const node of graphNodes || []) {
        for (const value of [node.id, graphNodeValue(node.id), node.label]) {
            const text = String(value || "").trim();
            if (text.length < 2 || seen.has(text)) {
                continue;
            }
            seen.add(text);
            terms.push({ text, nodeId: node.id });
        }
    }
    return terms.sort((left, right) => right.text.length - left.text.length);
}

function graphNodeValue(nodeId) {
    const parts = String(nodeId || "").split(":");
    return parts.length > 1 ? parts.slice(1).join(":") : nodeId;
}

function renderSources(sources) {
    elements.sourceCount.textContent = String(sources.length);
    elements.sourceList.innerHTML = sources.length
        ? sources.map((source) => `
            <article class="related-card related-card-static">
                <div class="related-title">${escapeHtml(source.meeting_name || source.meeting_id || "-")}</div>
                <div class="related-meta">${escapeHtml(source.evidence_id || "-")} | ${escapeHtml(source.relation || "-")} | ${escapeHtml(source.item_id || "-")}</div>
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

function renderDiagnostics(data, state = "idle") {
    if (!elements.diagnosticPanel || !elements.diagnosticStatus) {
        return;
    }
    if (!data) {
        const label = state === "running" ? "執行中" : state === "error" ? "錯誤" : "待命";
        elements.diagnosticStatus.textContent = label;
        elements.diagnosticStatus.className = `badge border ${state === "error" ? "text-bg-danger" : "text-bg-light"}`;
        elements.diagnosticPanel.innerHTML = state === "running"
            ? renderLoadingInline("正在整理查詢診斷...")
            : '<div class="related-empty">尚未有查詢診斷。</div>';
        renderIcons();
        return;
    }

    const trace = data.trace || {};
    const route = data.query_route || trace.route || {};
    const graph = data.contexts?.graph || {};
    const graphSummary = trace.graph_summary || graph.summary || {};
    const warnings = data.warnings || [];
    const statusText = warnings.length ? `${warnings.length} 個警告` : route.query_type || "就緒";
    elements.diagnosticStatus.textContent = statusText;
    elements.diagnosticStatus.className = `badge border ${warnings.length ? "text-bg-warning" : "text-bg-light"}`;

    elements.diagnosticPanel.innerHTML = `
        <div class="diagnostic-grid">
            ${renderDiagnosticSection("查詢路由", renderRouteDiagnostics(route, data))}
            ${renderDiagnosticSection("實體", renderEntityDiagnostics(route.entities || {}))}
            ${renderDiagnosticSection("檢索器", renderRetrieverDiagnostics(trace.retrievers || []))}
            ${renderDiagnosticSection("證據", renderEvidenceDiagnostics(trace, graphSummary, graph))}
            ${renderDiagnosticSection("警告", renderWarningDiagnostics(warnings))}
        </div>
    `;
    renderIcons();
}

function renderDiagnosticSection(title, body) {
    return `
        <section class="diagnostic-section">
            <div class="diagnostic-section-title">${escapeHtml(title)}</div>
            ${body}
        </section>
    `;
}

function renderRouteDiagnostics(route, data) {
    const rows = [
        ["查詢類型", route.query_type || "-"],
        ["路由來源", route.route_source || "-"],
        ["信心分數", route.confidence ?? "-"],
        ["檢索模式", (route.retrieval_modes || []).join(", ") || "-"],
        ["回答樣式", route.answer_style || "-"],
        ["限制筆數", data.limit ?? "-"],
        ["限制模式", data.limit_mode || "-"],
    ];
    return renderDiagnosticRows(rows);
}

function renderEntityDiagnostics(entities) {
    const entries = Object.entries(entities || {}).filter(([, value]) => String(value || "").trim());
    if (!entries.length) {
        return '<div class="related-empty">沒有實體資訊。</div>';
    }
    return `
        <div class="diagnostic-chip-row">
            ${entries.map(([key, value]) => `<span class="search-chip">${escapeHtml(key)}: ${escapeHtml(value)}</span>`).join("")}
        </div>
    `;
}

function renderRetrieverDiagnostics(retrievers) {
    if (!retrievers.length) {
        return '<div class="related-empty">沒有檢索器追蹤資料。</div>';
    }
    return retrievers.map((retriever) => {
        const enabled = retriever.enabled !== false;
        const mode = enabled ? "已啟用" : "已停用";
        const chips = [
            `筆數：${retriever.count ?? 0}`,
            `限制：${retriever.limit ?? 0}`,
            ...(retriever.retrieval_modes ? [`模式：${retriever.retrieval_modes.join(", ")}`] : []),
            ...((retriever.expanded_keywords || []).length ? [`擴展關鍵字：${retriever.expanded_keywords.join(", ")}`] : []),
        ];
        return `
            <article class="diagnostic-retriever ${enabled ? "" : "diagnostic-muted"}">
                <div class="diagnostic-retriever-head">
                    <strong>${escapeHtml(retriever.name || "-")}</strong>
                    <span>${escapeHtml(mode)}</span>
                </div>
                <div class="diagnostic-chip-row">
                    ${chips.map((chip) => `<span class="search-chip">${escapeHtml(chip)}</span>`).join("")}
                </div>
                ${(retriever.warnings || []).length ? `<div class="diagnostic-warning-text">${(retriever.warnings || []).map(escapeHtml).join("<br>")}</div>` : ""}
            </article>
        `;
    }).join("");
}

function renderEvidenceDiagnostics(trace, graphSummary, graph) {
    const contextCounts = trace.context_counts || {};
    const evidence = trace.evidence || {};
    const rows = [
        ["structured_context", contextCounts.structured ?? 0],
        ["graph_paths", contextCounts.graph_paths ?? graph.paths?.length ?? 0],
        ["semantic_context", contextCounts.semantic ?? 0],
        ["sources", contextCounts.sources ?? 0],
        ["evidence_records", evidence.count ?? contextCounts.evidence ?? 0],
        ["selection_mode", graphSummary.selection_mode || "-"],
        ["visible_paths", graphSummary.visible_paths ?? graph.paths?.length ?? 0],
        ["total_paths", graphSummary.total_paths ?? graph.paths?.length ?? 0],
        ["hidden_paths", graphSummary.hidden_paths ?? 0],
    ];
    const relationChips = Object.entries(evidence.relations || {})
        .map(([relation, count]) => `<span class="search-chip">${escapeHtml(relation)}: ${escapeHtml(count)}</span>`)
        .join("");
    const sourceChips = Object.entries(evidence.sources || {})
        .map(([source, count]) => `<span class="search-chip">${escapeHtml(source)}: ${escapeHtml(count)}</span>`)
        .join("");
    return `
        ${renderDiagnosticRows(rows)}
        <div class="diagnostic-subtitle">Relations</div>
        <div class="diagnostic-chip-row">${relationChips || '<span class="search-chip">-</span>'}</div>
        <div class="diagnostic-subtitle">來源</div>
        <div class="diagnostic-chip-row">${sourceChips || '<span class="search-chip">-</span>'}</div>
    `;
}

function renderWarningDiagnostics(warnings) {
    if (!warnings.length) {
        return '<div class="related-empty">沒有警告。</div>';
    }
    return warnings.map((warning) => `<div class="diagnostic-warning-text">${escapeHtml(warning)}</div>`).join("");
}

function renderDiagnosticRows(rows) {
    return `
        <div class="compact-list diagnostic-rows">
            ${rows.map(([key, value]) => `
                <div class="compact-list-row">
                    <strong>${escapeHtml(key)}</strong>
                    <span>${escapeHtml(String(value ?? "-"))}</span>
                </div>
            `).join("")}
        </div>
    `;
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
    let result = {};
    try {
        result = await response.json();
    } catch (_error) {
        result = { success: false, message: `${response.status} ${response.statusText || "請求失敗"}` };
    }
    if (!response.ok || !result.success) {
        throw new Error(result.message || "請求失敗。");
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

function truncateText(value, maxLength) {
    const text = String(value ?? "");
    if (text.length <= maxLength) {
        return text;
    }
    return `${text.slice(0, Math.max(maxLength - 3, 0))}...`;
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
