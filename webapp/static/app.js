let currentExtractedData = [];
let currentJobId = "";
let currentPdfUrl = "";
let currentExcelUrl = "";
let currentMetadata = {};
let currentRejectedData = [];
let currentApprovalId = "";
let previewZoom = 1;
let isPanning = false;
let panStartX = 0;
let panStartY = 0;
let scrollStartLeft = 0;
let scrollStartTop = 0;
let isPlaceBalloonMode = false;
let isDrawingSelection = false;
let selectionStart = null;
let refreshPreviewTimer = null;
let previewRefreshInFlight = false;
let previewRefreshPending = false;
let manualOcrInFlight = false;
let selectionAnimationFrame = null;
let pendingSelectionFrame = null;
let pendingPdfRefresh = false;

const processButton = document.getElementById("process-btn");
const cancelProcessButton = document.getElementById("cancel-process-btn");
const fileInput = document.getElementById("pdf-upload");
const loadingMessage = document.getElementById("loading-msg");
const reviewSection = document.getElementById("review-section");
const previewImage = document.getElementById("ballooned-preview");
const previewContainer = document.querySelector(".image-container");
const selectionBox = document.getElementById("selection-box");
const metadataPanel = document.getElementById("metadata-panel");
let statusPollTimer = null;

processButton.addEventListener("click", async () => {
    if (fileInput.files.length === 0) {
        alert("Please select a PDF first.");
        return;
    }

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    currentJobId = "";
    loadingMessage.classList.remove("hidden");
    loadingMessage.textContent = "Uploading drawing...";
    reviewSection.classList.add("hidden");
    processButton.disabled = true;
    cancelProcessButton.classList.remove("hidden");
    cancelProcessButton.disabled = false;

    try {
        const response = await fetch("/api/upload-async", {
            method: "POST",
            body: formData
        });

        const data = await parseResponse(response);
        if (!response.ok || !["queued", "processing", "success", "needs_review"].includes(data.status)) {
            throw new Error(data.message || "Processing failed.");
        }

        currentJobId = data.job_id || "";
        loadingMessage.textContent = data.message || "Processing drawing in background...";
        if (["success", "needs_review"].includes(data.status)) {
            applyProcessingResult(data);
        } else {
            startStatusPolling(currentJobId);
        }
    } catch (error) {
        alert(error.message || "Error processing drawing. Check server logs.");
        console.error(error);
    } finally {
        if (!currentJobId) {
            loadingMessage.classList.add("hidden");
            processButton.disabled = false;
            cancelProcessButton.classList.add("hidden");
        }
    }
});

cancelProcessButton.addEventListener("click", async () => {
    if (!currentJobId) {
        return;
    }
    cancelProcessButton.disabled = true;
    loadingMessage.classList.remove("hidden");
    loadingMessage.textContent = "Cancel requested...";
    try {
        const response = await fetch(`/api/jobs/${encodeURIComponent(currentJobId)}/cancel`, {
            method: "POST"
        });
        const data = await parseResponse(response);
        if (!response.ok) {
            throw new Error(data.message || "Cancel failed.");
        }
        loadingMessage.textContent = data.message || "Cancel requested.";
    } catch (error) {
        alert(error.message || "Error cancelling OCR.");
        cancelProcessButton.disabled = false;
    }
});

function applyProcessingResult(data) {
    currentJobId = data.job_id;
    currentExtractedData = data.extracted_data || [];
    renumberRows();
    currentPdfUrl = data.ballooned_pdf || "";
    currentExcelUrl = data.fa_excel || "";
    currentMetadata = data.metadata || {};
    currentRejectedData = data.rejected_data || [];
    currentApprovalId = "";

    if (data.ballooned_image) {
        previewImage.src = data.ballooned_image;
        previewZoom = 1;
        applyPreviewZoom();
        previewImage.classList.remove("hidden");
    } else {
        previewImage.classList.add("hidden");
    }

    renderTable(currentExtractedData);
    renderRejectedTable(currentRejectedData);
    renderMetadata(
        data.metadata || {},
        data.titleblock_diagnostics || {},
        data.processing_timings || {}
    );
    reviewSection.classList.remove("hidden");
    loadingMessage.classList.add("hidden");
    processButton.disabled = false;
    cancelProcessButton.classList.add("hidden");
    cancelProcessButton.disabled = false;

    const quality = data.quality || {};
    if (quality.status === "needs_review") {
        const messages = (quality.issues || [])
            .map((issue) => issue.message || issue.type)
            .filter(Boolean);
        alert(
            `OCR finished, but approval is blocked by ${quality.issue_count || messages.length} quality check(s).\n\n` +
            `${messages.join("\n")}\n\nCorrect these items in the review screen before approval.`
        );
    }
}

