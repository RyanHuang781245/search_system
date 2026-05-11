const state = {
    documents: {
        page: 1,
        limit: 10,
        total: 0,
        selectedDocumentId: null,
        filters: {
            keyword: "",
            doc_type: "",
            status: "",
        },
    },
    meetings: {
        selectedMeetingId: null,
        filters: {
            keyword: "",
            meeting_name: "",
            date_from: "",
            date_to: "",
            responsible_unit: "",
        },
    },
    items: {
        filters: {
            keyword: "",
            owner: "",
            planned_date: "",
            meeting_id: "",
        },
    },
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
};

const elements = {
    uploadForm: document.getElementById("upload-form"),
    fileInput: document.getElementById("file-input"),
    fileModifiedAt: document.getElementById("file-modified-at"),
    selectedFile: document.getElementById("selected-file"),
    uploadSubmit: document.getElementById("upload-submit"),
    refreshButton: document.getElementById("refresh-button"),
    filterForm: document.getElementById("filter-form"),
    documentList: document.getElementById("document-list"),
    pageIndicator: document.getElementById("page-indicator"),
    prevPage: document.getElementById("prev-page"),
    nextPage: document.getElementById("next-page"),
    emptyDetail: document.getElementById("empty-detail"),
    detailContent: document.getElementById("detail-content"),
    parseButton: document.getElementById("parse-button"),
    deleteButton: document.getElementById("delete-button"),
    parseResult: document.getElementById("parse-result"),
    parseResultBody: document.getElementById("parse-result-body"),
    dropzone: document.getElementById("dropzone"),
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
    searchForm: document.getElementById("search-form"),
    searchSubmit: document.getElementById("search-submit"),
    searchSummary: document.getElementById("search-summary"),
    searchResults: document.getElementById("search-results"),
    searchPrevPage: document.getElementById("search-prev-page"),
    searchNextPage: document.getElementById("search-next-page"),
};

const detailFields = {
    name: document.getElementById("detail-name"),
    id: document.getElementById("detail-id"),
    status: document.getElementById("detail-status"),
    docType: document.getElementById("detail-doc-type"),
    ext: document.getElementById("detail-ext"),
    size: document.getElementById("detail-size"),
    mime: document.getElementById("detail-mime"),
    fileModified: document.getElementById("detail-file-modified"),
    created: document.getElementById("detail-created"),
    updated: document.getElementById("detail-updated"),
    path: document.getElementById("detail-path"),
    description: document.getElementById("detail-description"),
    tags: document.getElementById("detail-tags"),
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
    resetDocumentDetailPanel();
    resetMeetingDetailPanel();
    loadDocuments();
    loadMeetingMinutes();
    loadMeetingItems();
    loadSearchResults();
    renderIcons();
}

function bindEvents() {
    elements.fileInput.addEventListener("change", handleFileSelection);
    elements.uploadForm.addEventListener("submit", handleUpload);
    elements.refreshButton.addEventListener("click", handleRefreshAll);
    elements.filterForm.addEventListener("input", debounce(handleDocumentFilterChange, 300));
    elements.filterForm.addEventListener("change", handleDocumentFilterChange);
    elements.prevPage.addEventListener("click", () => changePage(-1));
    elements.nextPage.addEventListener("click", () => changePage(1));
    elements.parseButton.addEventListener("click", handleParseMeetingMinutes);
    elements.deleteButton.addEventListener("click", handleDelete);
    elements.meetingFilterForm.addEventListener("input", debounce(handleMeetingFilterChange, 300));
    elements.meetingFilterForm.addEventListener("change", handleMeetingFilterChange);
    elements.itemFilterForm.addEventListener("input", debounce(handleItemFilterChange, 300));
    elements.itemFilterForm.addEventListener("change", handleItemFilterChange);
    elements.searchForm.addEventListener("input", debounce(handleSearchFilterChange, 300));
    elements.searchForm.addEventListener("change", handleSearchFilterChange);
    elements.searchForm.addEventListener("submit", handleSearchSubmit);
    elements.searchPrevPage.addEventListener("click", () => changeSearchPage(-1));
    elements.searchNextPage.addEventListener("click", () => changeSearchPage(1));

    elements.dropzone.addEventListener("dragover", (event) => {
        event.preventDefault();
        elements.dropzone.classList.add("is-dragover");
    });
    elements.dropzone.addEventListener("dragleave", () => {
        elements.dropzone.classList.remove("is-dragover");
    });
    elements.dropzone.addEventListener("drop", (event) => {
        event.preventDefault();
        elements.dropzone.classList.remove("is-dragover");
        if (event.dataTransfer.files.length) {
            elements.fileInput.files = event.dataTransfer.files;
            handleFileSelection();
        }
    });
}

