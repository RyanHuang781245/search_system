const state = {
    search: {
        searchId: null,
        page: 1,
        limit: 10,
        total: 0,
        filters: {
            q: "",
            date_from: "",
            date_to: "",
            responsible_unit: "",
            owner: "",
            chairperson: "",
            status: "",
        },
    },
    selectedMeetingId: null,
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
    meetingDetailEmpty: document.getElementById("meeting-detail-empty"),
    meetingDetailContent: document.getElementById("meeting-detail-content"),
    meetingDetailItems: document.getElementById("meeting-detail-items"),
    meetingItemsCount: document.getElementById("meeting-items-count"),
    openMeetingsLink: document.getElementById("open-meetings-link"),
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

const toast = new bootstrap.Toast(elements.toastElement, { delay: 2800 });

init();

function init() {
    bindEvents();
    resetMeetingDetailPanel();
    loadSearchResults();
    renderIcons();
}

function bindEvents() {
    elements.refreshButton.addEventListener("click", loadSearchResults);
    elements.searchForm.addEventListener("input", debounce(handleSearchFilterChange, 300));
    elements.searchForm.addEventListener("change", handleSearchFilterChange);
    elements.searchForm.addEventListener("submit", handleSearchSubmit);
    elements.searchPrevPage.addEventListener("click", () => changeSearchPage(-1));
    elements.searchNextPage.addEventListener("click", () => changeSearchPage(1));
}

function handleSearchFilterChange() {
    const formData = new FormData(elements.searchForm);
    state.search.filters.q = String(formData.get("q") || "").trim();
    state.search.filters.date_from = String(formData.get("date_from") || "").trim();
    state.search.filters.date_to = String(formData.get("date_to") || "").trim();
    state.search.filters.responsible_unit = String(formData.get("responsible_unit") || "").trim();
    state.search.filters.owner = String(formData.get("owner") || "").trim();
    state.search.filters.chairperson = String(formData.get("chairperson") || "").trim();
    state.search.filters.status = String(formData.get("status") || "").trim();
    state.search.limit = Math.max(parseInt(formData.get("limit") || "10", 10) || 10, 1);
    state.search.page = 1;
    loadSearchResults();
}

function handleSearchSubmit(event) {
    event.preventDefault();
    handleSearchFilterChange();
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
        renderSearchSummary(result.data);
        renderSearchResults(result.data.results || []);
        updateSearchPagination();
    } catch (error) {
        elements.searchSummary.textContent = "搜尋失敗。";
        elements.searchResults.innerHTML = renderEmptyState("搜尋失敗", error.message);
        showToast(error.message, "error");
    } finally {
        elements.searchSubmit.disabled = false;
    }
}

function renderSearchSummary(data) {
    const totalPages = Math.max(1, Math.ceil((data.total || 0) / state.search.limit));
    const queryText = data.query ? `「${data.query}」` : "全部會議";
    elements.searchSummary.textContent = `${queryText}｜共 ${data.total || 0} 筆｜第 ${state.search.page} / ${totalPages} 頁`;
}

function updateSearchPagination() {
    const totalPages = Math.max(1, Math.ceil(state.search.total / state.search.limit));
    elements.searchPrevPage.disabled = state.search.page <= 1;
    elements.searchNextPage.disabled = state.search.page >= totalPages;
}