function startStatusPolling(jobId) {
    if (statusPollTimer) {
        clearInterval(statusPollTimer);
    }

    statusPollTimer = setInterval(async () => {
        try {
            const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
            const data = await parseResponse(response);
            if (!response.ok) {
                throw new Error(data.message || "Could not read job status.");
            }

            loadingMessage.textContent = data.message || `Status: ${data.status}`;
            if (["success", "needs_review"].includes(data.status) && data.result) {
                clearInterval(statusPollTimer);
                statusPollTimer = null;
                applyProcessingResult(data.result);
            } else if (data.status === "error") {
                clearInterval(statusPollTimer);
                statusPollTimer = null;
                loadingMessage.classList.add("hidden");
                processButton.disabled = false;
                cancelProcessButton.classList.add("hidden");
                alert(data.message || "Processing failed.");
            } else if (data.status === "cancelled") {
                clearInterval(statusPollTimer);
                statusPollTimer = null;
                loadingMessage.textContent = data.message || "Processing cancelled.";
                processButton.disabled = false;
                cancelProcessButton.classList.add("hidden");
            }
        } catch (error) {
            clearInterval(statusPollTimer);
            statusPollTimer = null;
            loadingMessage.classList.add("hidden");
            processButton.disabled = false;
            cancelProcessButton.classList.add("hidden");
            alert(error.message || "Error checking job status.");
        }
    }, 5000);
}

async function parseResponse(response) {
    const text = await response.text();
    if (!text) {
        return {};
    }

    try {
        return JSON.parse(text);
    } catch (error) {
        return {
            status: "error",
            message: response.ok ? text : `Server returned ${response.status}: ${text}`
        };
    }
}

function safeText(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#039;"
    }[char]));
}

function renderMetadata(metadata, diagnostics, processingTimings = {}) {
    const fields = [
        ["part_number", "Part Number", metadata.part_number],
        ["drawing_number", "Drawing Number", metadata.drawing_number],
        ["revision", "Revision", metadata.revision],
        ["material", "Material", metadata.material],
        ["part_name", "Part Name", metadata.part_name]
    ];
    const status = diagnostics.status || "";
    const cropMethod = diagnostics.crop_method || "";
    const stageSeconds = processingTimings.seconds || {};
    const totalSeconds = Number(stageSeconds.total || 0);
    const slowestStage = Object.entries(stageSeconds)
        .filter(([name, seconds]) => name !== "total" && Number(seconds) > 0)
        .sort((left, right) => Number(right[1]) - Number(left[1]))[0];
    const timingSummary = totalSeconds
        ? `${(totalSeconds / 60).toFixed(1)} min total`
        : "Not measured";
    const slowestSummary = slowestStage
        ? `${slowestStage[0].replaceAll("_", " ")} (${(Number(slowestStage[1]) / 60).toFixed(1)} min)`
        : "-";
    metadataPanel.innerHTML = `
        <div class="metadata-grid">
            ${fields.map(([key, label, value]) => `
                <div>
                    <label for="metadata-${safeText(key)}">${safeText(label)}</label>
                    <input id="metadata-${safeText(key)}" class="metadata-input" data-metadata-key="${safeText(key)}" value="${safeText(value || "")}" placeholder="Not detected">
                </div>
            `).join("")}
            <div>
                <span>Title OCR</span>
                <strong>${safeText([status, cropMethod].filter(Boolean).join(" / ") || "-")}</strong>
            </div>
            <div>
                <span>Processing Time</span>
                <strong>${safeText(timingSummary)}</strong>
            </div>
            <div>
                <span>Slowest Stage</span>
                <strong>${safeText(slowestSummary)}</strong>
            </div>
        </div>
    `;
    metadataPanel.querySelectorAll("[data-metadata-key]").forEach((input) => {
        input.addEventListener("input", function () {
            currentMetadata[this.dataset.metadataKey] = this.value.trim();
        });
    });
    metadataPanel.classList.remove("hidden");
}