function handleRefreshAll() {
    loadDocuments();
    loadMeetingMinutes();
    loadMeetingItems();
    loadSearchResults();
}

function handleFileSelection() {
    const file = elements.fileInput.files[0];
    if (!file) {
        elements.selectedFile.textContent = "No file selected";
        elements.fileModifiedAt.value = "";
        return;
    }

    elements.selectedFile.textContent = `${file.name} | ${formatFileSize(file.size)}`;
    elements.fileModifiedAt.value = file.lastModified ? new Date(file.lastModified).toISOString() : "";
}

async function handleUpload(event) {
    event.preventDefault();

    if (!elements.fileInput.files.length) {
        showToast("Please select a file first.", "error");
        return;
    }

    const formData = new FormData(elements.uploadForm);
    setUploadSubmitting(true);

    try {
        const result = await fetchJson("/api/documents/upload/", {
            method: "POST",
            body: formData,
        });

        showToast(result.message || "Upload succeeded.", "success");
        elements.uploadForm.reset();
        elements.selectedFile.textContent = "No file selected";
        elements.fileModifiedAt.value = "";
        state.documents.page = 1;
        await loadDocuments();

        if (result.data?.document_id) {
            await loadDocumentDetail(result.data.document_id);
        }
    } catch (error) {
        showToast(error.message, "error");
    } finally {
        setUploadSubmitting(false);
    }
}

function setUploadSubmitting(isSubmitting) {
    Array.from(elements.uploadForm.elements).forEach((element) => {
        element.disabled = isSubmitting;
    });
    elements.uploadSubmit.innerHTML = isSubmitting
        ? '<span class="spinner-border spinner-border-sm me-2"></span><span>Uploading...</span>'
        : '<i data-lucide="upload"></i><span>Upload Document</span>';
    renderIcons();
}

function handleDocumentFilterChange() {
    const formData = new FormData(elements.filterForm);
    state.documents.filters.keyword = String(formData.get("keyword") || "").trim();
    state.documents.filters.doc_type = String(formData.get("doc_type") || "").trim();
    state.documents.filters.status = String(formData.get("status") || "").trim();
    state.documents.page = 1;
    loadDocuments();
}

async function loadDocuments() {
    elements.documentList.innerHTML = renderLoadingState("Loading documents...");

    try {
        const params = new URLSearchParams({
            page: String(state.documents.page),
            limit: String(state.documents.limit),
        });

        Object.entries(state.documents.filters).forEach(([key, value]) => {
            if (value) {
                params.set(key, value);
            }
        });

        const result = await fetchJson(`/api/documents/?${params.toString()}`);
        state.documents.total = result.data.total;
        renderDocumentList(result.data.documents);
        updatePagination();

        if (
            state.documents.selectedDocumentId &&
            !result.data.documents.some((document) => document.document_id === state.documents.selectedDocumentId)
        ) {
            state.documents.selectedDocumentId = null;
            resetDocumentDetailPanel();
        }
    } catch (error) {
        elements.documentList.innerHTML = renderEmptyState("Load failed", error.message);
        showToast(error.message, "error");
    }
}

