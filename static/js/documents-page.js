const state = {
    page: 1,
    limit: 10,
    total: 0,
    selectedDocumentId: null,
    filters: { keyword: "", doc_type: "", status: "" },
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
    openMeetingsLink: document.getElementById("open-meetings-link"),
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

const toast = new bootstrap.Toast(elements.toastElement, { delay: 2800 });

init();

function init() {
    bindEvents();
    resetDetailPanel();
    loadDocuments();
    renderIcons();
}

function bindEvents() {
    elements.fileInput.addEventListener("change", handleFileSelection);
    elements.uploadForm.addEventListener("submit", handleUpload);
    elements.refreshButton.addEventListener("click", loadDocuments);
    elements.filterForm.addEventListener("input", debounce(handleFilterChange, 300));
    elements.filterForm.addEventListener("change", handleFilterChange);
    elements.prevPage.addEventListener("click", () => changePage(-1));
    elements.nextPage.addEventListener("click", () => changePage(1));
    elements.parseButton.addEventListener("click", handleParseMeetingMinutes);
    elements.deleteButton.addEventListener("click", handleDelete);

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

function handleFileSelection() {
    const file = elements.fileInput.files[0];
    if (!file) {
        elements.selectedFile.textContent = "尚未選擇檔案";
        elements.fileModifiedAt.value = "";
        return;
    }
    elements.selectedFile.textContent = `${file.name} | ${formatFileSize(file.size)}`;
    elements.fileModifiedAt.value = file.lastModified ? new Date(file.lastModified).toISOString() : "";
}

async function handleUpload(event) {
    event.preventDefault();
    if (!elements.fileInput.files.length) {
        showToast("請先選擇檔案。", "error");
        return;
    }
    const formData = new FormData(elements.uploadForm);
    setUploadSubmitting(true);
    try {
        const result = await fetchJson("/api/documents/upload/", { method: "POST", body: formData });
        showToast(result.message || "文件上傳成功。", "success");
        elements.uploadForm.reset();
        elements.selectedFile.textContent = "尚未選擇檔案";
        elements.fileModifiedAt.value = "";
        state.page = 1;
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
        ? '<span class="spinner-border spinner-border-sm me-2"></span><span>上傳中...</span>'
        : '<i data-lucide="upload"></i><span>上傳文件</span>';
    renderIcons();
}

function handleFilterChange() {
    const formData = new FormData(elements.filterForm);
    state.filters.keyword = String(formData.get("keyword") || "").trim();
    state.filters.doc_type = String(formData.get("doc_type") || "").trim();
    state.filters.status = String(formData.get("status") || "").trim();
    state.page = 1;
    loadDocuments();
}

async function loadDocuments() {
    elements.documentList.innerHTML = renderLoadingState("載入文件中...");
    try {
        const params = new URLSearchParams({ page: String(state.page), limit: String(state.limit) });
        Object.entries(state.filters).forEach(([key, value]) => {
            if (value) params.set(key, value);
        });
        const result = await fetchJson(`/api/documents/?${params.toString()}`);
        state.total = result.data.total;
        renderDocumentList(result.data.documents);
        updatePagination();
        if (
            state.selectedDocumentId &&
            !result.data.documents.some((document) => document.document_id === state.selectedDocumentId)
        ) {
            state.selectedDocumentId = null;
            resetDetailPanel();
        }
    } catch (error) {
        elements.documentList.innerHTML = renderEmptyState("載入失敗", error.message);
        showToast(error.message, "error");
    }
}

function renderDocumentList(documents) {
    if (!documents.length) {
        elements.documentList.innerHTML = renderEmptyState("沒有文件", "目前查無符合條件的文件。");
        renderIcons();
        return;
    }
    elements.documentList.innerHTML = documents.map((document) => {
        const activeClass = document.document_id === state.selectedDocumentId ? "active" : "";
        return `
            <article class="document-card ${activeClass}" data-document-id="${escapeHtml(document.document_id)}">
                <div class="document-card-head">
                    <div class="document-card-main">
                        <h3 class="document-card-title">${escapeHtml(document.original_filename)}</h3>
                        <p class="document-card-meta">${escapeHtml(document.doc_type || "未分類")} | ${formatFileSize(document.file_size)}</p>
                    </div>
                    <span class="badge rounded-pill text-bg-light border document-status-badge">${escapeHtml(document.status)}</span>
                </div>
                <p class="document-card-meta mb-1">建立時間：${formatDate(document.created_at)}</p>
                <p class="document-card-meta mb-0">修改時間：${formatDate(document.file_modified_at)}</p>
            </article>
        `;
    }).join("");
    elements.documentList.querySelectorAll(".document-card").forEach((card) => {
        card.addEventListener("click", () => loadDocumentDetail(card.dataset.documentId));
    });
    renderIcons();
}

function updatePagination() {
    const totalPages = Math.max(1, Math.ceil(state.total / state.limit));
    elements.pageIndicator.textContent = `第 ${state.page} / ${totalPages} 頁`;
    elements.prevPage.disabled = state.page <= 1;
    elements.nextPage.disabled = state.page >= totalPages;
}

function changePage(direction) {
    const totalPages = Math.max(1, Math.ceil(state.total / state.limit));
    const nextPage = state.page + direction;
    if (nextPage < 1 || nextPage > totalPages) return;
    state.page = nextPage;
    loadDocuments();
}

async function loadDocumentDetail(documentId) {
    elements.emptyDetail.classList.remove("d-none");
    elements.detailContent.classList.add("d-none");
    elements.emptyDetail.innerHTML = `
        <div class="detail-placeholder"><i data-lucide="loader-circle"></i></div>
        <h3 class="h6 fw-bold">載入文件明細中</h3>
        <p class="text-muted small mb-0">正在從 API 取得文件 metadata。</p>
    `;
    renderIcons();
    try {
        const result = await fetchJson(`/api/documents/${documentId}/`);
        state.selectedDocumentId = documentId;
        renderDocumentDetail(result.data);
        highlightSelectedCard();
    } catch (error) {
        showToast(error.message, "error");
        resetDetailPanel();
    }
}

function renderDocumentDetail(document) {
    elements.emptyDetail.classList.add("d-none");
    elements.detailContent.classList.remove("d-none");
    detailFields.name.textContent = document.original_filename || "-";
    detailFields.id.textContent = document.document_id || "-";
    detailFields.status.textContent = document.status || "-";
    detailFields.status.className = `badge rounded-pill ${statusBadgeClass(document.status)}`;
    detailFields.docType.textContent = document.doc_type || "未分類";
    detailFields.ext.textContent = document.file_ext || "-";
    detailFields.size.textContent = formatFileSize(document.file_size);
    detailFields.mime.textContent = document.mime_type || "-";
    detailFields.fileModified.textContent = formatDate(document.file_modified_at);
    detailFields.created.textContent = formatDate(document.created_at);
    detailFields.updated.textContent = formatDate(document.updated_at);
    detailFields.path.textContent = document.file_path || "-";
    detailFields.description.textContent = document.description || "-";
    detailFields.tags.textContent = Array.isArray(document.tags) && document.tags.length ? document.tags.join(", ") : "-";
    elements.parseButton.disabled = document.status === "deleted" || document.file_ext !== ".pdf";
    elements.parseResult.classList.add("d-none");
}

async function handleParseMeetingMinutes() {
    if (!state.selectedDocumentId) return;
    elements.parseButton.disabled = true;
    elements.parseButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span><span>解析中...</span>';
    try {
        const result = await fetchJson(`/api/documents/${state.selectedDocumentId}/parse-meeting-minutes/`, { method: "POST" });
        if (result.data?.status === "needs_ocr") {
            showToast(result.message || "PDF 文字層不足，需要先做 OCR。", "error");
            renderParseResult({ status: "needs_ocr", message: "PDF 文字層不足，文件狀態已更新為 needs_ocr。" });
        } else {
            showToast(result.message || "會議記錄解析成功。", "success");
            renderParseResult({
                status: "parsed",
                meeting_id: result.data.meeting_id,
                meeting_name: result.data.meeting_name,
                meeting_date: result.data.meeting_date,
                item_count: result.data.item_count,
            });
            if (result.data?.meeting_id) {
                elements.openMeetingsLink.href = `/meetings/?meeting_id=${encodeURIComponent(result.data.meeting_id)}`;
            }
        }
        await loadDocumentDetail(state.selectedDocumentId);
        await loadDocuments();
    } catch (error) {
        showToast(error.message, "error");
    } finally {
        elements.parseButton.disabled = false;
        elements.parseButton.innerHTML = '<i data-lucide="scan-text"></i><span>解析會議記錄 PDF</span>';
        renderIcons();
    }
}

function renderParseResult(result) {
    elements.parseResult.classList.remove("d-none");
    if (result.status === "needs_ocr") {
        elements.parseResultBody.innerHTML = `<div class="summary-pill warning">needs_ocr</div><div class="summary-copy">${escapeHtml(result.message)}</div>`;
        return;
    }
    elements.parseResultBody.innerHTML = `
        <div class="summary-pill success">parsed</div>
        <div class="summary-copy">
            <div><strong>${escapeHtml(result.meeting_name || "-")}</strong></div>
            <div>Meeting ID：${escapeHtml(result.meeting_id || "-")}</div>
            <div>日期：${escapeHtml(result.meeting_date || "-")}｜項目數：${escapeHtml(String(result.item_count ?? "-"))}</div>
        </div>
    `;
}

async function handleDelete() {
    if (!state.selectedDocumentId) return;
    const confirmed = window.confirm("確定要將這份文件標記為刪除嗎？");
    if (!confirmed) return;
    elements.deleteButton.disabled = true;
    try {
        const result = await fetchJson(`/api/documents/${state.selectedDocumentId}/`, { method: "DELETE" });
        showToast(result.message || "文件已刪除。", "success");
        state.selectedDocumentId = null;
        resetDetailPanel();
        await loadDocuments();
    } catch (error) {
        showToast(error.message, "error");
    } finally {
        elements.deleteButton.disabled = false;
    }
}

function resetDetailPanel() {
    elements.emptyDetail.classList.remove("d-none");
    elements.detailContent.classList.add("d-none");
    elements.emptyDetail.innerHTML = `
        <div class="detail-placeholder"><i data-lucide="file-text"></i></div>
        <h3 class="h6 fw-bold">選擇一份文件</h3>
        <p class="text-muted small mb-0">查看文件 metadata，並從這裡啟動會議記錄 PDF 解析。</p>
    `;
    renderIcons();
    highlightSelectedCard();
}

function highlightSelectedCard() {
    elements.documentList.querySelectorAll(".document-card").forEach((card) => {
        card.classList.toggle("active", card.dataset.documentId === state.selectedDocumentId);
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

function formatDate(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat("zh-TW", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    }).format(date);
}

function formatFileSize(size) {
    if (typeof size !== "number" || Number.isNaN(size)) return "-";
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
    if (status === "deleted") return "text-bg-danger";
    if (status === "parsed") return "text-bg-success";
    if (status === "needs_ocr") return "text-bg-warning";
    return "text-bg-primary";
}

function escapeHtml(value) {
    return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

function renderIcons() {
    if (window.lucide) window.lucide.createIcons();
}