function renderTable(dataArray) {
    const tbody = document.getElementById("table-body");
    tbody.innerHTML = "";

    dataArray.forEach((item, index) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td contenteditable="true" data-key="Balloon No" data-index="${index}">${safeText(item["Balloon No"])}</td>
            <td contenteditable="true" data-key="Report Symbol" data-index="${index}">${safeText(item["Report Symbol"] ?? item["Symbol"])}</td>
            <td contenteditable="true" data-key="Dimension" data-index="${index}">${safeText(item["Dimension"])}</td>
            <td contenteditable="true" data-key="Tolerance -" data-index="${index}">${safeText(item["Tolerance -"])}</td>
            <td contenteditable="true" data-key="Tolerance +" data-index="${index}">${safeText(item["Tolerance +"])}</td>
            <td contenteditable="true" data-key="MIN" data-index="${index}">${safeText(item["MIN"])}</td>
            <td contenteditable="true" data-key="MAX" data-index="${index}">${safeText(item["MAX"])}</td>
            <td contenteditable="true" data-key="Review Reason" data-index="${index}">${safeText(item["Review Reason"])}</td>
            <td><input class="number-input" type="number" step="0.1" min="0.5" max="3" data-key="Balloon Size" data-index="${index}" value="${safeText(item["Balloon Size"] ?? "1")}"></td>
            <td><input class="number-input" type="number" step="5" min="-180" max="180" data-key="Balloon Rotation" data-index="${index}" value="${safeText(item["Balloon Rotation"] ?? "0")}"></td>
            <td class="${item["Needs Review"] === "YES" ? "needs-review" : ""}">${safeText(item["Needs Review"])}</td>
            <td>
                <button type="button" class="small-secondary-btn" data-action="add-subrow" data-index="${index}">+ Sub-row</button>
                <button type="button" class="small-danger-btn" data-action="delete-row" data-index="${index}">Delete</button>
            </td>
        `;
        tbody.appendChild(tr);
    });

    document.querySelectorAll('td[contenteditable="true"]').forEach((cell) => {
        cell.addEventListener("focus", function () {
            this.dataset.originalValue = this.innerText.trim();
        });
        cell.addEventListener("keydown", function (event) {
            if (event.key === "Enter") {
                event.preventDefault();
                this.blur();
            }
        });
        cell.addEventListener("input", function () {
            const index = Number(this.getAttribute("data-index"));
            const key = this.getAttribute("data-key");
            if (key === "Balloon No") {
                return;
            }
            currentExtractedData[index][key] = this.innerText.trim();
            if (key === "Report Symbol") {
                currentExtractedData[index]["Symbol"] = this.innerText.trim();
            }
        });
        cell.addEventListener("blur", function () {
            const index = Number(this.getAttribute("data-index"));
            const key = this.getAttribute("data-key");
            if (key === "Balloon No") {
                applyBalloonNumberEdit(index, this.innerText.trim(), this.dataset.originalValue || "");
                renderTable(currentExtractedData);
                queuePreviewRefresh();
                return;
            }
            currentExtractedData[index][key] = this.innerText.trim();
        });
    });

    document.querySelectorAll(".number-input").forEach((input) => {
        input.addEventListener("input", function () {
            const index = Number(this.getAttribute("data-index"));
            const key = this.getAttribute("data-key");
            currentExtractedData[index][key] = this.value;
            queuePreviewRefresh();
        });
    });

    document.querySelectorAll('[data-action="delete-row"]').forEach((button) => {
        button.addEventListener("click", function () {
            const index = Number(this.getAttribute("data-index"));
            currentExtractedData.splice(index, 1);
            renumberRows();
            renderTable(currentExtractedData);
            queuePreviewRefresh();
        });
    });

    document.querySelectorAll('[data-action="add-subrow"]').forEach((button) => {
        button.addEventListener("click", function () {
            addBlankSubrow(Number(this.getAttribute("data-index")));
        });
    });
}

function renderRejectedTable(dataArray) {
    const tbody = document.getElementById("rejected-table-body");
    if (!tbody) {
        return;
    }
    tbody.innerHTML = "";

    dataArray.forEach((item, index) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${safeText(item["Extracted Value"])}</td>
            <td>${safeText(item["OCR Text"])}</td>
            <td>${safeText(item["Reject Reason"])}</td>
            <td>${safeText(item["OCR Confidence"])}</td>
            <td><button type="button" class="small-secondary-btn" data-action="promote-row" data-index="${index}">Add</button></td>
        `;
        tbody.appendChild(tr);
    });

    document.querySelectorAll('[data-action="promote-row"]').forEach((button) => {
        button.addEventListener("click", function () {
            const index = Number(this.getAttribute("data-index"));
            const rejected = currentRejectedData[index];
            if (!rejected) {
                return;
            }
            currentExtractedData.push(createRowFromRejected(rejected));
            currentRejectedData.splice(index, 1);
            renumberRows();
            renderTable(currentExtractedData);
            renderRejectedTable(currentRejectedData);
            queuePreviewRefresh();
        });
    });
}

function createEmptyManualRow() {
    const nextNumber = nextBalloonMainNumber();
    return {
        "Balloon No": nextNumber,
        "Display Balloon No": nextNumber,
        "Report Symbol": "",
        "Symbol": "",
        "Dimension": "",
        "Tolerance -": "",
        "Tolerance +": "",
        "MIN": "",
        "MAX": "",
        "Needs Review": "YES",
        "Review Reason": "Manual row - verify before export",
        "Measurement Type": "manual",
        "Balloon Size": "1",
        "Balloon Rotation": "0",
        "X": 0,
        "Y": 0,
        "Width": 0,
        "Height": 0
    };
}

function createRowFromRejected(rejected) {
    const value = rejected["Extracted Value"] || rejected["OCR Text"] || "";
    const nextNumber = nextBalloonMainNumber();
    return {
        "Balloon No": nextNumber,
        "Display Balloon No": nextNumber,
        "Report Symbol": "",
        "Symbol": "",
        "Dimension": value,
        "Tolerance -": "",
        "Tolerance +": "",
        "MIN": "",
        "MAX": "",
        "Needs Review": "YES",
        "Review Reason": `Promoted rejected OCR: ${rejected["Reject Reason"] || "review required"}`,
        "Measurement Type": rejected["Measurement Type"] || "manual",
        "Balloon Size": "1",
        "Balloon Rotation": "0",
        "X": rejected["X"] || 0,
        "Y": rejected["Y"] || 0,
        "Width": rejected["Width"] || 0,
        "Height": rejected["Height"] || 0
    };
}

