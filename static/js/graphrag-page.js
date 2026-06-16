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
    renderEvalCases([]);
    renderSources([]);
    renderWarnings([]);
    renderEvidenceGraph({ nodes: [], edges: [] });
    renderIcons();
}

function bindEvents() {
    elements.refreshButton?.addEventListener("click", () => {
        elements.indexStatus.textContent = "控制台已重新整理。";
        showToast("控制台已重新整理。", "success");
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

    const limit = elements.askLimit.value || "auto";
    setButtonLoading(elements.askSubmit, "生成中...");
    elements.answerPanel.innerHTML = renderLoadingInline("正在產生 GraphRAG 回答...");
    renderSources([]);
    renderWarnings([]);
    renderEvidenceGraph({ nodes: [], edges: [] });

    try {
        const result = await fetchJson("/api/graphrag/ask/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question, limit }),
        });
        const data = result.data || {};
        renderEvidenceGraph(data.contexts?.graph || {});
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

async function handleEvalSeed() {
    const questions = (elements.evalQuestions?.value || "")
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);
    if (!questions.length) {
        showToast("請輸入至少一個評估問題。", "error");
        return;
    }

    const limit = elements.evalLimit?.value || "auto";
    setButtonLoading(elements.evalSeedButton, "產生中...");
    elements.evalSummary.innerHTML = renderLoadingInline("正在產生候選 golden cases...");
    elements.evalResults.innerHTML = "";

    try {
        const result = await fetchJson("/api/graphrag/eval/seed/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ questions, limit }),
        });
        currentEvalCases = result.data?.cases || [];
        renderEvalCases(currentEvalCases);
        showToast(result.message || "候選案例已產生。", "success");
    } catch (error) {
        elements.evalSummary.innerHTML = renderErrorBlock(error.message);
        showToast(error.message, "error");
    } finally {
        restoreButton(elements.evalSeedButton, '<i data-lucide="wand-sparkles"></i><span>產生候選</span>');
    }
}

async function handleEvalRun() {
    if (!currentEvalCases.length) {
        showToast("請先產生候選案例。", "error");
        return;
    }
    setButtonLoading(elements.evalRunButton, "評估中...");
    elements.evalSummary.innerHTML = renderLoadingInline("正在執行 GraphRAG 回歸評估...");

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
        showToast("請先勾選要保存的正確案例。", "error");
        return;
    }
    setButtonLoading(elements.evalSaveButton, "保存中...");
    elements.evalSummary.innerHTML = renderLoadingInline(`正在保存 ${approvedCases.length} 題 golden cases...`);

    try {
        const result = await fetchJson("/api/graphrag/eval/save/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cases: approvedCases }),
        });
        const data = result.data || {};
        elements.evalSummary.innerHTML = renderSaveSummary(data);
        showToast(result.message || "Golden cases 已保存。", "success");
    } catch (error) {
        elements.evalSummary.innerHTML = renderErrorBlock(error.message);
        showToast(error.message, "error");
    } finally {
        restoreButton(elements.evalSaveButton, '<i data-lucide="save"></i><span>保存已確認</span>');
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

function renderEvalCases(cases) {
    if (!elements.evalSummary || !elements.evalResults) {
        return;
    }
    if (!cases.length) {
        elements.evalSummary.innerHTML = "尚未產生評估案例。";
        elements.evalResults.innerHTML = renderEmptyBlock("沒有候選案例。");
        renderIcons();
        return;
    }
    const consistentCount = cases.filter((item) => item.observed?.evidence_consistency?.is_consistent).length;
    const approvedCount = cases.filter((item) => item.enabled || item.review_status === "approved").length;
    elements.evalSummary.innerHTML = `
        <div class="compact-list">
            <div class="compact-list-row"><strong>候選案例</strong><span>${cases.length}</span></div>
            <div class="compact-list-row"><strong>證據一致</strong><span>${consistentCount}/${cases.length}</span></div>
            <div class="compact-list-row"><strong>已確認</strong><span>${approvedCount}/${cases.length}</span></div>
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
                    <span class="related-meta d-block">${checked ? "approved" : "needs_review"}</span>
                </span>
            </label>
            <div class="related-meta">
                ${escapeHtml(caseItem.id || "-")} | route ${escapeHtml(route)} | ${consistency.is_consistent ? "consistent" : "inconsistent"}
            </div>
            <div class="related-body">${escapeHtml(truncateText(caseItem.observed?.answer || "-", 220))}</div>
            <div class="related-reasons">
                ${renderChipGroup("items", expectedItems)}
                ${renderChipGroup("meetings", expectedMeetings)}
                ${renderChipGroup("relations", expectedRelations)}
            </div>
        </article>
    `;
}

function renderEvalReport(report) {
    const summary = report.summary || {};
    const results = report.results || [];
    elements.evalSummary.innerHTML = `
        <div class="compact-list">
            <div class="compact-list-row"><strong>Passed</strong><span>${escapeHtml(String(summary.passed || 0))}</span></div>
            <div class="compact-list-row"><strong>Failed</strong><span>${escapeHtml(String(summary.failed || 0))}</span></div>
            <div class="compact-list-row"><strong>Skipped</strong><span>${escapeHtml(String(summary.skipped || 0))}</span></div>
            <div class="compact-list-row"><strong>Enabled</strong><span>${escapeHtml(String(summary.enabled || 0))}</span></div>
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
            <div class="compact-list-row"><strong>Saved</strong><span>${escapeHtml(String(data.saved || 0))}</span></div>
            <div class="compact-list-row"><strong>Created</strong><span>${escapeHtml(String(data.created || 0))}</span></div>
            <div class="compact-list-row"><strong>Updated</strong><span>${escapeHtml(String(data.updated || 0))}</span></div>
            <div class="compact-list-row"><strong>Skipped</strong><span>${escapeHtml(String(data.skipped || 0))}</span></div>
            <div class="compact-list-row"><strong>File</strong><span>${escapeHtml(data.path || "-")}</span></div>
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
            ${failures.length ? `<div class="related-body">${failures.map((failure) => escapeHtml(failure)).join("<br>")}</div>` : '<div class="related-body">通過。</div>'}
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
                <span>閱讀</span>
            </button>
        </div>
        <div class="answer-body">${renderMarkdownAnswer(data.answer || "-", graph.nodes || [])}</div>
        <div class="score-grid score-grid-inline mt-3">
            <div class="score-pill"><span class="score-pill-label">Structured</span><span class="score-pill-value">${escapeHtml(String(data.contexts?.structured?.length || 0))}</span></div>
            <div class="score-pill"><span class="score-pill-label">Graph</span><span class="score-pill-value">${escapeHtml(formatGraphEvidenceCount(data.contexts?.graph || {}))}</span></div>
            <div class="score-pill"><span class="score-pill-label">Semantic</span><span class="score-pill-value">${escapeHtml(String(data.contexts?.semantic?.length || 0))}</span></div>
            <div class="score-pill"><span class="score-pill-label">Scope</span><span class="score-pill-value">${escapeHtml(formatAnswerScope(data))}</span></div>
        </div>
        ${renderTraceSummary(data.trace)}
    `;
}

function formatAnswerScope(data) {
    const limit = data.limit || "-";
    const mode = String(data.limit_mode || "").replace("auto:", "");
    return mode ? `${limit} ${mode}` : String(limit);
}

function renderEvidenceGraph(graph) {
    const graphElement = document.getElementById("evidence-graph");
    const emptyElement = document.getElementById("evidence-graph-empty");
    const countElement = document.getElementById("evidence-graph-count");
    const legendElement = document.getElementById("graph-legend");
    const detailElement = document.getElementById("graph-detail-panel");
    const nodes = graph.nodes || [];
    const edges = graph.edges || [];
    const summary = graph.summary || {};
    evidenceGraphData = { nodes, edges, summary };
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

    if (!nodes.length || !edges.length) {
        graphElement.classList.add("d-none");
        emptyElement.classList.remove("d-none");
        emptyElement.textContent = "No graph evidence for this answer.";
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
    const visible = Number(summary.visible_paths ?? graph?.paths?.length ?? 0);
    const total = Number(summary.total_paths ?? graph?.paths?.length ?? visible);
    if (!Number.isFinite(total) || total <= 0) {
        return "0";
    }
    return visible === total ? String(total) : `${visible}/${total}`;
}

function graphEvidenceTitle(summary, nodes, edges) {
    const total = Number(summary?.total_paths || 0);
    const visible = Number(summary?.visible_paths || 0);
    const hidden = Number(summary?.hidden_paths || 0);
    const mode = summary?.selection_mode || "unknown";
    return `${visible}/${total || visible} evidence paths, ${hidden} hidden, ${nodes.length} nodes, ${edges.length} edges, ${mode}`;
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
            type: "Relationship",
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
            <span>${escapeHtml(detail.type || "Detail")}</span>
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
    `;
    container.querySelector("[data-graph-detail-close]")?.addEventListener("click", () => {
        container.classList.add("d-none");
    });
    renderIcons();
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

function truncateText(value, maxLength) {
    const text = String(value ?? "");
    if (text.length <= maxLength) {
        return text;
    }
    return `${text.slice(0, Math.max(maxLength - 1, 0))}…`;
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