function renderDocumentList(documents) {
    if (!documents.length) {
        elements.documentList.innerHTML = renderEmptyState("No documents", "No matching documents were found.");
        renderIcons();
        return;
    }

    elements.documentList.innerHTML = documents
        .map((document) => {
            const activeClass = document.document_id === state.documents.selectedDocumentId ? "active" : "";
            return `
                <article class="document-card ${activeClass}" data-document-id="${escapeHtml(document.document_id)}">
                    <div class="document-card-head">
                        <div class="document-card-main">
                            <h3 class="document-card-title">${escapeHtml(document.original_filename)}</h3>
                            <p class="document-card-meta">${escapeHtml(document.doc_type || "unknown")} | ${formatFileSize(document.file_size)}</p>
                        </div>
                        <span class="badge rounded-pill text-bg-light border document-status-badge">${escapeHtml(document.status)}</span>
                    </div>
                    <p class="document-card-meta mb-1">Created: ${formatDate(document.created_at)}</p>
                    <p class="document-card-meta mb-0">Modified: ${formatDate(document.file_modified_at)}</p>
                </article>
            `;
        })
        .join("");

    elements.documentList.querySelectorAll(".document-card").forEach((card) => {
        card.addEventListener("click", () => loadDocumentDetail(card.dataset.documentId));
    });
    renderIcons();
}

function updatePagination() {
    const totalPages = Math.max(1, Math.ceil(state.documents.total / state.documents.limit));
    elements.pageIndicator.textContent = `Page ${state.documents.page} / ${totalPages}`;
    elements.prevPage.disabled = state.documents.page <= 1;
    elements.nextPage.disabled = state.documents.page >= totalPages;
}

function changePage(direction) {
    const totalPages = Math.max(1, Math.ceil(state.documents.total / state.documents.limit));
    const nextPage = state.documents.page + direction;
    if (nextPage < 1 || nextPage > totalPages) {
        return;
    }
    state.documents.page = nextPage;
    loadDocuments();
}

async function loadDocumentDetail(documentId) {
    elements.emptyDetail.classList.remove("d-none");
    elements.detailContent.classList.add("d-none");
    elements.emptyDetail.innerHTML = `
        <div class="detail-placeholder"><i data-lucide="loader-circle"></i></div>
        <h3 class="h6 fw-bold">Loading document detail</h3>
        <p class="text-muted small mb-0">Fetching metadata from the API.</p>
    `;
    renderIcons();

    try {
        const result = await fetchJson(`/api/documents/${documentId}/`);
        state.documents.selectedDocumentId = documentId;
        renderDocumentDetail(result.data);
        highlightSelectedCard();
    } catch (error) {
        showToast(error.message, "error");
        resetDocumentDetailPanel();
    }
}

function renderDocumentDetail(document) {
    elements.emptyDetail.classList.add("d-none");
    elements.detailContent.classList.remove("d-none");

    detailFields.name.textContent = document.original_filename || "-";
    detailFields.id.textContent = document.document_id || "-";
    detailFields.status.textContent = document.status || "-";
    detailFields.status.className = `badge rounded-pill ${statusBadgeClass(document.status)}`;
    detailFields.docType.textContent = document.doc_type || "unknown";
    detailFields.ext.textContent = document.file_ext || "-";
    detailFields.size.textContent = formatFileSize(document.file_size);
    detailFields.mime.textContent = document.mime_type || "-";
    detailFields.fileModified.textContent = formatDate(document.file_modified_at);
    detailFields.created.textContent = formatDate(document.created_at);
    detailFields.updated.textContent = formatDate(document.updated_at);
    detailFields.path.textContent = document.file_path || "-";
    detailFields.description.textContent = document.description || "-";
    detailFields.tags.textContent = Array.isArray(document.tags) && document.tags.length
        ? document.tags.join(", ")
        : "-";

    elements.parseButton.disabled = document.status === "deleted" || document.file_ext !== ".pdf";
    elements.parseResult.classList.add("d-none");
}