function renumberRows() {
    const groups = groupedBalloonRows(currentExtractedData);
    groups.forEach((group, groupIndex) => {
        const main = String(groupIndex + 1);
        const isSubrowGroup = group.rows.length > 1;
        group.rows.forEach(({ row, suffix }, rowIndex) => {
            const resolvedSuffix = isSubrowGroup ? (suffix || String(rowIndex + 1)) : suffix;
            row["Balloon No"] = resolvedSuffix ? `${main}.${resolvedSuffix}` : main;
            row["Display Balloon No"] = main;
            if (isSubrowGroup) {
                row["Subrow Count"] = group.rows.length;
                row["Subrow Index"] = rowIndex + 1;
            }
        });
    });

    // groupedBalloonRows returns the intended numeric order, but updating the
    // row values alone leaves the source array in its old order. Rebuild the
    // array so the review table, corrected preview, PDF, and Excel all consume
    // the same order the reviewer requested.
    currentExtractedData = groups.flatMap((group) => group.rows.map(({ row }) => row));
}

function nextBalloonMainNumber() {
    const parsed = currentExtractedData
        .map((row) => parseBalloonNumber(row["Balloon No"]))
        .filter(Boolean);
    return String(parsed.length ? Math.max(...parsed.map((item) => item.main)) + 1 : 1);
}

function insertManualCropRows(rows) {
    const usableRows = Array.isArray(rows) && rows.length ? rows : [createEmptyManualRow()];
    const main = nextBalloonMainNumber();
    const count = usableRows.length;
    usableRows.forEach((source, index) => {
        const row = { ...source };
        row["Balloon No"] = count > 1 ? `${main}.${index + 1}` : main;
        row["Display Balloon No"] = main;
        if (count > 1) {
            row["Subrow Count"] = count;
            row["Subrow Index"] = index + 1;
        }
        currentExtractedData.push(row);
    });
    renumberRows();
}

function addBlankSubrow(index) {
    const source = currentExtractedData[index];
    if (!source) {
        return;
    }
    const parsed = parseBalloonNumber(source["Balloon No"]);
    if (!parsed) {
        alert("Enter a valid main balloon number before adding a sub-row.");
        return;
    }

    const groupIndexes = [];
    currentExtractedData.forEach((row, rowIndex) => {
        const current = parseBalloonNumber(row["Balloon No"]);
        if (current && current.main === parsed.main) {
            groupIndexes.push(rowIndex);
        }
    });
    const insertAt = Math.max(...groupIndexes) + 1;

    const multiplierCandidates = [
        source["Specification"],
        `${source["Report Symbol"] || ""}${source["Dimension"] || ""}`,
        `${source["Symbol"] || ""}${source["Dimension"] || ""}`
    ];
    let multiplier = null;
    for (const candidate of multiplierCandidates) {
        const match = String(candidate || "").trim().match(/^(\d{1,2})\s*[xX×]\s*(.+)$/);
        if (match) {
            const count = Number(match[1]);
            if (count >= 2 && count <= 20) {
                multiplier = { count, value: match[2].trim() };
                break;
            }
        }
    }

    if (multiplier && groupIndexes.length < multiplier.count) {
        const symbolMatch = multiplier.value.match(/^([A-Za-zØ⌀]+)\s*(.*)$/);
        const cleanSymbol = symbolMatch ? symbolMatch[1] : (source["Report Symbol"] || source["Symbol"] || "");
        const cleanDimension = symbolMatch && symbolMatch[2]
            ? symbolMatch[2]
            : (source["Dimension"] || multiplier.value);
        const originalSpecification = source["Specification"] || `${multiplier.count}X ${multiplier.value}`;

        groupIndexes.forEach((rowIndex, groupIndex) => {
            const row = currentExtractedData[rowIndex];
            row["Report Symbol"] = cleanSymbol;
            row["Symbol"] = cleanSymbol;
            row["Dimension"] = cleanDimension;
            row["Specification"] = originalSpecification;
            row["Multiplier Count"] = multiplier.count;
            row["Multiplier Index"] = groupIndex + 1;
        });

        const missingRows = [];
        for (let multiplierIndex = groupIndexes.length + 1; multiplierIndex <= multiplier.count; multiplierIndex += 1) {
            missingRows.push({
                ...source,
                "Balloon No": `${parsed.main}.${multiplierIndex}`,
                "Display Balloon No": String(parsed.main),
                "Report Symbol": cleanSymbol,
                "Symbol": cleanSymbol,
                "Dimension": cleanDimension,
                "Specification": originalSpecification,
                "Multiplier Count": multiplier.count,
                "Multiplier Index": multiplierIndex,
                "Needs Review": "YES",
                "Review Reason": "Manual multiplier sub-row - verify before export"
            });
        }
        currentExtractedData.splice(insertAt, 0, ...missingRows);
        renumberRows();
        renderTable(currentExtractedData);
        queuePreviewRefresh();
        return;
    }

    const newRow = {
        ...source,
        "Balloon No": `${parsed.main}.${groupIndexes.length + 1}`,
        "Display Balloon No": String(parsed.main),
        "Report Symbol": "",
        "Symbol": "",
        "Dimension": "",
        "Nominal": "",
        "Tolerance -": "",
        "Tolerance +": "",
        "MIN": "",
        "MAX": "",
        "Specification": "",
        "Multiplier Count": 1,
        "Multiplier Index": "",
        "Needs Review": "YES",
        "Review Reason": "Manual sub-row - verify before export"
    };
    currentExtractedData.splice(insertAt, 0, newRow);
    renumberRows();
    renderTable(currentExtractedData);
    queuePreviewRefresh();
}