function renderSearchResults(results) {
    if (!results.length) {
        elements.searchResults.innerHTML = renderEmptyState("沒有搜尋結果", "請嘗試其他關鍵字，或放寬篩選條件。");
        renderIcons();
        return;
    }
    elements.searchResults.innerHTML = results.map((result) => {
        const matchedFields = Array.isArray(result.matched_fields) && result.matched_fields.length
            ? result.matched_fields.map((field) => `<span class="search-chip">${escapeHtml(FIELD_LABELS[field] || field)}</span>`).join("")
            : '<span class="search-chip">無直接欄位命中</span>';
        const matchedItems = Array.isArray(result.matched_items) && result.matched_items.length
            ? result.matched_items.map((item) => `
                <button type="button" class="search-item-match" data-search-meeting-id="${escapeHtml(result.meeting_id)}" data-search-item-id="${escapeHtml(item.item_id || "")}" data-search-document-id="${escapeHtml(result.document_id || "")}">
                    <div class="search-item-top"><span>項次 #${escapeHtml(item.item_no || "-")}</span><span>分數 ${escapeHtml(String(item.score ?? 0))}</span></div>
                    <div class="search-item-body">${escapeHtml(item.content || "-")}</div>
                    <div class="search-item-meta">${escapeHtml(item.owner || "-")} | ${escapeHtml(item.planned_date || "-")}</div>
                </button>
            `).join("")
            : '<div class="text-muted small">沒有命中的會議項目。</div>';
        return `
            <article class="search-result-card">
                <button type="button" class="search-result-main" data-search-meeting-id="${escapeHtml(result.meeting_id)}" data-search-document-id="${escapeHtml(result.document_id || "")}">
                    <div class="search-result-head">
                        <div>
                            <h3 class="search-result-title">${escapeHtml(result.meeting_name || "-")}</h3>
                            <div class="search-result-meta">${escapeHtml(result.meeting_date || "-")} | ${escapeHtml(result.responsible_unit || "-")}</div>
                        </div>
                        <div class="search-score-badge">分數 ${escapeHtml(String(result.score ?? 0))}</div>
                    </div>
                    <div class="search-result-submeta">Meeting ID：${escapeHtml(result.meeting_id || "-")} | 文件：${escapeHtml(result.document_id || "-")}</div>
                </button>
                <div class="search-field-row">${matchedFields}</div>
                <div class="search-item-list">${matchedItems}</div>
            </article>
        `;
    }).join("");
    elements.searchResults.querySelectorAll(".search-result-main").forEach((button) => {
        button.addEventListener("click", async () => {
            await logSearchClick({ meeting_id: button.dataset.searchMeetingId, document_id: button.dataset.searchDocumentId });
            if (button.dataset.searchMeetingId) loadMeetingDetail(button.dataset.searchMeetingId);
        });
    });
    elements.searchResults.querySelectorAll(".search-item-match").forEach((button) => {
        button.addEventListener("click", async () => {
            await logSearchClick({
                meeting_id: button.dataset.searchMeetingId,
                item_id: button.dataset.searchItemId,
                document_id: button.dataset.searchDocumentId,
            });
            if (button.dataset.searchMeetingId) loadMeetingDetail(button.dataset.searchMeetingId);
        });
    });
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
        console.error("記錄搜尋點擊失敗", error);
    }
}

async function loadMeetingDetail(meetingId) {
    try {
        const result = await fetchJson(`/api/meeting-minutes/${meetingId}/`);
        state.selectedMeetingId = meetingId;
        renderMeetingDetail(result.data.meeting_minutes, result.data.meeting_items || []);
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
    meetingDetailFields.attendees.textContent = Array.isArray(meeting.attendees) && meeting.attendees.length ? meeting.attendees.join(", ") : "-";
    elements.meetingItemsCount.textContent = `${items.length} 筆`;
    elements.meetingDetailItems.innerHTML = items.length
        ? items.map((item) => `
            <tr>
                <td>${escapeHtml(item.item_no || "-")}</td>
                <td class="text-break">${escapeHtml(item.content || "-")}</td>
                <td>${escapeHtml(item.owner || "-")}</td>
                <td>${escapeHtml(item.planned_date || "-")}</td>
                <td>${escapeHtml(item.actual_completed_date || "-")}</td>
                <td class="text-break">${escapeHtml(item.tracking_result || "-")}</td>
            </tr>
        `).join("")
        : '<tr><td colspan="6" class="text-center text-muted py-4">這場會議目前沒有解析到任何項目。</td></tr>';
}

function resetMeetingDetailPanel() {
    elements.meetingDetailEmpty.classList.remove("d-none");
    elements.meetingDetailContent.classList.add("d-none");
    elements.meetingDetailItems.innerHTML = "";
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const result = await response.json();
    if (!response.ok || !result.success) throw new Error(result.message || "請求失敗。");
    return result;
}

function showToast(message, type) {
    elements.toastBody.textContent = message;
    elements.toastElement.className = `toast align-items-center border-0 ${type === "error" ? "text-bg-danger" : "text-bg-success"}`;
    toast.show();
}

function renderLoadingState(message) {
    return `<div class="empty-state-shell"><div class="spinner-border text-primary mb-3" role="status"></div><div class="fw-semibold">${escapeHtml(message)}</div></div>`;
}

function renderEmptyState(title, message) {
    return `<div class="empty-state-shell"><div class="empty-state-icon"><i data-lucide="file-search"></i></div><div class="fw-bold text-dark mb-1">${escapeHtml(title)}</div><div class="text-muted small">${escapeHtml(message)}</div></div>`;
}

function debounce(callback, delay) {
    let timerId = null;
    return (...args) => {
        window.clearTimeout(timerId);
        timerId = window.setTimeout(() => callback(...args), delay);
    };
}

function escapeHtml(value) {
    return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

function renderIcons() {
    if (window.lucide) window.lucide.createIcons();
}
