const state = {
    search: {
        searchId: null,
        page: 1,
        limit: 10,
        total: 0,
        expandedKeywords: [],
        filters: {
            q: "",
            date_from: "",
            date_to: "",
            responsible_unit: "",
            owner: "",
            chairperson: "",
            has_owner: "",
            has_planned_date: "",
            is_completed: "",
            has_tracking_result: "",
            status: "",
            sort_by: "final_score",
        },
    },
    selectedMeetingId: null,
    selectedItemId: null,
};

const elements = {
    refreshButton: document.getElementById("refresh-button"),
    toastElement: document.getElementById("status-toast"),
    toastBody: document.getElementById("status-toast-body"),
    searchForm: document.getElementById("search-form"),
    searchSubmit: document.getElementById("search-submit"),
    searchSummary: document.getElementById("search-summary"),
    searchResults: document.getElementById("search-results"),
    searchPrevPage: document.getElementById("search-prev-page"),
    searchNextPage: document.getElementById("search-next-page"),
    graphKeywords: document.getElementById("graph-keywords"),
    meetingDetailEmpty: document.getElementById("meeting-detail-empty"),
    meetingDetailContent: document.getElementById("meeting-detail-content"),
    meetingDetailItems: document.getElementById("meeting-detail-items"),
    meetingItemsCount: document.getElementById("meeting-items-count"),
    openMeetingsLink: document.getElementById("open-meetings-link"),
    relatedMeetings: document.getElementById("related-meetings"),
    relatedItems: document.getElementById("related-items"),
    statsPanel: document.getElementById("search-stats"),
};

const meetingDetailFields = {
    name: document.getElementById("meeting-detail-name"),
    id: document.getElementById("meeting-detail-id"),
    documentId: document.getElementById("meeting-detail-document-id"),
    date: document.getElementById("meeting-detail-date"),
    time: document.getElementById("meeting-detail-time"),
    location: document.getElementById("meeting-detail-location"),
    chairperson: document.getElementById("meeting-detail-chairperson"),
    recorder: document.getElementById("meeting-detail-recorder"),
    unit: document.getElementById("meeting-detail-unit"),
    attendees: document.getElementById("meeting-detail-attendees"),
};

const FIELD_LABELS = {
    meeting_name: "會議名稱",
    location: "地點",
    chairperson: "主席",
    recorder: "記錄",
    responsible_unit: "權責單位",
    attendees: "出席人員",
    item_content: "會議內容",
    content: "會議內容",
    owner: "負責人",
    planned_date: "預計日期",
    actual_completed_date: "實際完成日",
    tracking_result: "追蹤結果",
};

const SCORE_LABELS = {
    keyword_score: "關鍵字",
    structure_score: "結構",
    task_score: "任務",
    recency_score: "日期",
    feedback_score: "回饋",
    graph_score: "圖譜",
};

const toast = new bootstrap.Toast(elements.toastElement, { delay: 2800 });

init();

function init() {
    bindEvents();
    hydrateDefaults();
    resetMeetingDetailPanel();
    renderGraphKeywords([]);
    loadSearchResults();
    loadSearchStats();
    renderIcons();
}

function bindEvents() {
    elements.refreshButton?.addEventListener("click", () => {
        loadSearchResults();
        loadSearchStats();
        if (state.selectedMeetingId) {
            loadMeetingDetail(state.selectedMeetingId, state.selectedItemId);
        }
    });

    elements.searchForm?.addEventListener("submit", handleSearchSubmit);
    elements.searchPrevPage?.addEventListener("click", () => changeSearchPage(-1));
    elements.searchNextPage?.addEventListener("click", () => changeSearchPage(1));
}

function hydrateDefaults() {
    const formData = new FormData(elements.searchForm);
    state.search.limit = Math.max(parseInt(formData.get("limit") || "10", 10) || 10, 1);
    state.search.filters.sort_by = String(formData.get("sort_by") || "final_score");
}

function handleSearchSubmit(event) {
    event.preventDefault();
    collectFiltersFromForm();
    state.search.page = 1;
    loadSearchResults();
}

function collectFiltersFromForm() {
    const formData = new FormData(elements.searchForm);
    Object.keys(state.search.filters).forEach((key) => {
        state.search.filters[key] = String(formData.get(key) || "").trim();
    });
    state.search.limit = Math.max(parseInt(formData.get("limit") || "10", 10) || 10, 1);
}