function parseBalloonNumber(value) {
    const match = String(value || "").trim().match(/^(\d+)(?:\.(\d+))?$/);
    if (!match) {
        return null;
    }
    return {
        main: Number(match[1]),
        suffix: match[2] || ""
    };
}

function groupedBalloonRows(rows) {
    const groupsByMain = new Map();
    rows.forEach((row, index) => {
        const parsed = parseBalloonNumber(row["Balloon No"]);
        if (!parsed) {
            const fallbackMain = 100000 + index;
            groupsByMain.set(fallbackMain, {
                main: fallbackMain,
                firstIndex: index,
                rows: [{ row, suffix: "" }]
            });
            return;
        }
        if (!groupsByMain.has(parsed.main)) {
            groupsByMain.set(parsed.main, {
                main: parsed.main,
                firstIndex: index,
                rows: []
            });
        }
        groupsByMain.get(parsed.main).rows.push({ row, suffix: parsed.suffix });
    });
    return Array.from(groupsByMain.values()).sort((left, right) => {
        if (left.main !== right.main) {
            return left.main - right.main;
        }
        return left.firstIndex - right.firstIndex;
    });
}

function displayBalloonNumber(value) {
    const parsed = parseBalloonNumber(value);
    return parsed ? String(parsed.main) : String(value || "").trim();
}

function applyBalloonNumberEdit(index, newValue, oldValue) {
    const target = parseBalloonNumber(newValue);
    if (!target || target.main < 1) {
        currentExtractedData[index]["Balloon No"] = oldValue || currentExtractedData[index]["Balloon No"] || String(index + 1);
        currentExtractedData[index]["Display Balloon No"] = displayBalloonNumber(currentExtractedData[index]["Balloon No"]);
        return;
    }

    const oldParsed = parseBalloonNumber(oldValue) || parseBalloonNumber(currentExtractedData[index]["Balloon No"]);
    if (!oldParsed) {
        currentExtractedData[index]["Balloon No"] = target.suffix ? `${target.main}.${target.suffix}` : String(target.main);
        currentExtractedData[index]["Display Balloon No"] = String(target.main);
        renumberRows();
        return;
    }

    const groups = groupedBalloonRows(currentExtractedData);
    const movingIndex = groups.findIndex((group) => group.main === oldParsed.main);
    if (movingIndex < 0) {
        renumberRows();
        return;
    }

    const [movingGroup] = groups.splice(movingIndex, 1);
    const insertIndex = Math.max(0, Math.min(target.main - 1, groups.length));
    groups.splice(insertIndex, 0, movingGroup);

    groups.forEach((group, groupIndex) => {
        const main = String(groupIndex + 1);
        group.rows.forEach(({ row, suffix }) => {
            row["Balloon No"] = suffix ? `${main}.${suffix}` : main;
            row["Display Balloon No"] = main;
        });
    });
    currentExtractedData = groups.flatMap((group) => group.rows.map(({ row }) => row));
}

document.getElementById("export-excel-btn").addEventListener("click", async () => {
    if (!currentJobId) {
        alert("Please process a drawing first.");
        return;
    }

    try {
        const response = await fetch("/api/export-excel", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                job_id: currentJobId,
                items: currentExtractedData,
                metadata: currentMetadata
            })
        });

        if (!response.ok) {
            throw new Error("Excel export failed.");
        }

        const blob = await response.blob();
        downloadBlob(blob, "FA_Inspection_Report.xlsx");
    } catch (error) {
        alert(error.message || "Error downloading Excel.");
    }
});

document.getElementById("export-corrected-pdf-btn").addEventListener("click", async () => {
    if (!currentJobId) {
        alert("Please process a drawing first.");
        return;
    }

    const button = document.getElementById("export-corrected-pdf-btn");
    const originalText = button.innerText;
    button.disabled = true;
    button.innerText = "Creating PDF...";
    loadingMessage.textContent = "Creating corrected balloon PDF...";
    loadingMessage.classList.remove("hidden");

    try {
        const response = await fetch("/api/export-corrected-pdf", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                job_id: currentJobId,
                items: currentExtractedData,
                metadata: currentMetadata
            })
        });

        if (!response.ok) {
            throw new Error("Corrected PDF export failed.");
        }

        const blob = await response.blob();
        downloadBlob(blob, "Ballooned_Drawing.pdf");
    } catch (error) {
        alert(error.message || "Error downloading corrected PDF.");
    } finally {
        button.disabled = false;
        button.innerText = originalText;
        loadingMessage.classList.add("hidden");
    }
});

