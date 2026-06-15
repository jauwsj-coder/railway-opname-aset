const FACILITY_CONFIG = {
  MASTER_SHEET: "MASTER_ASET",
  DAMAGED_SHEET: "ASET_RUSAK",
  DISPOSAL_SHEET: "ASET_DISPOSAL",
  LOG_SHEET: "LOG_FASILITAS_ASET",
  DAMAGED_MARKERS: ["RUSAK", "BROKEN", "MAINTENANCE", "NOT OK"],
  MASTER_HEADERS: [
    "NOMOR ASSET", "TYPE", "NO LAYOUT", "USER", "OPNAME", "KONDISI", "AREA",
    "LOKASI DETAIL", "KONDISI TERAKHIR", "STATUS TERAKHIR",
    "TANGGAL OPNAME TERAKHIR", "KETERANGAN TERAKHIR", "DOKUMENTASI TERAKHIR"
  ],
  DAMAGED_HEADERS: [
    "NOMOR ASSET", "TYPE", "NO LAYOUT", "USER", "AREA", "LOKASI DETAIL",
    "KONDISI TERAKHIR", "STATUS TERAKHIR", "KETERANGAN TERAKHIR",
    "DOKUMENTASI TERAKHIR", "STATUS PERBAIKAN", "TANGGAL UPDATE",
    "PIC FOLLOW UP", "CATATAN PERBAIKAN", "DOKUMENTASI PERBAIKAN"
  ],
  DISPOSAL_HEADERS: [
    "NOMOR ASSET", "TYPE", "NO LAYOUT", "USER", "AREA", "LOKASI DETAIL",
    "KONDISI TERAKHIR", "STATUS TERAKHIR", "ALASAN DISPOSAL", "STATUS DISPOSAL",
    "TANGGAL UPDATE", "PIC", "CATATAN DISPOSAL", "DOKUMENTASI DISPOSAL"
  ],
  LOG_HEADERS: [
    "TIMESTAMP", "NOMOR ASSET", "TYPE", "AREA", "LOKASI DETAIL", "AKTIVITAS",
    "STATUS SEBELUM", "STATUS SESUDAH", "KONDISI SEBELUM", "KONDISI SESUDAH",
    "PIC", "CATATAN", "DOKUMENTASI"
  ]
};

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("Fasilitas Aset")
    .addItem("Setup Sheet Fasilitas", "setupSheetFasilitas")
    .addSeparator()
    .addItem("Sync Aset Rusak", "syncAsetRusak")
    .addItem("Proses Update Perbaikan", "prosesUpdatePerbaikan")
    .addItem("Proses Disposal", "prosesDisposal")
    .addSeparator()
    .addItem("Refresh Semua", "refreshSemua")
    .addToUi();
}

function setupSheetFasilitas() {
  return runMenuAction_("Setup Sheet Fasilitas", function () {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    validateSheetHeaders_(getRequiredSheet_(ss, FACILITY_CONFIG.MASTER_SHEET), FACILITY_CONFIG.MASTER_HEADERS);
    const results = [
      ensureSheet_(ss, FACILITY_CONFIG.DAMAGED_SHEET, FACILITY_CONFIG.DAMAGED_HEADERS),
      ensureSheet_(ss, FACILITY_CONFIG.DISPOSAL_SHEET, FACILITY_CONFIG.DISPOSAL_HEADERS),
      ensureSheet_(ss, FACILITY_CONFIG.LOG_SHEET, FACILITY_CONFIG.LOG_HEADERS)
    ];
    return "Setup selesai. Header baru ditambahkan: " +
      results.reduce(function (total, item) { return total + item.addedHeaders; }, 0) + ".";
  });
}

function syncAsetRusak() {
  return runMenuAction_("Sync Aset Rusak", function () {
    setupSheetFasilitasCore_();
    return syncAsetRusakCore_();
  });
}

function prosesUpdatePerbaikan() {
  return runMenuAction_("Proses Update Perbaikan", function () {
    setupSheetFasilitasCore_();
    return prosesUpdatePerbaikanCore_();
  });
}