function changeSearchPage(direction) {
    const totalPages = Math.max(1, Math.ceil(state.search.total / state.search.limit));
    const nextPage = state.search.page + direction;
    if (nextPage < 1 || nextPage > totalPages) return;
    state.search.page = nextPage;
    loadSearchResults();
}

async function loadSearchResults() {
    elements.searchResults.innerHTML = renderLoadingState("搜尋中...");
    elements.searchSubmit.disabled = true;

    try {
        const params = new URLSearchParams({ page: String(state.search.page), limit: String(state.search.limit) });
        Object.entries(state.search.filters).forEach(([key, value]) => {
            if (value) params.set(key, value);
        });

        const result = await fetchJson(`/api/search/meeting-minutes/?${params.toString()}`);
        state.search.searchId = result.data.search_id || null;
        state.search.total = result.data.total || 0;
        state.search.expandedKeywords = Array.isArray(result.data.expanded_keywords_from_graph)
            ? result.data.expanded_keywords_from_graph
            : [];

        if (!state.search.expandedKeywords.length && state.search.filters.q) {
            state.search.expandedKeywords = await fetchExpandedKeywords(state.search.filters.q);
        }

        renderSearchSummary(result.data);
        renderGraphKeywords(state.search.expandedKeywords);
        renderSearchResults(result.data.results || []);
        updateSearchPagination();
    } catch (error) {
        elements.searchSummary.textContent = "搜尋失敗。";
        elements.searchResults.innerHTML = renderEmptyState("搜尋失敗", error.message);
        renderGraphKeywords([]);
        showToast(error.message, "error");
    } finally {
        elements.searchSubmit.disabled = false;
    }
}

async function fetchExpandedKeywords(query) {
    try {
        const result = await fetchJson(`/api/graph/keyword/${encodeURIComponent(query)}/related/`);
        return Array.isArray(result.data.related_keywords)
            ? result.data.related_keywords.map((item) => item.keyword).filter(Boolean)
            : [];
    } catch (_error) {
        return [];
    }
}

function renderSearchSummary(data) {
    const totalPages = Math.max(1, Math.ceil((data.total || 0) / state.search.limit));
    const queryText = data.query ? `關鍵字：${data.query}` : "全部會議";
    const graphText = state.search.expandedKeywords.length
        ? `｜圖譜擴展：${state.search.expandedKeywords.join("、")}`
        : "";
    elements.searchSummary.textContent = `${queryText}｜共 ${data.total || 0} 筆｜第 ${state.search.page} / ${totalPages} 頁${graphText}`;
}

function updateSearchPagination() {
    const totalPages = Math.max(1, Math.ceil(state.search.total / state.search.limit));
    elements.searchPrevPage.disabled = state.search.page <= 1;
    elements.searchNextPage.disabled = state.search.page >= totalPages;
}

function renderGraphKeywords(keywords) {
    if (!keywords.length) {
        elements.graphKeywords.innerHTML = '<div class="related-empty">目前沒有從圖譜擴展出其他關鍵字。</div>';
        return;
    }

    elements.graphKeywords.innerHTML = keywords.map((keyword) => `
        <button type="button" class="related-card graph-keyword-card" data-graph-keyword="${escapeHtml(keyword)}">
            <div class="related-title">${escapeHtml(keyword)}</div>
            <div class="related-meta">點擊查看此詞的關聯關鍵字</div>
        </button>
    `).join("");

    elements.graphKeywords.querySelectorAll("[data-graph-keyword]").forEach((button) => {
        button.addEventListener("click", async () => {
            const keyword = button.dataset.graphKeyword;
            await loadGraphKeywordRelated(keyword);
        });
    });
}

async function loadGraphKeywordRelated(keyword) {
    try {
        const result = await fetchJson(`/api/graph/keyword/${encodeURIComponent(keyword)}/related/`);
        const related = Array.isArray(result.data.related_keywords) ? result.data.related_keywords : [];
        if (!related.length) {
            showToast(`${keyword} 沒有更多圖譜關聯詞。`, "success");
            return;
        }

        elements.graphKeywords.innerHTML = related.map((item) => `
            <div class="related-card related-card-static">
                <div class="related-title">${escapeHtml(item.keyword)}</div>
                <div class="related-meta">權重 ${escapeHtml(formatScore(item.weight))}｜共現 ${escapeHtml(String(item.count || 0))} 次</div>
            </div>
        `).join("");
    } catch (error) {
        showToast(error.message, "error");
    }
}