document.getElementById("approve-download-btn").addEventListener("click", async () => {
    if (!currentJobId) {
        alert("Please process a drawing first.");
        return;
    }
    if (!currentExtractedData.length) {
        alert("There are no checked characteristics to approve.");
        return;
    }

    const confirmed = window.confirm(
        "FINAL QC APPROVAL\n\n" +
        "Confirm that you checked the complete drawing, including every characteristic, " +
        "symbol, value, tolerance, balloon, overlap, and title-block field.\n\n" +
        "This approval is permanent and cannot be overwritten."
    );
    if (!confirmed) {
        return;
    }

    const button = document.getElementById("approve-download-btn");
    const originalText = button.innerText;
    button.disabled = true;
    button.innerText = "Saving Approval...";
    loadingMessage.textContent = "Creating the permanent QC approval package...";
    loadingMessage.classList.remove("hidden");

    try {
        const response = await fetch(`/api/jobs/${encodeURIComponent(currentJobId)}/approve`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                items: currentExtractedData,
                metadata: currentMetadata,
                confirmed_complete: true
            })
        });
        const data = await parseResponse(response);
        if (!response.ok) {
            throw new Error(data.message || "Approval failed.");
        }

        currentApprovalId = data.approval_id || "";
        if (data.package_url) {
            downloadUrl(data.package_url, data.package_filename || "Approved_Drawing.zip");
        }
        const counts = data.change_counts || {};
        const summary = ["added", "edited", "deleted", "moved", "unchanged"]
            .map((name) => `${name}: ${counts[name] || 0}`)
            .join(", ");
        alert(
            `${data.message || "Drawing approved."}\nApproval ID: ${currentApprovalId}\n${summary}\n` +
            "Roboflow training was not started."
        );
    } catch (error) {
        alert(error.message || "Error saving the approval.");
    } finally {
        button.disabled = false;
        button.innerText = originalText;
        loadingMessage.classList.add("hidden");
    }
});

document.getElementById("add-row-btn").addEventListener("click", () => {
    currentExtractedData.push(createEmptyManualRow());
    renderTable(currentExtractedData);
    const tbody = document.getElementById("table-body");
    const lastRow = tbody.lastElementChild;
    if (lastRow) {
        lastRow.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
});

document.getElementById("download-pdf-btn").addEventListener("click", async () => {
    if (!currentPdfUrl) {
        alert("No balloon PDF is ready yet.");
        return;
    }
    if (currentJobId && currentExtractedData.length) {
        await refreshCorrectedPreview({ includePdf: true });
    }
    downloadUrl(currentPdfUrl, "Ballooned_Drawing.pdf");
});

document.getElementById("zoom-in-btn").addEventListener("click", () => {
    zoomPreview(0.25);
});

document.getElementById("zoom-out-btn").addEventListener("click", () => {
    zoomPreview(-0.25);
});

document.getElementById("zoom-reset-btn").addEventListener("click", () => {
    previewZoom = 1;
    applyPreviewZoom();
    previewContainer.scrollLeft = 0;
    previewContainer.scrollTop = 0;
});

document.getElementById("place-balloon-btn").addEventListener("click", () => {
    isPlaceBalloonMode = !isPlaceBalloonMode;
    const button = document.getElementById("place-balloon-btn");
    button.classList.toggle("active-tool", isPlaceBalloonMode);
    previewContainer.classList.toggle("is-selecting", isPlaceBalloonMode);
    button.innerText = isPlaceBalloonMode ? "Draw Box..." : "Add Balloon";
    loadingMessage.textContent = isPlaceBalloonMode
        ? "Draw a box around the missing dimension. OCR will extract it into the table."
        : "";
    loadingMessage.classList.toggle("hidden", !isPlaceBalloonMode);
});

function applyPreviewZoom() {
    previewImage.style.width = `${Math.round(previewZoom * 100)}%`;
    previewImage.style.maxWidth = "none";
}

function zoomPreview(delta, anchorX = null, anchorY = null) {
    const oldZoom = previewZoom;
    const nextZoom = Math.max(0.35, Math.min(5, previewZoom + delta));
    if (nextZoom === oldZoom) {
        return;
    }

    const rect = previewContainer.getBoundingClientRect();
    const offsetX = anchorX === null ? rect.width / 2 : anchorX - rect.left;
    const offsetY = anchorY === null ? rect.height / 2 : anchorY - rect.top;
    const beforeX = (previewContainer.scrollLeft + offsetX) / oldZoom;
    const beforeY = (previewContainer.scrollTop + offsetY) / oldZoom;

    previewZoom = nextZoom;
    applyPreviewZoom();

    previewContainer.scrollLeft = beforeX * previewZoom - offsetX;
    previewContainer.scrollTop = beforeY * previewZoom - offsetY;
}

function queuePreviewRefresh(delay = 800) {
    if (refreshPreviewTimer) {
        clearTimeout(refreshPreviewTimer);
    }
    refreshPreviewTimer = setTimeout(() => {
        refreshCorrectedPreview();
    }, delay);
}

async function refreshCorrectedPreview(options = {}) {
    return refreshCorrectedPreviewWithOptions(options);
}

async function refreshCorrectedPreviewWithOptions(options) {
    if (!currentJobId || !previewImage.src) {
        return;
    }
    const includePdf = Boolean(options.includePdf);
    if (previewRefreshInFlight) {
        previewRefreshPending = true;
        pendingPdfRefresh = pendingPdfRefresh || includePdf;
        return;
    }

    previewRefreshInFlight = true;
    try {
        const response = await fetch("/api/render-preview", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                job_id: currentJobId,
                items: currentExtractedData,
                metadata: currentMetadata,
                include_pdf: includePdf
            })
        });
        const data = await parseResponse(response);
        if (!response.ok || data.status !== "success") {
            throw new Error(data.message || "Preview refresh failed.");
        }
        currentExtractedData = data.items || currentExtractedData;
        if (data.ballooned_pdf) {
            currentPdfUrl = data.ballooned_pdf;
        }
        if (data.ballooned_image) {
            previewImage.src = `${data.ballooned_image}?v=${Date.now()}`;
        }
    } catch (error) {
        alert(error.message || "Error refreshing corrected preview.");
    } finally {
        previewRefreshInFlight = false;
        if (previewRefreshPending) {
            const shouldRefreshPdf = pendingPdfRefresh;
            previewRefreshPending = false;
            pendingPdfRefresh = false;
            if (shouldRefreshPdf) {
                refreshCorrectedPreviewWithOptions({ includePdf: true });
            } else {
                queuePreviewRefresh();
            }
        }
    }
}