function prosesDisposal() {
  return runMenuAction_("Proses Disposal", function () {
    setupSheetFasilitasCore_();
    return prosesDisposalCore_();
  });
}

function refreshSemua() {
  return runMenuAction_("Refresh Semua", function () {
    setupSheetFasilitasCore_();
    const damaged = syncAsetRusakCore_();
    const repairs = prosesUpdatePerbaikanCore_();
    const disposal = prosesDisposalCore_();
    return [damaged, repairs, disposal].join("\n");
  });
}

function setupSheetFasilitasCore_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  validateSheetHeaders_(getRequiredSheet_(ss, FACILITY_CONFIG.MASTER_SHEET), FACILITY_CONFIG.MASTER_HEADERS);
  ensureSheet_(ss, FACILITY_CONFIG.DAMAGED_SHEET, FACILITY_CONFIG.DAMAGED_HEADERS);
  ensureSheet_(ss, FACILITY_CONFIG.DISPOSAL_SHEET, FACILITY_CONFIG.DISPOSAL_HEADERS);
  ensureSheet_(ss, FACILITY_CONFIG.LOG_SHEET, FACILITY_CONFIG.LOG_HEADERS);
}

function syncAsetRusakCore_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const master = readSheet_(getRequiredSheet_(ss, FACILITY_CONFIG.MASTER_SHEET), FACILITY_CONFIG.MASTER_HEADERS);
  const damaged = readSheet_(getRequiredSheet_(ss, FACILITY_CONFIG.DAMAGED_SHEET), FACILITY_CONFIG.DAMAGED_HEADERS);
  const existing = {};
  damaged.rows.forEach(function (row) {
    if (normalize_(row["NOMOR ASSET"])) existing[normalize_(row["NOMOR ASSET"])] = true;
  });

  const newRows = [];
  master.rows.forEach(function (asset) {
    const code = normalize_(asset["NOMOR ASSET"]);
    if (!code || existing[code] || !isDamagedAsset_(asset)) return;
    newRows.push(recordToRow_(damaged.headers, {
      "NOMOR ASSET": asset["NOMOR ASSET"],
      "TYPE": asset["TYPE"],
      "NO LAYOUT": asset["NO LAYOUT"],
      "USER": asset["USER"],
      "AREA": asset["AREA"],
      "LOKASI DETAIL": asset["LOKASI DETAIL"],
      "KONDISI TERAKHIR": asset["KONDISI TERAKHIR"] || asset["KONDISI"],
      "STATUS TERAKHIR": asset["STATUS TERAKHIR"],
      "KETERANGAN TERAKHIR": asset["KETERANGAN TERAKHIR"],
      "DOKUMENTASI TERAKHIR": asset["DOKUMENTASI TERAKHIR"],
      "STATUS PERBAIKAN": "MENUNGGU PERBAIKAN",
      "TANGGAL UPDATE": new Date()
    }));
    existing[code] = true;
  });
  appendRows_(damaged.sheet, newRows);
  return "Sync Aset Rusak: " + newRows.length + " aset baru ditambahkan.";
}