function renderSearchResults(results) {
    if (!results.length) {
        elements.searchResults.innerHTML = renderEmptyState("沒有搜尋結果", "請調整關鍵字或篩選條件後再試一次。");
        renderIcons();
        return;
    }

    elements.searchResults.innerHTML = results.map((result) => renderSearchResultCard(result)).join("");

    elements.searchResults.querySelectorAll(".search-result-main").forEach((button) => {
        button.addEventListener("click", async () => {
            const meetingId = button.dataset.searchMeetingId;
            await logSearchClick({ meeting_id: meetingId, document_id: button.dataset.searchDocumentId });
            if (meetingId) loadMeetingDetail(meetingId);
        });
    });

    elements.searchResults.querySelectorAll(".search-item-match").forEach((button) => {
        button.addEventListener("click", async () => {
            const meetingId = button.dataset.searchMeetingId;
            const itemId = button.dataset.searchItemId || null;
            await logSearchClick({
                meeting_id: meetingId,
                item_id: itemId,
                document_id: button.dataset.searchDocumentId,
            });
            if (meetingId) loadMeetingDetail(meetingId, itemId);
        });
    });
}

function renderSearchResultCard(result) {
    const matchedFields = Array.isArray(result.matched_fields) && result.matched_fields.length
        ? result.matched_fields.map((field) => `<span class="search-chip">${escapeHtml(FIELD_LABELS[field] || field)}</span>`).join("")
        : '<span class="search-chip">沒有欄位命中資訊</span>';

    const snippets = renderSnippetList(result.matched_snippets || []);
    const matchedItems = renderMatchedItems(result);
    const scoreDetail = renderScoreDetail(result.score_detail, false);
    const graphScore = Number(result.score_detail?.graph_score || 0);

    return `
        <article class="search-result-card">
            <button type="button" class="search-result-main" data-search-meeting-id="${escapeHtml(result.meeting_id)}" data-search-document-id="${escapeHtml(result.document_id || "")}">
                <div class="search-result-head">
                    <div class="search-result-copy">
                        <h3 class="search-result-title">${escapeHtml(result.meeting_name || "-")}</h3>
                        <div class="search-result-meta">${escapeHtml(result.meeting_date || "-")}｜${escapeHtml(result.responsible_unit || "-")}</div>
                    </div>
                    <div class="search-score-stack">
                        <div class="search-score-badge">總分 ${escapeHtml(formatScore(result.final_score))}</div>
                        ${graphScore ? `<div class="search-score-subbadge">圖譜 +${escapeHtml(formatScore(graphScore))}</div>` : ""}
                    </div>
                </div>
                <div class="search-result-submeta">Meeting ID：${escapeHtml(result.meeting_id || "-")}｜文件：${escapeHtml(result.document_id || "-")}</div>
            </button>

            <div class="search-field-row">${matchedFields}</div>
            ${snippets}
            ${matchedItems}

            <details class="result-detail-toggle">
                <summary>查看分數來源</summary>
                <div class="score-grid score-grid-card">${scoreDetail}</div>
            </details>
        </article>
    `;
}

function renderSnippetList(snippets) {
    if (!Array.isArray(snippets) || !snippets.length) {
        return "";
    }

    return `
        <div class="search-snippet-list">
            ${snippets.slice(0, 2).map((snippet) => `
                <div class="search-snippet">
                    <div class="search-snippet-label">${escapeHtml(FIELD_LABELS[snippet.field] || snippet.field)}</div>
                    <div class="search-snippet-body">${snippet.snippet || "-"}</div>
                </div>
            `).join("")}
        </div>
    `;
}

function renderMatchedItems(result) {
    const items = Array.isArray(result.matched_items) ? result.matched_items : [];
    if (!items.length) {
        return '<div class="search-item-list"><div class="text-muted small">沒有命中的會議項目。</div></div>';
    }

    const previewItems = items.slice(0, 2);
    const hiddenCount = Math.max(items.length - previewItems.length, 0);

    return `
        <div class="search-item-list">
            ${previewItems.map((item) => `
                <button type="button" class="search-item-match" data-search-meeting-id="${escapeHtml(result.meeting_id)}" data-search-item-id="${escapeHtml(item.item_id || "")}" data-search-document-id="${escapeHtml(result.document_id || "")}">
                    <div class="search-item-top">
                        <span>項次 #${escapeHtml(item.item_no || "-")}</span>
                        <span>分數 ${escapeHtml(formatScore(item.final_score))}</span>
                    </div>
                    <div class="search-item-body">${escapeHtml(item.content || "-")}</div>
                    <div class="search-item-meta">${escapeHtml(item.owner || "-")}｜${escapeHtml(item.planned_date || "-")}</div>
                </button>
            `).join("")}
            ${hiddenCount ? `<div class="search-hidden-note">另有 ${hiddenCount} 筆命中項目，請點開會議查看完整內容。</div>` : ""}
        </div>
    `;
}

