const state = {
    meetings: {
        selectedMeetingId: null,
        filters: { keyword: "", meeting_name: "", date_from: "", date_to: "", responsible_unit: "" },
    },
    items: {
        filters: { keyword: "", owner: "", planned_date: "", meeting_id: "" },
    },
};

const elements = {
    refreshButton: document.getElementById("refresh-button"),
    toastElement: document.getElementById("status-toast"),
    toastBody: document.getElementById("status-toast-body"),
    meetingFilterForm: document.getElementById("meeting-filter-form"),
    meetingList: document.getElementById("meeting-list"),
    meetingDetailEmpty: document.getElementById("meeting-detail-empty"),
    meetingDetailContent: document.getElementById("meeting-detail-content"),
    meetingDetailItems: document.getElementById("meeting-detail-items"),
    meetingItemsCount: document.getElementById("meeting-items-count"),
    itemFilterForm: document.getElementById("item-filter-form"),
    meetingItemsList: document.getElementById("meeting-items-list"),
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
    pageCount: document.getElementById("meeting-detail-page-count"),
    attendees: document.getElementById("meeting-detail-attendees"),
};

const toast = new bootstrap.Toast(elements.toastElement, { delay: 2800 });

init();

function init() {
    bindEvents();
    hydrateFromQueryString();
    resetMeetingDetailPanel();
    loadMeetingMinutes();
    loadMeetingItems();
    renderIcons();
}

function bindEvents() {
    elements.refreshButton.addEventListener("click", handleRefreshAll);
    elements.meetingFilterForm.addEventListener("input", debounce(handleMeetingFilterChange, 300));
    elements.meetingFilterForm.addEventListener("change", handleMeetingFilterChange);
    elements.itemFilterForm.addEventListener("input", debounce(handleItemFilterChange, 300));
    elements.itemFilterForm.addEventListener("change", handleItemFilterChange);
}

function hydrateFromQueryString() {
    const params = new URLSearchParams(window.location.search);
    const meetingId = params.get("meeting_id");
    if (meetingId) {
        state.meetings.selectedMeetingId = meetingId;
        state.items.filters.meeting_id = meetingId;
        elements.itemFilterForm.elements.meeting_id.value = meetingId;
    }
}

function handleRefreshAll() {
    loadMeetingMinutes();
    loadMeetingItems();
    if (state.meetings.selectedMeetingId) loadMeetingDetail(state.meetings.selectedMeetingId);
}

function handleMeetingFilterChange() {
    const formData = new FormData(elements.meetingFilterForm);
    state.meetings.filters.keyword = String(formData.get("keyword") || "").trim();
    state.meetings.filters.meeting_name = String(formData.get("meeting_name") || "").trim();
    state.meetings.filters.date_from = String(formData.get("date_from") || "").trim();
    state.meetings.filters.date_to = String(formData.get("date_to") || "").trim();
    state.meetings.filters.responsible_unit = String(formData.get("responsible_unit") || "").trim();
    loadMeetingMinutes();
}

async function loadMeetingMinutes() {
    elements.meetingList.innerHTML = renderLoadingState("載入會議中...");
    try {
        const params = new URLSearchParams();
        Object.entries(state.meetings.filters).forEach(([key, value]) => {
            if (value) params.set(key, value);
        });
        const query = params.toString();
        const result = await fetchJson(`/api/meeting-minutes/${query ? `?${query}` : ""}`);
        renderMeetingList(result.data.meeting_minutes || []);
        if (state.meetings.selectedMeetingId) {
            const hasSelected = (result.data.meeting_minutes || []).some((item) => item.meeting_id === state.meetings.selectedMeetingId);
            if (hasSelected) {
                loadMeetingDetail(state.meetings.selectedMeetingId);
            } else {
                resetMeetingDetailPanel();
            }
        }
    } catch (error) {
        elements.meetingList.innerHTML = renderEmptyState("載入失敗", error.message);
        showToast(error.message, "error");
    }
}

function renderMeetingList(meetings) {
    if (!meetings.length) {
        elements.meetingList.innerHTML = renderEmptyState("沒有會議", "目前查無符合條件的會議記錄。");
        renderIcons();
        return;
    }
    elements.meetingList.innerHTML = meetings.map((meeting) => {
        const activeClass = meeting.meeting_id === state.meetings.selectedMeetingId ? "active" : "";
        return `
            <article class="document-card ${activeClass}" data-meeting-id="${escapeHtml(meeting.meeting_id)}">
                <div class="document-card-head">
                    <div class="document-card-main">
                        <h3 class="document-card-title">${escapeHtml(meeting.meeting_name || "-")}</h3>
                        <p class="document-card-meta">${escapeHtml(meeting.meeting_date || "-")} | ${escapeHtml(meeting.responsible_unit || "-")}</p>
                    </div>
                    <span class="badge rounded-pill text-bg-light border document-status-badge">${escapeHtml(meeting.status || "parsed")}</span>
                </div>
                <p class="document-card-meta mb-1">Meeting ID：${escapeHtml(meeting.meeting_id)}</p>
                <p class="document-card-meta mb-0">文件：${escapeHtml(meeting.document_id || "-")}</p>
            </article>
        `;
    }).join("");
    elements.meetingList.querySelectorAll("[data-meeting-id]").forEach((card) => {
        card.addEventListener("click", () => {
            state.meetings.selectedMeetingId = card.dataset.meetingId;
            state.items.filters.meeting_id = card.dataset.meetingId;
            elements.itemFilterForm.elements.meeting_id.value = card.dataset.meetingId;
            loadMeetingDetail(card.dataset.meetingId);
            loadMeetingItems();
            highlightMeetingCard();
        });
    });
    renderIcons();
}

