const PERIOD_PATTERN = /^(\d{4})-(Jan-Jun|Jul-Des)$/;
const MAX_FILE_BYTES = 10 * 1024 * 1024;

function doPost(e) {
  try {
    const payload = JSON.parse((e && e.postData && e.postData.contents) || "{}");
    validateSecret_(payload.secret);

    if (payload.action === "upload") {
      return jsonResponse_(uploadPhoto_(payload, false));
    }
    if (payload.action === "test") {
      return jsonResponse_(uploadPhoto_(payload, true));
    }
    if (payload.action === "cleanup") {
      return jsonResponse_({ success: true, cleanup: cleanupDrivePhotos() });
    }
    throw new Error("Action Apps Script tidak valid.");
  } catch (error) {
    return jsonResponse_({ success: false, message: String(error.message || error) });
  }
}

function uploadPhoto_(payload, isTest) {
  if (!payload.base64Data || !payload.fileName || !payload.mimeType) {
    throw new Error("Data foto, nama file, dan MIME type wajib dikirim.");
  }
  if (!/^image\/(jpeg|png|webp)$/.test(payload.mimeType)) {
    throw new Error("Format foto harus JPG, PNG, atau WEBP.");
  }

  const bytes = Utilities.base64Decode(payload.base64Data);
  if (bytes.length > MAX_FILE_BYTES) {
    throw new Error("Ukuran foto maksimal 10 MB.");
  }

  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const periodName = currentPeriodName_();
    const periodFolder = getOrCreatePeriodFolder_(periodName);
    const blob = Utilities.newBlob(bytes, payload.mimeType, sanitizeFileName_(payload.fileName));
    const file = periodFolder.createFile(blob);

    if (isTest) {
      file.setTrashed(true);
    } else {
      try {
        file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
      } catch (sharingError) {
        // Domain Google Workspace tertentu melarang public link. File tetap berhasil disimpan.
      }
    }

    const cleanup = cleanupDrivePhotosUnlocked_();
    return {
      success: true,
      url: isTest ? "" : file.getUrl(),
      fileId: file.getId(),
      period: periodName,
      testFileMovedToTrash: isTest,
      cleanup: cleanup,
      message: isTest
        ? "Tes upload melalui Apps Script berhasil dan file tes dipindahkan ke Trash."
        : "Foto berhasil diunggah melalui Google Apps Script."
    };
  } finally {
    lock.releaseLock();
  }
}

function cleanupDrivePhotos() {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    return cleanupDrivePhotosUnlocked_();
  } finally {
    lock.releaseLock();
  }
}

function cleanupDrivePhotosUnlocked_() {
  const root = getRootFolder_();
  const folders = root.getFolders();
  const periods = [];

  while (folders.hasNext()) {
    const folder = folders.next();
    const key = periodSortKey_(folder.getName());
    if (key !== null) {
      periods.push({ key: key, folder: folder });
    }
  }

  periods.sort(function(a, b) { return b.key - a.key; });
  const keptPeriods = periods.slice(0, 2).map(function(item) {
    return item.folder.getName();
  });
  const trashedFolders = [];
  let affectedFiles = 0;
  let affectedFolders = 0;

  periods.slice(2).forEach(function(item) {
    const counts = countDescendants_(item.folder);
    affectedFiles += counts.files;
    affectedFolders += counts.folders + 1;
    trashedFolders.push(item.folder.getName());
    item.folder.setTrashed(true);
  });

  return {
    keptPeriods: keptPeriods,
    trashedFolders: trashedFolders,
    affectedFiles: affectedFiles,
    affectedFolders: affectedFolders,
    affectedItems: affectedFiles + affectedFolders
  };
}

function createDailyCleanupTrigger() {
  ScriptApp.getProjectTriggers().forEach(function(trigger) {
    if (trigger.getHandlerFunction() === "cleanupDrivePhotos") {
      ScriptApp.deleteTrigger(trigger);
    }
  });
  ScriptApp.newTrigger("cleanupDrivePhotos").timeBased().everyDays(1).atHour(2).create();
}

function getOrCreatePeriodFolder_(name) {
  const root = getRootFolder_();
  const matches = root.getFoldersByName(name);
  return matches.hasNext() ? matches.next() : root.createFolder(name);
}

function getRootFolder_() {
  const folderId = PropertiesService.getScriptProperties().getProperty("PHOTO_FOLDER_ID");
  if (!folderId) {
    throw new Error("Script Property PHOTO_FOLDER_ID belum diisi.");
  }
  try {
    return DriveApp.getFolderById(folderId);
  } catch (error) {
    throw new Error("Folder Drive owner tidak dapat diakses. Periksa PHOTO_FOLDER_ID.");
  }
}

function validateSecret_(receivedSecret) {
  const expectedSecret = PropertiesService.getScriptProperties().getProperty("PHOTO_UPLOAD_SECRET");
  if (!expectedSecret) {
    throw new Error("Script Property PHOTO_UPLOAD_SECRET belum diisi.");
  }
  if (!receivedSecret || receivedSecret !== expectedSecret) {
    throw new Error("PHOTO_UPLOAD_SECRET tidak valid.");
  }
}

function currentPeriodName_() {
  const timezone = Session.getScriptTimeZone() || "Asia/Jakarta";
  const year = Utilities.formatDate(new Date(), timezone, "yyyy");
  const month = Number(Utilities.formatDate(new Date(), timezone, "M"));
  return year + "-" + (month <= 6 ? "Jan-Jun" : "Jul-Des");
}

function periodSortKey_(name) {
  const match = String(name || "").match(PERIOD_PATTERN);
  if (!match) {
    return null;
  }
  return Number(match[1]) * 2 + (match[2] === "Jul-Des" ? 1 : 0);
}

function countDescendants_(folder) {
  let files = 0;
  let folders = 0;
  const childFiles = folder.getFiles();
  const childFolders = folder.getFolders();

  while (childFiles.hasNext()) {
    childFiles.next();
    files++;
  }
  while (childFolders.hasNext()) {
    const child = childFolders.next();
    const nested = countDescendants_(child);
    files += nested.files;
    folders += nested.folders + 1;
  }
  return { files: files, folders: folders };
}

function sanitizeFileName_(name) {
  return String(name || "foto-opname.jpg").replace(/[\\/:*?"<>|]+/g, "_").substring(0, 180);
}

function jsonResponse_(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}