function renderScoreDetail(detail, includeRecency = true) {
    if (!detail) return "";
    const keys = includeRecency
        ? ["keyword_score", "structure_score", "task_score", "recency_score", "feedback_score", "graph_score"]
        : ["keyword_score", "structure_score", "task_score", "feedback_score", "graph_score"];

    return keys.map((key) => `
        <div class="score-pill">
            <span class="score-pill-label">${SCORE_LABELS[key]}</span>
            <span class="score-pill-value">${escapeHtml(formatScore(detail[key] ?? 0))}</span>
        </div>
    `).join("");
}

async function logSearchClick({ meeting_id, item_id = null, document_id = null }) {
    if (!state.search.searchId || !meeting_id) return;
    try {
        await fetchJson("/api/search/click/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ search_id: state.search.searchId, meeting_id, item_id, document_id }),
        });
    } catch (error) {
        console.error("search click log failed", error);
    }
}

async function loadMeetingDetail(meetingId, itemId = null) {
    try {
        const [meetingResult, relatedMeetingsResult, relatedItemsResult] = await Promise.all([
            fetchJson(`/api/meeting-minutes/${meetingId}/`),
            fetchJson(`/api/search/related-meetings/${meetingId}/`),
            itemId ? fetchJson(`/api/search/related-items/${itemId}/`) : Promise.resolve({ data: { related_items: [] } }),
        ]);

        state.selectedMeetingId = meetingId;
        state.selectedItemId = itemId;
        renderMeetingDetail(meetingResult.data.meeting_minutes, meetingResult.data.meeting_items || []);
        renderRelatedMeetings(relatedMeetingsResult.data.related_meetings || []);
        renderRelatedItems(relatedItemsResult.data.related_items || []);
        elements.openMeetingsLink.href = `/meetings/?meeting_id=${encodeURIComponent(meetingId)}`;
    } catch (error) {
        showToast(error.message, "error");
    }
}

function renderMeetingDetail(meeting, items) {
    elements.meetingDetailEmpty.classList.add("d-none");
    elements.meetingDetailContent.classList.remove("d-none");

    meetingDetailFields.name.textContent = meeting.meeting_name || "-";
    meetingDetailFields.id.textContent = meeting.meeting_id || "-";
    meetingDetailFields.documentId.textContent = meeting.document_id || "-";
    meetingDetailFields.date.textContent = meeting.meeting_date || "-";
    meetingDetailFields.time.textContent = [meeting.start_time, meeting.end_time].filter(Boolean).join(" - ") || "-";
    meetingDetailFields.location.textContent = meeting.location || "-";
    meetingDetailFields.chairperson.textContent = meeting.chairperson || "-";
    meetingDetailFields.recorder.textContent = meeting.recorder || "-";
    meetingDetailFields.unit.textContent = meeting.responsible_unit || "-";
    meetingDetailFields.attendees.textContent = Array.isArray(meeting.attendees) && meeting.attendees.length ? meeting.attendees.join("、") : "-";

    elements.meetingItemsCount.textContent = `${items.length} 筆`;
    elements.meetingDetailItems.innerHTML = items.length
        ? items.map((item) => `
            <tr class="${state.selectedItemId && state.selectedItemId === item.item_id ? "table-primary" : ""}">
                <td>${escapeHtml(item.item_no || "-")}</td>
                <td class="text-break">${escapeHtml(item.content || "-")}</td>
                <td>${escapeHtml(item.owner || "-")}</td>
                <td>${escapeHtml(item.planned_date || "-")}</td>
                <td>${escapeHtml(item.actual_completed_date || "-")}</td>
                <td class="text-break">${escapeHtml(item.tracking_result || "-")}</td>
            </tr>
        `).join("")
        : '<tr><td colspan="6" class="text-center text-muted py-4">目前沒有會議項目資料。</td></tr>';
}