function prosesUpdatePerbaikanCore_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const master = readSheet_(getRequiredSheet_(ss, FACILITY_CONFIG.MASTER_SHEET), FACILITY_CONFIG.MASTER_HEADERS);
  const damaged = readSheet_(getRequiredSheet_(ss, FACILITY_CONFIG.DAMAGED_SHEET), FACILITY_CONFIG.DAMAGED_HEADERS);
  const disposal = readSheet_(getRequiredSheet_(ss, FACILITY_CONFIG.DISPOSAL_SHEET), FACILITY_CONFIG.DISPOSAL_HEADERS);
  const log = readSheet_(getRequiredSheet_(ss, FACILITY_CONFIG.LOG_SHEET), FACILITY_CONFIG.LOG_HEADERS);
  const masterByCode = indexByAsset_(master.rows);
  const disposalByCode = indexByAsset_(disposal.rows);
  const logs = [];
  const disposalRows = [];
  let repaired = 0;
  let cannotRepair = 0;

  damaged.rows.forEach(function (damagedAsset) {
    const code = normalize_(damagedAsset["NOMOR ASSET"]);
    const status = normalize_(damagedAsset["STATUS PERBAIKAN"]);
    const asset = masterByCode[code];
    if (!code || !asset) return;

    if (status === "SELESAI DIPERBAIKI" &&
        !(normalize_(asset["KONDISI TERAKHIR"]) === "BAIK" && normalize_(asset["STATUS TERAKHIR"]) === "SELESAI DIPERBAIKI")) {
      const before = snapshot_(asset);
      updateMasterAsset_(master, asset._rowNumber, {
        "KONDISI TERAKHIR": "BAIK",
        "STATUS TERAKHIR": "SELESAI DIPERBAIKI",
        "TANGGAL OPNAME TERAKHIR": new Date(),
        "KETERANGAN TERAKHIR": damagedAsset["CATATAN PERBAIKAN"],
        "DOKUMENTASI TERAKHIR": damagedAsset["DOKUMENTASI PERBAIKAN"]
      });
      logs.push(facilityLogRow_(log.headers, asset, "SELESAI PERBAIKAN", before.status, "SELESAI DIPERBAIKI",
        before.condition, "BAIK", damagedAsset["PIC FOLLOW UP"], damagedAsset["CATATAN PERBAIKAN"], damagedAsset["DOKUMENTASI PERBAIKAN"]));
      repaired++;
    }

    const existingDisposal = disposalByCode[code];
    const disposalStatus = existingDisposal ? normalize_(existingDisposal["STATUS DISPOSAL"]) : "";
    const canSendToDisposal = !existingDisposal || disposalStatus === "MENUNGGU DISPOSAL";
    if (status === "TIDAK BISA DIPERBAIKI" && canSendToDisposal &&
        normalize_(asset["STATUS TERAKHIR"]) !== "MENUNGGU DISPOSAL") {
      const before = snapshot_(asset);
      if (!existingDisposal) {
        disposalRows.push(recordToRow_(disposal.headers, {
          "NOMOR ASSET": asset["NOMOR ASSET"], "TYPE": asset["TYPE"], "NO LAYOUT": asset["NO LAYOUT"],
          "USER": asset["USER"], "AREA": asset["AREA"], "LOKASI DETAIL": asset["LOKASI DETAIL"],
          "KONDISI TERAKHIR": asset["KONDISI TERAKHIR"] || asset["KONDISI"],
          "STATUS TERAKHIR": "MENUNGGU DISPOSAL", "ALASAN DISPOSAL": damagedAsset["CATATAN PERBAIKAN"],
          "STATUS DISPOSAL": "MENUNGGU DISPOSAL", "TANGGAL UPDATE": new Date(),
          "PIC": damagedAsset["PIC FOLLOW UP"], "CATATAN DISPOSAL": damagedAsset["CATATAN PERBAIKAN"],
          "DOKUMENTASI DISPOSAL": damagedAsset["DOKUMENTASI PERBAIKAN"]
        }));
        disposalByCode[code] = {"NOMOR ASSET": asset["NOMOR ASSET"], "STATUS DISPOSAL": "MENUNGGU DISPOSAL"};
      }
      updateMasterAsset_(master, asset._rowNumber, {"STATUS TERAKHIR": "MENUNGGU DISPOSAL"});
      logs.push(facilityLogRow_(log.headers, asset, "TIDAK BISA DIPERBAIKI", before.status, "MENUNGGU DISPOSAL",
        before.condition, before.condition, damagedAsset["PIC FOLLOW UP"], damagedAsset["CATATAN PERBAIKAN"], damagedAsset["DOKUMENTASI PERBAIKAN"]));
      cannotRepair++;
    }
  });
  appendRows_(disposal.sheet, disposalRows);
  appendRows_(log.sheet, logs);
  return "Update Perbaikan: " + repaired + " selesai diperbaiki, " + cannotRepair + " diteruskan ke disposal.";
}