async function loadMeetingDetail(meetingId) {
    try {
        const result = await fetchJson(`/api/meeting-minutes/${meetingId}/`);
        state.meetings.selectedMeetingId = meetingId;
        renderMeetingDetail(result.data.meeting_minutes, result.data.meeting_items || []);
        highlightMeetingCard();
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
    meetingDetailFields.pageCount.textContent = meeting.page_count ?? "-";
    meetingDetailFields.attendees.textContent = Array.isArray(meeting.attendees) && meeting.attendees.length ? meeting.attendees.join(", ") : "-";
    elements.meetingItemsCount.textContent = `${items.length} 筆`;
    elements.meetingDetailItems.innerHTML = items.length
        ? items.map(renderMeetingItemRow).join("")
        : '<tr><td colspan="6" class="text-center text-muted py-4">這場會議目前沒有解析到任何項目。</td></tr>';
}

function renderMeetingItemRow(item) {
    return `
        <tr>
            <td>${escapeHtml(item.item_no || "-")}</td>
            <td class="text-break">${escapeHtml(item.content || "-")}</td>
            <td>${escapeHtml(item.owner || "-")}</td>
            <td>${escapeHtml(item.planned_date || "-")}</td>
            <td>${escapeHtml(item.actual_completed_date || "-")}</td>
            <td class="text-break">${escapeHtml(item.tracking_result || "-")}</td>
        </tr>
    `;
}

function resetMeetingDetailPanel() {
    elements.meetingDetailEmpty.classList.remove("d-none");
    elements.meetingDetailContent.classList.add("d-none");
    elements.meetingDetailItems.innerHTML = "";
    highlightMeetingCard();
}

function highlightMeetingCard() {
    elements.meetingList.querySelectorAll("[data-meeting-id]").forEach((card) => {
        card.classList.toggle("active", card.dataset.meetingId === state.meetings.selectedMeetingId);
    });
}

function handleItemFilterChange() {
    const formData = new FormData(elements.itemFilterForm);
    state.items.filters.keyword = String(formData.get("keyword") || "").trim();
    state.items.filters.owner = String(formData.get("owner") || "").trim();
    state.items.filters.planned_date = String(formData.get("planned_date") || "").trim();
    state.items.filters.meeting_id = String(formData.get("meeting_id") || "").trim();
    loadMeetingItems();
}

async function loadMeetingItems() {
    elements.meetingItemsList.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-4">載入中...</td></tr>';
    try {
        const params = new URLSearchParams();
        Object.entries(state.items.filters).forEach(([key, value]) => {
            if (value) params.set(key, value);
        });
        const query = params.toString();
        const result = await fetchJson(`/api/meeting-items/${query ? `?${query}` : ""}`);
        renderMeetingItemsTable(result.data.meeting_items || []);
    } catch (error) {
        elements.meetingItemsList.innerHTML = `<tr><td colspan="6" class="text-center text-danger py-4">${escapeHtml(error.message)}</td></tr>`;
        showToast(error.message, "error");
    }
}

function renderMeetingItemsTable(items) {
    elements.meetingItemsList.innerHTML = items.length
        ? items.map((item) => `
            <tr>
                <td class="text-break">
                    <button type="button" class="btn btn-link btn-sm px-0 item-link" data-item-meeting-id="${escapeHtml(item.meeting_id || "")}">
                        ${escapeHtml(item.meeting_id || "-")}
                    </button>
                </td>
                <td>${escapeHtml(item.item_no || "-")}</td>
                <td class="text-break">${escapeHtml(item.content || "-")}</td>
                <td>${escapeHtml(item.owner || "-")}</td>
                <td>${escapeHtml(item.planned_date || "-")}</td>
                <td>${escapeHtml(String(item.page_number ?? "-"))}</td>
            </tr>
        `).join("")
        : '<tr><td colspan="6" class="text-center text-muted py-4">目前沒有符合條件的會議項目。</td></tr>';
    elements.meetingItemsList.querySelectorAll(".item-link").forEach((button) => {
        button.addEventListener("click", () => {
            const meetingId = button.dataset.itemMeetingId;
            if (!meetingId) return;
            state.meetings.selectedMeetingId = meetingId;
            loadMeetingDetail(meetingId);
            highlightMeetingCard();
        });
    });
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