function renderRelatedMeetings(items) {
    if (!items.length) {
        elements.relatedMeetings.innerHTML = '<div class="related-empty">目前沒有找到相關會議。</div>';
        return;
    }

    elements.relatedMeetings.innerHTML = items.slice(0, 3).map((item) => `
        <button type="button" class="related-card" data-related-meeting-id="${escapeHtml(item.meeting_id || "")}">
            <div class="related-title">${escapeHtml(item.meeting_name || item.meeting_id || "-")}</div>
            <div class="related-meta">${escapeHtml(item.meeting_date || "-")}｜分數 ${escapeHtml(formatScore(item.score))}</div>
            <div class="related-reasons">${(item.reason || []).slice(0, 2).map((reason) => `<span class="search-chip">${escapeHtml(reason)}</span>`).join("")}</div>
        </button>
    `).join("");

    elements.relatedMeetings.querySelectorAll("[data-related-meeting-id]").forEach((button) => {
        button.addEventListener("click", () => loadMeetingDetail(button.dataset.relatedMeetingId));
    });
}

function renderRelatedItems(items) {
    if (!items.length) {
        elements.relatedItems.innerHTML = '<div class="related-empty">目前沒有找到相關項目。</div>';
        return;
    }

    elements.relatedItems.innerHTML = items.slice(0, 3).map((item) => `
        <div class="related-card related-card-static">
            <div class="related-title">項次 ${escapeHtml(item.item_no || "-")}｜${escapeHtml(item.meeting_name || "-")}</div>
            <div class="related-meta">${escapeHtml(item.owner || "-")}｜${escapeHtml(item.planned_date || "-")}｜分數 ${escapeHtml(formatScore(item.score))}</div>
            <div class="related-body">${escapeHtml(item.content || "-")}</div>
        </div>
    `).join("");
}

async function loadSearchStats() {
    elements.statsPanel.innerHTML = renderLoadingState("載入統計中...");
    try {
        const result = await fetchJson("/api/search/stats/");
        renderSearchStats(result.data);
    } catch (error) {
        elements.statsPanel.innerHTML = `<div class="related-empty">${escapeHtml(error.message)}</div>`;
    }
}

function renderSearchStats(data) {
    const topQueries = (data.top_queries || []).slice(0, 3);
    const recentSearches = (data.recent_searches || []).slice(0, 3);

    elements.statsPanel.innerHTML = `
        <div class="stats-grid">
            <div class="stat-mini-card">
                <div class="stat-label">搜尋次數</div>
                <div class="stat-value stat-value-sm">${escapeHtml(String(data.total_search_count ?? 0))}</div>
            </div>
            <div class="stat-mini-card">
                <div class="stat-label">點擊次數</div>
                <div class="stat-value stat-value-sm">${escapeHtml(String(data.total_click_count ?? 0))}</div>
            </div>
        </div>
        <details class="stats-collapse" open>
            <summary>熱門查詢</summary>
            ${renderCompactList(topQueries, (item) => `${escapeHtml(item.query)} <span>${escapeHtml(String(item.count))}</span>`)}
        </details>
        <details class="stats-collapse">
            <summary>最近搜尋</summary>
            ${renderCompactList(recentSearches, (item) => `${escapeHtml(item.query || "(空白查詢)")} <span>${escapeHtml(String(item.result_count ?? 0))}</span>`)}
        </details>
    `;
}

function renderCompactList(items, formatter) {
    if (!items.length) {
        return '<div class="compact-empty-row">目前沒有資料。</div>';
    }
    return `<div class="compact-list">${items.map((item) => `<div class="compact-list-row">${formatter(item)}</div>`).join("")}</div>`;
}

function resetMeetingDetailPanel() {
    elements.meetingDetailEmpty.classList.remove("d-none");
    elements.meetingDetailContent.classList.add("d-none");
    elements.meetingDetailItems.innerHTML = "";
    elements.relatedMeetings.innerHTML = "";
    elements.relatedItems.innerHTML = "";
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const result = await response.json();
    if (!response.ok || !result.success) {
        throw new Error(result.message || "系統發生錯誤。");
    }
    return result;
}

function showToast(message, type) {
    elements.toastBody.textContent = message;
    elements.toastElement.className = `toast align-items-center border-0 ${type === "error" ? "text-bg-danger" : "text-bg-success"}`;
    toast.show();
}

function renderLoadingState(message) {
    return `<div class="empty-state-shell compact-empty"><div class="spinner-border text-primary mb-3" role="status"></div><div class="fw-semibold">${escapeHtml(message)}</div></div>`;
}

function renderEmptyState(title, message) {
    return `<div class="empty-state-shell"><div class="empty-state-icon"><i data-lucide="file-search"></i></div><div class="fw-bold text-dark mb-1">${escapeHtml(title)}</div><div class="text-muted small">${escapeHtml(message)}</div></div>`;
}

function formatScore(value) {
    const numeric = Number(value || 0);
    return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(1);
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
    if (window.lucide) window.lucide.createIcons();
}
