const state = {
    page: 1,
    limit: 10,
    total: 0,
    selectedDocumentId: null,
    filters: {
        keyword: "",
        doc_type: "",
        status: "",
    },
};

const elements = {
    uploadForm: document.getElementById("upload-form"),
    fileInput: document.getElementById("file-input"),
    fileModifiedAt: document.getElementById("file-modified-at"),
    selectedFile: document.getElementById("selected-file"),
    uploadSubmit: document.getElementById("upload-submit"),
    filterForm: document.getElementById("filter-form"),
    refreshButton: document.getElementById("refresh-button"),
    documentList: document.getElementById("document-list"),
    pageIndicator: document.getElementById("page-indicator"),
    prevPage: document.getElementById("prev-page"),
    nextPage: document.getElementById("next-page"),
    emptyDetail: document.getElementById("empty-detail"),
    detailContent: document.getElementById("detail-content"),
    deleteButton: document.getElementById("delete-button"),
    toastElement: document.getElementById("status-toast"),
    toastBody: document.getElementById("status-toast-body"),
    dropzone: document.getElementById("dropzone"),
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

    elements.selectedFile.textContent = `${file.name} · ${formatFileSize(file.size)}`;
    elements.fileModifiedAt.value = file.lastModified
        ? new Date(file.lastModified).toISOString()
        : "";
}

async function handleUpload(event) {
    event.preventDefault();

    if (!elements.fileInput.files.length) {
        showToast("請先選擇要上傳的文件。", "error");
        return;
    }

    const formData = new FormData(elements.uploadForm);
    setUploadSubmitting(true);

    try {
        const response = await fetch("/api/documents/upload/", {
            method: "POST",
            body: formData,
        });
        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.message || "Upload failed.");
        }

        showToast(result.message || "File uploaded successfully.", "success");
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
    elements.documentList.innerHTML = renderLoadingState("正在取得最新文件列表");

    try {
        const params = new URLSearchParams({
            page: String(state.page),
            limit: String(state.limit),
        });

        Object.entries(state.filters).forEach(([key, value]) => {
            if (value) {
                params.set(key, value);
            }
        });

        const response = await fetch(`/api/documents/?${params.toString()}`);
        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.message || "Failed to load documents.");
        }

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
        elements.documentList.innerHTML = renderEmptyState(
            "目前沒有符合條件的文件",
            "你可以先上傳一份文件，或調整上方篩選條件。"
        );
        renderIcons();
        return;
    }

    elements.documentList.innerHTML = documents
        .map((document) => {
            const activeClass = document.document_id === state.selectedDocumentId ? "active" : "";
            return `
                <article class="document-card ${activeClass}" data-document-id="${escapeHtml(document.document_id)}">
                    <div class="document-card-head">
                        <div class="document-card-main">
                            <h3 class="document-card-title">${escapeHtml(document.original_filename)}</h3>
                            <p class="document-card-meta">${escapeHtml(document.doc_type || "unknown")} · ${formatFileSize(document.file_size)}</p>
                        </div>
                        <span class="badge rounded-pill text-bg-light border document-status-badge">${escapeHtml(document.status)}</span>
                    </div>
                    <p class="document-card-meta mb-1">建立時間：${formatDate(document.created_at)}</p>
                    <p class="document-card-meta mb-0">檔案修改時間：${formatDate(document.file_modified_at)}</p>
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
    const totalPages = Math.max(1, Math.ceil(state.total / state.limit));
    elements.pageIndicator.textContent = `第 ${state.page} 頁 / 共 ${totalPages} 頁`;
    elements.prevPage.disabled = state.page <= 1;
    elements.nextPage.disabled = state.page >= totalPages;
}

function changePage(direction) {
    const totalPages = Math.max(1, Math.ceil(state.total / state.limit));
    const nextPage = state.page + direction;
    if (nextPage < 1 || nextPage > totalPages) {
        return;
    }
    state.page = nextPage;
    loadDocuments();
}

async function loadDocumentDetail(documentId) {
    elements.emptyDetail.classList.remove("d-none");
    elements.detailContent.classList.add("d-none");
    elements.emptyDetail.innerHTML = `
        <div class="detail-placeholder">
            <i data-lucide="loader-circle"></i>
        </div>
        <h3 class="h6 fw-bold">載入明細中</h3>
        <p class="text-muted small mb-0">正在取得文件 metadata。</p>
    `;
    renderIcons();

    try {
        const response = await fetch(`/api/documents/${documentId}/`);
        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.message || "Failed to load detail.");
        }

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
    detailFields.status.className = `badge rounded-pill ${document.status === "deleted" ? "text-bg-danger" : "text-bg-primary"}`;
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
}

async function handleDelete() {
    if (!state.selectedDocumentId) {
        return;
    }

    const confirmed = window.confirm("確定要刪除這份文件嗎？此操作會做 soft delete。");
    if (!confirmed) {
        return;
    }

    elements.deleteButton.disabled = true;

    try {
        const response = await fetch(`/api/documents/${state.selectedDocumentId}/`, {
            method: "DELETE",
        });
        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.message || "Delete failed.");
        }

        showToast(result.message || "Document deleted successfully.", "success");
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
    elements.emptyDetail.innerHTML = `
        <div class="detail-placeholder">
            <i data-lucide="file-text"></i>
        </div>
        <h3 class="h6 fw-bold">選一份文件來查看</h3>
        <p class="text-muted small mb-0">
            從列表點擊文件後，這裡會顯示 metadata、檔案修改時間與刪除操作。
        </p>
    `;
    elements.detailContent.classList.add("d-none");
    highlightSelectedCard();
    renderIcons();
}

function highlightSelectedCard() {
    elements.documentList.querySelectorAll(".document-card").forEach((card) => {
        card.classList.toggle("active", card.dataset.documentId === state.selectedDocumentId);
    });
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
            <div class="empty-state-icon">
                <i data-lucide="file-search"></i>
            </div>
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