async function handleParseMeetingMinutes() {
    if (!state.documents.selectedDocumentId) {
        return;
    }

    elements.parseButton.disabled = true;
    elements.parseButton.innerHTML =
        '<span class="spinner-border spinner-border-sm me-2"></span><span>Parsing...</span>';

    try {
        const result = await fetchJson(
            `/api/documents/${state.documents.selectedDocumentId}/parse-meeting-minutes/`,
            { method: "POST" }
        );

        if (result.data?.status === "needs_ocr") {
            showToast(result.message || "OCR is required.", "error");
            renderParseResult({
                status: "needs_ocr",
                message: "The PDF text layer is insufficient. Document status was updated to needs_ocr.",
            });
        } else {
            showToast(result.message || "Meeting minutes parsed successfully.", "success");
            renderParseResult({
                status: "parsed",
                meeting_id: result.data.meeting_id,
                meeting_name: result.data.meeting_name,
                meeting_date: result.data.meeting_date,
                item_count: result.data.item_count,
            });

            if (result.data?.meeting_id) {
                state.meetings.selectedMeetingId = result.data.meeting_id;
                state.items.filters.meeting_id = result.data.meeting_id;
                syncItemFilterForm();
                await loadMeetingDetail(result.data.meeting_id);
            }
        }

        await loadDocumentDetail(state.documents.selectedDocumentId);
        await loadDocuments();
        await loadMeetingMinutes();
        await loadMeetingItems();
    } catch (error) {
        showToast(error.message, "error");
    } finally {
        elements.parseButton.disabled = false;
        elements.parseButton.innerHTML = '<i data-lucide="scan-text"></i><span>Parse Meeting PDF</span>';
        renderIcons();
    }
}

function renderParseResult(result) {
    elements.parseResult.classList.remove("d-none");

    if (result.status === "needs_ocr") {
        elements.parseResultBody.innerHTML = `
            <div class="summary-pill warning">needs_ocr</div>
            <div class="summary-copy">${escapeHtml(result.message)}</div>
        `;
        return;
    }

    elements.parseResultBody.innerHTML = `
        <div class="summary-pill success">parsed</div>
        <div class="summary-copy">
            <div><strong>${escapeHtml(result.meeting_name || "-")}</strong></div>
            <div>Meeting ID: ${escapeHtml(result.meeting_id || "-")}</div>
            <div>Date: ${escapeHtml(result.meeting_date || "-")} | Items: ${escapeHtml(String(result.item_count ?? "-"))}</div>
        </div>
    `;
}

async function handleDelete() {
    if (!state.documents.selectedDocumentId) {
        return;
    }

    const confirmed = window.confirm("Delete this document with soft delete?");
    if (!confirmed) {
        return;
    }

    elements.deleteButton.disabled = true;
    try {
        const result = await fetchJson(`/api/documents/${state.documents.selectedDocumentId}/`, {
            method: "DELETE",
        });
        showToast(result.message || "Document deleted.", "success");
        state.documents.selectedDocumentId = null;
        resetDocumentDetailPanel();
        await loadDocuments();
    } catch (error) {
        showToast(error.message, "error");
    } finally {
        elements.deleteButton.disabled = false;
    }
}

function resetDocumentDetailPanel() {
    elements.emptyDetail.classList.remove("d-none");
    elements.detailContent.classList.add("d-none");
    elements.emptyDetail.innerHTML = `
        <div class="detail-placeholder"><i data-lucide="file-text"></i></div>
        <h3 class="h6 fw-bold">Select a document</h3>
        <p class="text-muted small mb-0">View metadata and parse a PDF into structured meeting records.</p>
    `;
    renderIcons();
    highlightSelectedCard();
}