previewContainer.addEventListener("contextmenu", (event) => {
    event.preventDefault();
});

previewContainer.addEventListener("mousedown", (event) => {
    if (isPlaceBalloonMode && event.button === 0) {
        event.preventDefault();
        startSelection(event);
        return;
    }

    if (event.button !== 0) {
        return;
    }

    event.preventDefault();
    isPanning = true;
    panStartX = event.clientX;
    panStartY = event.clientY;
    scrollStartLeft = previewContainer.scrollLeft;
    scrollStartTop = previewContainer.scrollTop;
    previewContainer.classList.add("is-panning");
});

window.addEventListener("mouseup", (event) => {
    if (isDrawingSelection && event.button === 0) {
        finishSelection(event);
        return;
    }

    if (event.button !== 0) {
        return;
    }

    isPanning = false;
    previewContainer.classList.remove("is-panning");
});

window.addEventListener("mousemove", (event) => {
    if (isDrawingSelection) {
        updateSelection(event);
        return;
    }

    if (!isPanning) {
        return;
    }

    event.preventDefault();
    previewContainer.scrollLeft = scrollStartLeft - (event.clientX - panStartX);
    previewContainer.scrollTop = scrollStartTop - (event.clientY - panStartY);
});

previewContainer.addEventListener("wheel", (event) => {
    event.preventDefault();
    const direction = event.deltaY < 0 ? 0.18 : -0.18;
    zoomPreview(direction, event.clientX, event.clientY);
}, { passive: false });

function imagePointFromEvent(event, options = {}) {
    if (!previewImage.naturalWidth || !previewImage.naturalHeight) {
        alert("Preview image is not ready yet.");
        return null;
    }

    const clampToImage = Boolean(options.clampToImage);
    const imageRect = previewImage.getBoundingClientRect();
    const rawImageX = event.clientX - imageRect.left;
    const rawImageY = event.clientY - imageRect.top;
    if (
        !clampToImage
        && (rawImageX < 0 || rawImageY < 0 || rawImageX > imageRect.width || rawImageY > imageRect.height)
    ) {
        return null;
    }
    const imageX = Math.max(0, Math.min(rawImageX, imageRect.width));
    const imageY = Math.max(0, Math.min(rawImageY, imageRect.height));
    const containerRect = previewContainer.getBoundingClientRect();

    return {
        screenX: previewContainer.scrollLeft + (imageRect.left - containerRect.left) + imageX,
        screenY: previewContainer.scrollTop + (imageRect.top - containerRect.top) + imageY,
        naturalX: Math.round(imageX * previewImage.naturalWidth / imageRect.width),
        naturalY: Math.round(imageY * previewImage.naturalHeight / imageRect.height)
    };
}

function startSelection(event) {
    if (manualOcrInFlight) {
        return;
    }
    const point = imagePointFromEvent(event);
    if (!point) {
        return;
    }
    selectionStart = point;
    isDrawingSelection = true;
    selectionBox.classList.remove("hidden");
    updateSelectionBox(point.screenX, point.screenY, 1, 1);
}

function updateSelection(event) {
    if (!selectionStart) {
        return;
    }
    const point = imagePointFromEvent(event, { clampToImage: true });
    if (!point) {
        return;
    }
    const left = Math.min(selectionStart.screenX, point.screenX);
    const top = Math.min(selectionStart.screenY, point.screenY);
    const width = Math.abs(point.screenX - selectionStart.screenX);
    const height = Math.abs(point.screenY - selectionStart.screenY);
    pendingSelectionFrame = { left, top, width, height };
    if (selectionAnimationFrame !== null) {
        return;
    }
    selectionAnimationFrame = window.requestAnimationFrame(() => {
        selectionAnimationFrame = null;
        if (!pendingSelectionFrame) {
            return;
        }
        const frame = pendingSelectionFrame;
        pendingSelectionFrame = null;
        updateSelectionBox(frame.left, frame.top, frame.width, frame.height);
    });
}