function prosesDisposalCore_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const master = readSheet_(getRequiredSheet_(ss, FACILITY_CONFIG.MASTER_SHEET), FACILITY_CONFIG.MASTER_HEADERS);
  const disposal = readSheet_(getRequiredSheet_(ss, FACILITY_CONFIG.DISPOSAL_SHEET), FACILITY_CONFIG.DISPOSAL_HEADERS);
  const log = readSheet_(getRequiredSheet_(ss, FACILITY_CONFIG.LOG_SHEET), FACILITY_CONFIG.LOG_HEADERS);
  const masterByCode = indexByAsset_(master.rows);
  const logs = [];
  let completed = 0;
  let cancelled = 0;

  disposal.rows.forEach(function (disposalAsset) {
    const code = normalize_(disposalAsset["NOMOR ASSET"]);
    const status = normalize_(disposalAsset["STATUS DISPOSAL"]);
    const asset = masterByCode[code];
    if (!code || !asset) return;

    if (status === "SELESAI DISPOSAL" &&
        !(normalize_(asset["KONDISI TERAKHIR"]) === "DISPOSAL" && normalize_(asset["STATUS TERAKHIR"]) === "DISPOSAL")) {
      const before = snapshot_(asset);
      updateMasterAsset_(master, asset._rowNumber, {
        "KONDISI TERAKHIR": "DISPOSAL", "STATUS TERAKHIR": "DISPOSAL",
        "TANGGAL OPNAME TERAKHIR": new Date(), "KETERANGAN TERAKHIR": disposalAsset["CATATAN DISPOSAL"],
        "DOKUMENTASI TERAKHIR": disposalAsset["DOKUMENTASI DISPOSAL"]
      });
      logs.push(facilityLogRow_(log.headers, asset, "SELESAI DISPOSAL", before.status, "DISPOSAL",
        before.condition, "DISPOSAL", disposalAsset["PIC"], disposalAsset["CATATAN DISPOSAL"], disposalAsset["DOKUMENTASI DISPOSAL"]));
      completed++;
    }

    if (status === "BATAL DISPOSAL" && normalize_(asset["STATUS TERAKHIR"]) !== "RUSAK") {
      const before = snapshot_(asset);
      updateMasterAsset_(master, asset._rowNumber, {"STATUS TERAKHIR": "RUSAK"});
      logs.push(facilityLogRow_(log.headers, asset, "BATAL DISPOSAL", before.status, "RUSAK",
        before.condition, before.condition, disposalAsset["PIC"], disposalAsset["CATATAN DISPOSAL"], disposalAsset["DOKUMENTASI DISPOSAL"]));
      cancelled++;
    }
  });
  appendRows_(log.sheet, logs);
  return "Proses Disposal: " + completed + " selesai disposal, " + cancelled + " batal disposal.";
}

function runMenuAction_(label, action) {
  const lock = LockService.getDocumentLock();
  lock.waitLock(30000);
  try {
    const message = action();
    SpreadsheetApp.getActiveSpreadsheet().toast(message, label, 8);
    return message;
  } catch (error) {
    const message = label + " gagal: " + String(error.message || error);
    SpreadsheetApp.getUi().alert(message);
    throw error;
  } finally {
    lock.releaseLock();
  }
}