function highlightSelectedCard() {
    elements.documentList.querySelectorAll(".document-card").forEach((card) => {
        card.classList.toggle("active", card.dataset.documentId === state.documents.selectedDocumentId);
    });
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
    elements.meetingList.innerHTML = renderLoadingState("Loading meeting minutes...");

    try {
        const params = new URLSearchParams();
        Object.entries(state.meetings.filters).forEach(([key, value]) => {
            if (value) {
                params.set(key, value);
            }
        });

        const query = params.toString();
        const result = await fetchJson(`/api/meeting-minutes/${query ? `?${query}` : ""}`);
        renderMeetingList(result.data.meeting_minutes || []);

        if (state.meetings.selectedMeetingId) {
            const hasSelected = (result.data.meeting_minutes || []).some(
                (item) => item.meeting_id === state.meetings.selectedMeetingId
            );
            if (!hasSelected) {
                resetMeetingDetailPanel();
            }
        }
    } catch (error) {
        elements.meetingList.innerHTML = renderEmptyState("Load failed", error.message);
        showToast(error.message, "error");
    }
}

function renderMeetingList(meetings) {
    if (!meetings.length) {
        elements.meetingList.innerHTML = renderEmptyState(
            "No meeting minutes",
            "No matching meeting records were found."
        );
        renderIcons();
        return;
    }

    elements.meetingList.innerHTML = meetings
        .map((meeting) => {
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
                    <p class="document-card-meta mb-1">Meeting ID: ${escapeHtml(meeting.meeting_id)}</p>
                    <p class="document-card-meta mb-0">Document: ${escapeHtml(meeting.document_id || "-")}</p>
                </article>
            `;
        })
        .join("");

    elements.meetingList.querySelectorAll("[data-meeting-id]").forEach((card) => {
        card.addEventListener("click", () => loadMeetingDetail(card.dataset.meetingId));
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
    meetingDetailFields.attendees.textContent = Array.isArray(meeting.attendees) && meeting.attendees.length
        ? meeting.attendees.join(", ")
        : "-";

    elements.meetingItemsCount.textContent = `${items.length} items`;
    elements.meetingDetailItems.innerHTML = items.length
        ? items
              .map(
                  (item) => `
            <tr>
                <td>${escapeHtml(item.item_no || "-")}</td>
                <td class="text-break">${escapeHtml(item.content || "-")}</td>
                <td>${escapeHtml(item.owner || "-")}</td>
                <td>${escapeHtml(item.planned_date || "-")}</td>
                <td>${escapeHtml(item.actual_completed_date || "-")}</td>
                <td class="text-break">${escapeHtml(item.tracking_result || "-")}</td>
            </tr>
        `
              )
              .join("")
        : '<tr><td colspan="6" class="text-center text-muted py-4">No parsed items for this meeting.</td></tr>';
}

function resetMeetingDetailPanel() {
    state.meetings.selectedMeetingId = null;
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

function syncItemFilterForm() {
    elements.itemFilterForm.elements.meeting_id.value = state.items.filters.meeting_id || "";
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
    if (nextPage < 1 || nextPage > totalPages) {
        return;
    }
    state.search.page = nextPage;
    loadSearchResults();
}

async function loadSearchResults() {
    elements.searchResults.innerHTML = renderLoadingState("Loading search results...");
    if (elements.searchSubmit) {
        elements.searchSubmit.disabled = true;
    }
    try {
        const params = new URLSearchParams({
            page: String(state.search.page),
            limit: String(state.search.limit),
        });
        Object.entries(state.search.filters).forEach(([key, value]) => {
            if (value) {
                params.set(key, value);
            }
        });

        const result = await fetchJson(`/api/search/meeting-minutes/?${params.toString()}`);
        state.search.searchId = result.data.search_id || null;
        state.search.total = result.data.total || 0;
        renderSearchSummary(result.data);
        renderSearchResults(result.data.results || []);
        updateSearchPagination();
    } catch (error) {
        elements.searchSummary.textContent = "Search failed.";
        elements.searchResults.innerHTML = renderEmptyState("Search failed", error.message);
        showToast(error.message, "error");
    } finally {
        if (elements.searchSubmit) {
            elements.searchSubmit.disabled = false;
        }
    }
}

function renderSearchSummary(data) {
    const totalPages = Math.max(1, Math.ceil((data.total || 0) / state.search.limit));
    const queryText = data.query ? `"${data.query}"` : "all meetings";
    elements.searchSummary.textContent =
        `${queryText} | ${data.total || 0} results | page ${state.search.page} / ${totalPages}`;
}

function updateSearchPagination() {
    const totalPages = Math.max(1, Math.ceil(state.search.total / state.search.limit));
    elements.searchPrevPage.disabled = state.search.page <= 1;
    elements.searchNextPage.disabled = state.search.page >= totalPages;
}

function renderSearchResults(results) {
    if (!results.length) {
        elements.searchResults.innerHTML = renderEmptyState("No search results", "Try another keyword or relax the filters.");
        renderIcons();
        return;
    }

    elements.searchResults.innerHTML = results.map((result) => {
        const matchedFields = Array.isArray(result.matched_fields) && result.matched_fields.length
            ? result.matched_fields.map((field) => `<span class="search-chip">${escapeHtml(field)}</span>`).join("")
            : '<span class="search-chip">no direct field match</span>';
        const matchedItems = Array.isArray(result.matched_items) && result.matched_items.length
            ? result.matched_items.map((item) => `
                <button type="button" class="search-item-match" data-search-meeting-id="${escapeHtml(result.meeting_id)}" data-search-item-id="${escapeHtml(item.item_id || "")}" data-search-document-id="${escapeHtml(result.document_id || "")}">
                    <div class="search-item-top">
                        <span>#${escapeHtml(item.item_no || "-")}</span>
                        <span>score ${escapeHtml(String(item.score ?? 0))}</span>
                    </div>
                    <div class="search-item-body">${escapeHtml(item.content || "-")}</div>
                    <div class="search-item-meta">${escapeHtml(item.owner || "-")} | ${escapeHtml(item.planned_date || "-")}</div>
                </button>
            `).join("")
            : '<div class="text-muted small">No matched items.</div>';

        return `
            <article class="search-result-card">
                <button type="button" class="search-result-main" data-search-meeting-id="${escapeHtml(result.meeting_id)}" data-search-document-id="${escapeHtml(result.document_id || "")}">
                    <div class="search-result-head">
                        <div>
                            <h3 class="search-result-title">${escapeHtml(result.meeting_name || "-")}</h3>
                            <div class="search-result-meta">${escapeHtml(result.meeting_date || "-")} | ${escapeHtml(result.responsible_unit || "-")}</div>
                        </div>
                        <div class="search-score-badge">score ${escapeHtml(String(result.score ?? 0))}</div>
                    </div>
                    <div class="search-result-submeta">Meeting ID: ${escapeHtml(result.meeting_id || "-")} | Document: ${escapeHtml(result.document_id || "-")}</div>
                </button>
                <div class="search-field-row">${matchedFields}</div>
                <div class="search-item-list">${matchedItems}</div>
            </article>
        `;
    }).join("");

    elements.searchResults.querySelectorAll(".search-result-main").forEach((button) => {
        button.addEventListener("click", async () => {
            await logSearchClick({
                meeting_id: button.dataset.searchMeetingId,
                document_id: button.dataset.searchDocumentId,
            });
            if (button.dataset.searchMeetingId) {
                loadMeetingDetail(button.dataset.searchMeetingId);
            }
        });
    });

    elements.searchResults.querySelectorAll(".search-item-match").forEach((button) => {
        button.addEventListener("click", async () => {
            await logSearchClick({
                meeting_id: button.dataset.searchMeetingId,
                item_id: button.dataset.searchItemId,
                document_id: button.dataset.searchDocumentId,
            });
            if (button.dataset.searchMeetingId) {
                loadMeetingDetail(button.dataset.searchMeetingId);
            }
        });
    });
}

async function logSearchClick({ meeting_id, item_id = null, document_id = null }) {
    if (!state.search.searchId || !meeting_id) {
        return;
    }
    try {
        await fetchJson("/api/search/click/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                search_id: state.search.searchId,
                meeting_id,
                item_id,
                document_id,
            }),
        });
    } catch (error) {
        console.error("Failed to log search click", error);
    }
}

async function loadMeetingItems() {
    elements.meetingItemsList.innerHTML =
        '<tr><td colspan="6" class="text-center text-muted py-4">Loading...</td></tr>';

    try {
        const params = new URLSearchParams();
        Object.entries(state.items.filters).forEach(([key, value]) => {
            if (value) {
                params.set(key, value);
            }
        });

        const query = params.toString();
        const result = await fetchJson(`/api/meeting-items/${query ? `?${query}` : ""}`);
        renderMeetingItemsTable(result.data.meeting_items || []);
    } catch (error) {
        elements.meetingItemsList.innerHTML = `
            <tr><td colspan="6" class="text-center text-danger py-4">${escapeHtml(error.message)}</td></tr>
        `;
        showToast(error.message, "error");
    }
}

function renderMeetingItemsTable(items) {
    elements.meetingItemsList.innerHTML = items.length
        ? items
              .map(
                  (item) => `
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
        `
              )
              .join("")
        : '<tr><td colspan="6" class="text-center text-muted py-4">No matching meeting items.</td></tr>';

    elements.meetingItemsList.querySelectorAll(".item-link").forEach((button) => {
        button.addEventListener("click", () => {
            const meetingId = button.dataset.itemMeetingId;
            if (meetingId) {
                loadMeetingDetail(meetingId);
            }
        });
    });
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const result = await response.json();
    if (!response.ok || !result.success) {
        throw new Error(result.message || "Request failed.");
    }
    return result;
}

function showToast(message, type) {
    elements.toastBody.textContent = message;
    elements.toastElement.className = `toast align-items-center border-0 ${type === "error" ? "text-bg-danger" : "text-bg-success"}`;
    toast.show();
}

function renderLoadingState(message) {
    return `
        <div class="empty-state-shell">
            <div class="spinner-border text-primary mb-3" role="status"></div>
            <div class="fw-semibold">${escapeHtml(message)}</div>
        </div>
    `;
}

function renderEmptyState(title, message) {
    return `
        <div class="empty-state-shell">
            <div class="empty-state-icon"><i data-lucide="file-search"></i></div>
            <div class="fw-bold text-dark mb-1">${escapeHtml(title)}</div>
            <div class="text-muted small">${escapeHtml(message)}</div>
        </div>
    `;
}

function formatDate(value) {
    if (!value) {
        return "-";
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }

    return new Intl.DateTimeFormat("zh-TW", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    }).format(date);
}

function formatFileSize(size) {
    if (typeof size !== "number" || Number.isNaN(size)) {
        return "-";
    }

    const units = ["B", "KB", "MB", "GB"];
    let value = size;
    let unitIndex = 0;

    while (value >= 1024 && unitIndex < units.length - 1) {
        value /= 1024;
        unitIndex += 1;
    }

    return `${value.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function debounce(callback, delay) {
    let timerId = null;
    return (...args) => {
        window.clearTimeout(timerId);
        timerId = window.setTimeout(() => callback(...args), delay);
    };
}

function statusBadgeClass(status) {
    if (status === "deleted") {
        return "text-bg-danger";
    }
    if (status === "parsed") {
        return "text-bg-success";
    }
    if (status === "needs_ocr") {
        return "text-bg-warning";
    }
    return "text-bg-primary";
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