function updateSelectionBox(left, top, width, height) {
    selectionBox.style.left = `${left}px`;
    selectionBox.style.top = `${top}px`;
    selectionBox.style.width = `${width}px`;
    selectionBox.style.height = `${height}px`;
}

async function finishSelection(event) {
    if (manualOcrInFlight) {
        return;
    }
    const endPoint = imagePointFromEvent(event, { clampToImage: true });
    const startPoint = selectionStart;
    isDrawingSelection = false;
    selectionStart = null;
    if (selectionAnimationFrame !== null) {
        window.cancelAnimationFrame(selectionAnimationFrame);
        selectionAnimationFrame = null;
    }
    pendingSelectionFrame = null;

    if (!startPoint || !endPoint) {
        selectionBox.classList.add("hidden");
        return;
    }

    const x = Math.min(startPoint.naturalX, endPoint.naturalX);
    const y = Math.min(startPoint.naturalY, endPoint.naturalY);
    const width = Math.abs(endPoint.naturalX - startPoint.naturalX);
    const height = Math.abs(endPoint.naturalY - startPoint.naturalY);
    if (width < 8 || height < 8) {
        selectionBox.classList.add("hidden");
        alert("Draw a larger box around the dimension.");
        return;
    }

    selectionBox.classList.add("is-processing");
    await addManualBalloonFromBox({ x, y, width, height });
}

async function addManualBalloonFromBox(box) {
    if (!currentJobId) {
        alert("Please process a drawing first.");
        return;
    }
    if (manualOcrInFlight) {
        return;
    }

    manualOcrInFlight = true;
    loadingMessage.textContent = "OCR reading selected dimension...";
    loadingMessage.classList.remove("hidden");
    try {
        const response = await fetch("/api/ocr-crop", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                job_id: currentJobId,
                box
            })
        });
        const data = await parseResponse(response);
        if (!response.ok || data.status !== "success") {
            throw new Error(data.message || "Selected crop OCR failed.");
        }

        const rows = Array.isArray(data.rows) && data.rows.length
            ? data.rows
            : [data.row || createEmptyManualRow()];
        insertManualCropRows(rows);
        renderTable(currentExtractedData);
        await refreshCorrectedPreview();
    } catch (error) {
        alert(error.message || "Error adding balloon.");
    } finally {
        manualOcrInFlight = false;
        selectionBox.classList.remove("is-processing");
        selectionBox.classList.add("hidden");
        isPlaceBalloonMode = false;
        const button = document.getElementById("place-balloon-btn");
        button.classList.remove("active-tool");
        previewContainer.classList.remove("is-selecting");
        button.innerText = "Add Balloon";
        loadingMessage.classList.add("hidden");
    }
}

function addManualBalloonFromClick(event) {
    if (!previewImage.naturalWidth || !previewImage.naturalHeight) {
        alert("Preview image is not ready yet.");
        return;
    }

    const imageRect = previewImage.getBoundingClientRect();
    const clickX = event.clientX - imageRect.left;
    const clickY = event.clientY - imageRect.top;
    if (clickX < 0 || clickY < 0 || clickX > imageRect.width || clickY > imageRect.height) {
        return;
    }

    const naturalX = Math.round(clickX * previewImage.naturalWidth / imageRect.width);
    const naturalY = Math.round(clickY * previewImage.naturalHeight / imageRect.height);
    const symbol = prompt("Symbol? Example: blank, R, C, Ra, //, ⊥", "");
    if (symbol === null) {
        return;
    }
    const dimension = prompt("Dimension/value? Example: 21.5, M8, 0.05", "");
    if (dimension === null || !dimension.trim()) {
        return;
    }
    const minus = prompt("Tolerance (-)? Leave blank if none.", "");
    if (minus === null) {
        return;
    }
    const plus = prompt("Tolerance (+)? Leave blank if none.", "");
    if (plus === null) {
        return;
    }

    const row = createEmptyManualRow();
    row["Report Symbol"] = symbol.trim();
    row["Symbol"] = symbol.trim();
    row["Dimension"] = dimension.trim();
    row["Specification"] = `${symbol.trim()} ${dimension.trim()}`.trim();
    row["Tolerance -"] = minus.trim();
    row["Tolerance +"] = plus.trim();
    row["Measurement Type"] = "manual";
    row["Review Reason"] = "Manual balloon placed by user";
    row["X"] = Math.max(0, naturalX - 35);
    row["Y"] = Math.max(0, naturalY - 18);
    row["Width"] = 70;
    row["Height"] = 36;
    currentExtractedData.push(row);
    renderTable(currentExtractedData);

    isPlaceBalloonMode = false;
    const button = document.getElementById("place-balloon-btn");
    button.classList.remove("active-tool");
    button.innerText = "Place Balloon";
    loadingMessage.classList.add("hidden");
}

function downloadUrl(url, filename) {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
}

function downloadBlob(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    downloadUrl(url, filename);
    window.URL.revokeObjectURL(url);
}