function ensureSheet_(ss, name, requiredHeaders) {
  const sheet = ss.getSheetByName(name) || ss.insertSheet(name);
  const lastColumn = Math.max(sheet.getLastColumn(), 1);
  const headerRow = sheet.getRange(1, 1, 1, lastColumn).getDisplayValues()[0].map(clean_);
  const existing = headerRow.filter(function (value) { return value; });
  const missing = requiredHeaders.filter(function (header) { return existing.indexOf(header) === -1; });
  if (existing.length === 0) {
    sheet.getRange(1, 1, 1, requiredHeaders.length).setValues([requiredHeaders]);
  } else if (missing.length) {
    let lastHeaderColumn = headerRow.length;
    while (lastHeaderColumn > 0 && !headerRow[lastHeaderColumn - 1]) lastHeaderColumn--;
    sheet.getRange(1, lastHeaderColumn + 1, 1, missing.length).setValues([missing]);
  }
  sheet.setFrozenRows(1);
  sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), requiredHeaders.length)).setFontWeight("bold");
  validateSheetHeaders_(sheet, requiredHeaders);
  return {name: name, addedHeaders: missing.length};
}

function readSheet_(sheet, requiredHeaders) {
  validateSheetHeaders_(sheet, requiredHeaders);
  const values = sheet.getDataRange().getValues();
  const headers = values[0].map(clean_);
  const rows = values.slice(1).map(function (valuesRow, index) {
    const row = {_rowNumber: index + 2};
    headers.forEach(function (header, column) { row[header] = valuesRow[column]; });
    return row;
  });
  return {sheet: sheet, headers: headers, headerMap: headerMap_(headers), rows: rows};
}

function validateSheetHeaders_(sheet, requiredHeaders) {
  const headers = sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), 1)).getDisplayValues()[0].map(clean_);
  const missing = requiredHeaders.filter(function (header) { return headers.indexOf(header) === -1; });
  if (missing.length) throw new Error("Header sheet " + sheet.getName() + " belum lengkap: " + missing.join(", "));
}

function getRequiredSheet_(ss, name) {
  const sheet = ss.getSheetByName(name);
  if (!sheet) throw new Error("Sheet " + name + " belum tersedia.");
  return sheet;
}

function updateMasterAsset_(master, rowNumber, changes) {
  Object.keys(changes).forEach(function (header) {
    master.sheet.getRange(rowNumber, master.headerMap[header]).setValue(changes[header]);
  });
}

function facilityLogRow_(headers, asset, activity, statusBefore, statusAfter, conditionBefore, conditionAfter, pic, notes, documentation) {
  return recordToRow_(headers, {
    "TIMESTAMP": new Date(), "NOMOR ASSET": asset["NOMOR ASSET"], "TYPE": asset["TYPE"],
    "AREA": asset["AREA"], "LOKASI DETAIL": asset["LOKASI DETAIL"], "AKTIVITAS": activity,
    "STATUS SEBELUM": statusBefore, "STATUS SESUDAH": statusAfter,
    "KONDISI SEBELUM": conditionBefore, "KONDISI SESUDAH": conditionAfter,
    "PIC": pic, "CATATAN": notes, "DOKUMENTASI": documentation
  });
}

function appendRows_(sheet, rows) {
  if (!rows.length) return;
  sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, rows[0].length).setValues(rows);
}

function recordToRow_(headers, record) {
  return headers.map(function (header) { return Object.prototype.hasOwnProperty.call(record, header) ? record[header] : ""; });
}

function indexByAsset_(rows) {
  const result = {};
  rows.forEach(function (row) {
    const code = normalize_(row["NOMOR ASSET"]);
    if (code && !result[code]) result[code] = row;
  });
  return result;
}

function headerMap_(headers) {
  const result = {};
  headers.forEach(function (header, index) { result[header] = index + 1; });
  return result;
}

function snapshot_(asset) {
  return {
    status: clean_(asset["STATUS TERAKHIR"]),
    condition: clean_(asset["KONDISI TERAKHIR"] || asset["KONDISI"])
  };
}

function isDamagedAsset_(asset) {
  const text = normalize_((asset["KONDISI TERAKHIR"] || asset["KONDISI"]) + " " + asset["STATUS TERAKHIR"]);
  return FACILITY_CONFIG.DAMAGED_MARKERS.some(function (marker) { return text.indexOf(marker) !== -1; });
}

function normalize_(value) {
  return clean_(value).toUpperCase();
}

function clean_(value) {
  return value === null || value === undefined ? "" : String(value).trim();
}
